#!/usr/bin/env bash
# E2E screenshot tests for garmin-router-widget.
#
# Runs inside the connectiq-tester Docker container.  For each scenario it:
#   1. (Re-)starts mock_server.py in the appropriate mode
#   2. Loads the compiled widget in the CIQ simulator
#   3. Waits for the HTTP round-trip to complete
#   4. Presses keys and captures screenshots
#
# Usage (inside container, called by CI):
#   e2e.sh [DEVICE] [CERT_PATH]
#
# Prerequisites already provided by the container image:
#   monkeyc, monkeydo, simulator, xdotool, imagemagick (import), Xvfb, openssl

set -euo pipefail

DEVICE="${1:-edge530}"
CERT="${2:-}"
PORT=8765
DISP=:1
APP_DIR="/app"
RESULTS="$APP_DIR/test-results/e2e"
WORK="/tmp/app-e2e"
MOCK_PID=""
APP_PID=""
SIM_PID=""
XVFB_PID=""

mkdir -p "$RESULTS"

# ── SDK device inventory (diagnostic) ───────────────────────────────────────
echo "[e2e] SDK devices: $(ls /root/.Garmin/ConnectIQ/Devices 2>/dev/null | tr '\n' ' ')"
echo "[e2e] Device profile contents: $(ls /root/.Garmin/ConnectIQ/Devices/${DEVICE}/ 2>/dev/null | tr '\n' ' ')"
echo "[e2e] CONNECTIQ_HOME=${CONNECTIQ_HOME:-unset}"
echo "[e2e] SDK share/simulator (recursive): $(find ${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share/simulator -type f 2>/dev/null | tr '\n' ' ')"
echo "[e2e] SDK all font-like files: $(find ${CONNECTIQ_HOME:-/opt/connectiq-sdk} -type f \( -iname '*font*' -o -name '*.fnt' -o -name '*.fon' \) 2>/dev/null | tr '\n' ' ')"
echo "[e2e] ~/.Garmin/ConnectIQ top-level: $(ls /root/.Garmin/ConnectIQ/ 2>/dev/null | tr '\n' ' ')"

# ── Python3 guard ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[e2e] python3 not found — installing..."
    apt-get update -qq && apt-get install -y --quiet python3 >/dev/null
fi

# ── Ensure simulator finds SDK at the hardcoded ~/.Garmin/ConnectIQ path ─────
# connectiq-tester (the reference impl) puts the SDK directly inside
# ~/.Garmin/ConnectIQ/, so share/simulator/ lives at the hardcoded path the
# simulator uses. Our SDK is at /opt/connectiq-sdk/ — symlink share/ so the
# simulator finds it at both locations.
if [ ! -e /root/.Garmin/ConnectIQ/share ]; then
    echo "[e2e] Symlinking SDK share → ~/.Garmin/ConnectIQ/share"
    ln -s "${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share" /root/.Garmin/ConnectIQ/share
fi

echo "[e2e] ── Setup ──────────────────────────────────────────────────────"

# ── Copy widget source to a writable temp dir ────────────────────────────────
# We patch backendUrl without touching the mounted volume (checked-out source).
rm -rf "$WORK"
cp -r "$APP_DIR" "$WORK"
sed -i \
    "s|<property id=\"backendUrl\" type=\"string\">.*</property>|<property id=\"backendUrl\" type=\"string\">http://127.0.0.1:${PORT}</property>|" \
    "$WORK/resources/settings/properties.xml"
echo "[e2e] backendUrl patched → http://127.0.0.1:${PORT}"

# The sign-in gate treats a non-placeholder apiKey as an already-issued token,
# so the authenticated scenarios (A–C) proceed straight to the course list; the
# mock server ignores X-Api-Key. Scenario D recompiles with an empty apiKey to
# exercise the signed-out prompt.
patch_api_key() {
    sed -i \
        "s|<property id=\"apiKey\" type=\"string\">.*</property>|<property id=\"apiKey\" type=\"string\">${1}</property>|" \
        "$WORK/resources/settings/properties.xml"
}
patch_api_key "e2e-token"
echo "[e2e] apiKey patched → e2e-token (authenticated scenarios)"

