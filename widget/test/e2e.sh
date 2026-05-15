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
echo "[e2e] SDK device inventory:"
# monkeyc location → SDK root
MONKEYC_BIN=$(command -v monkeyc 2>/dev/null || true)
echo "[e2e]   monkeyc: ${MONKEYC_BIN:-not found}"
if [ -n "$MONKEYC_BIN" ]; then
    SDK_BIN=$(dirname "$(readlink -f "$MONKEYC_BIN")")
    SDK_ROOT=$(dirname "$SDK_BIN")
    echo "[e2e]   SDK root: $SDK_ROOT"
    echo "[e2e]   SDK root contents: $(ls "$SDK_ROOT" 2>/dev/null | tr '\n' ' ')"
fi
# Find device definitions by locating compiler.json files (one per device)
echo "[e2e]   compiler.json locations (first 10):"
find / -maxdepth 10 -name compiler.json 2>/dev/null | head -10 | while read -r f; do
    echo "[e2e]     $f"
done

# ── Python3 guard ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[e2e] python3 not found — installing..."
    apt-get update -qq && apt-get install -y --quiet python3 >/dev/null
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
monkeyc -f monkey.jungle -d "$DEVICE" \
    -o test-results/build/app.prg \
    -y "$CERT" -l 3
echo "[e2e] Compiled OK → test-results/build/app.prg"

# ── Start CIQ Simulator ──────────────────────────────────────────────────────
DISPLAY=$DISP simulator &
SIM_PID=$!
sleep 3   # wait for simulator to be ready

# ── Helpers ──────────────────────────────────────────────────────────────────
win() {
    DISPLAY=$DISP xdotool search --name "CIQ Simulator" 2>/dev/null | head -1 || true
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
    if [ -n "$APP_PID" ]; then
        kill "$APP_PID" 2>/dev/null || true
        sleep 1
    fi
    DISPLAY=$DISP timeout 30s monkeydo test-results/build/app.prg "$DEVICE" &
    APP_PID=$!
    echo "[e2e] App loaded (PID=$APP_PID)"
}

wait_for_http() {
    # Allow time for: app init + Communications.makeWebRequest + server response + onUpdate
    sleep 8
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
sleep 6   # wait for course-points HTTP response
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
echo "[e2e] ── All scenarios complete ──────────────────────────────────"
echo "[e2e] Screenshots:"
ls -la "$RESULTS/" || true