# ── Cleanup on exit ──────────────────────────────────────────────────────────
cleanup() {
    echo "[e2e] cleanup"
    [ -n "$APP_PID"  ] && kill "$APP_PID"  2>/dev/null || true
    [ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true
    [ -n "$SIM_PID"  ] && kill "$SIM_PID"  2>/dev/null || true
    [ -n "$XVFB_PID" ] && kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── Virtual display ──────────────────────────────────────────────────────────
Xvfb "$DISP" -screen 0 1280x1024x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 2

# ── Developer certificate ────────────────────────────────────────────────────
if [ -z "$CERT" ]; then
    CERT="/tmp/dev_key.der"
    openssl genrsa 4096 2>/dev/null \
        | openssl pkcs8 -topk8 -nocrypt -outform DER -out "$CERT" 2>/dev/null
    echo "[e2e] Generated temporary developer key"
fi

# ── Compile widget (no -t: app mode, not unit-test mode) ────────────────────
cd "$WORK"
mkdir -p test-results/build
compile_app() {
    local out="$1"
    monkeyc -f monkey.jungle -d "$DEVICE" -o "$out" -y "$CERT" -l 3
    echo "[e2e] Compiled OK → $out"
}
compile_app test-results/build/app.prg

# ── Start CIQ Simulator ──────────────────────────────────────────────────────
DISPLAY=$DISP simulator &
SIM_PID=$!
sleep 5   # wait for simulator to be ready

# ── Helpers ──────────────────────────────────────────────────────────────────
win() {
    # Pick the largest window named "CIQ Simulator" — avoids the menu-bar
    # sub-window which xdotool often lists first.
    local best_wid="" best_area=0
    while IFS= read -r wid; do
        local geom w h area
        geom=$(DISPLAY=$DISP xdotool getwindowgeometry "$wid" 2>/dev/null) || continue
        w=$(echo "$geom" | grep -oP 'Geometry: \K[0-9]+')
        h=$(echo "$geom" | grep -oP 'x\K[0-9]+')
        area=$(( ${w:-0} * ${h:-0} ))
        if [ "$area" -gt "$best_area" ]; then
            best_area=$area
            best_wid=$wid
        fi
    done < <(DISPLAY=$DISP xdotool search --name "CIQ Simulator" 2>/dev/null)
    echo "$best_wid"
}

activate() {
    local w; w=$(win)
    [ -n "$w" ] && DISPLAY=$DISP xdotool windowactivate "$w" 2>/dev/null || true
}

press() {
    local w; w=$(win)
    [ -n "$w" ] && DISPLAY=$DISP xdotool key --window "$w" "$@" 2>/dev/null || true
}

screenshot() {
    local name="$1"
    local w; w=$(win)
    if [ -z "$w" ]; then
        echo "[e2e] WARN: no simulator window — skipping $name"
        return
    fi
    DISPLAY=$DISP import -window "$w" "${RESULTS}/${name}.png"
    echo "[e2e] Screenshot: ${name}.png"
}

start_mock() {
    local new_mode="$1"
    if [ -n "$MOCK_PID" ]; then
        kill "$MOCK_PID" 2>/dev/null || true
        sleep 1
    fi
    python3 "$APP_DIR/test/mock_server.py" --port "$PORT" --mode "$new_mode" &
    MOCK_PID=$!
    sleep 1
    echo "[e2e] Mock server PID=$MOCK_PID  mode=$new_mode"
}

load_app() {
    local prg="${1:-test-results/build/app.prg}"
    if [ -n "$APP_PID" ]; then
        kill "$APP_PID" 2>/dev/null || true
        sleep 1
    fi
    DISPLAY=$DISP timeout 30s monkeydo "$prg" "$DEVICE" &
    APP_PID=$!
    echo "[e2e] App loaded (PID=$APP_PID, prg=$prg)"
}

wait_for_http() {
    # Allow time for: app init + Communications.makeWebRequest + server response + onUpdate
    sleep 15
}

# ════════════════════════════════════════════════════════════════════════════
# Scenario A — Happy path: course list
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario A: course list (happy path) ─────────────────────"
start_mock normal
load_app
wait_for_http
activate

screenshot "01_course_list"

# Scroll down one item
press Down
sleep 1
screenshot "02_course_list_scrolled"

# Select the highlighted course (START/ENTER key)
press Return
sleep 15   # wait for course-points HTTP response
screenshot "03_navigating"

# ════════════════════════════════════════════════════════════════════════════
# Scenario B — Server error (HTTP 500)
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario B: server error ────────────────────────────────"
start_mock error
load_app
wait_for_http
activate
screenshot "04_error_state"

# ════════════════════════════════════════════════════════════════════════════
# Scenario C — Empty course list
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario C: empty courses ───────────────────────────────"
start_mock empty
load_app
wait_for_http
activate
screenshot "05_empty_courses"

# ════════════════════════════════════════════════════════════════════════════
# Scenario D — Signed out: OAuth sign-in prompt
# Recompile with an empty apiKey so no token is present at startup → the widget
# shows the "Sign in with Garmin" prompt instead of loading courses.
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario D: signed-out sign-in prompt ─────────────────────"
patch_api_key ""
compile_app test-results/build/app-signedout.prg
start_mock normal
load_app test-results/build/app-signedout.prg
wait_for_http
activate
screenshot "06_signed_out"

# Press START → begins the phone OAuth flow (no phone in CI, so it parks on the
# "Check your phone..." state); capture that transition.
press Return
sleep 3
screenshot "07_signing_in"

# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── All scenarios complete ──────────────────────────────────"
echo "[e2e] Screenshots:"
ls -la "$RESULTS/" || true
