#!/usr/bin/env bash
# E2E screenshot tests for garmin-router-widget.
#
# Runs inside the connectiq-tester Docker container.  For each scenario it:
#   1. (Re-)starts mock_server.py in the appropriate mode
#   2. Loads the compiled widget in the CIQ simulator
#   3. Waits for the HTTP round-trip to complete
#   4. Clicks device frame buttons, captures screenshots, and asserts pixel colours
#
# Scenarios:
#   A  normal / navigate FIRST course  (Enter without Down)
#   B  normal / navigate SECOND course (Down → Enter)
#   C  error  / HTTP 500 → error state
#   D  empty  / empty list → "No courses found"
#   E  many   / 8 courses (2 pages of 5) → scroll to page 2
#
# Usage (inside container, called by CI):
#   e2e.sh [DEVICE] [CERT_PATH]
#
# Prerequisites already provided by the container image:
#   monkeyc, monkeydo, simulator, xdotool, imagemagick (import/convert), Xvfb, openssl

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
ASSERT_FAILED=false
CANVAS_WID=""   # innermost child X window of simulator (set by activate)
SIM_UP_X=""  SIM_UP_Y=""
SIM_DOWN_X="" SIM_DOWN_Y=""
_SIM_WARMED_UP=false   # skip the long first-load sleep on subsequent activate() calls

# Layout constants (must match CourseListView.mc)
LIST_TOP=26
ITEM_HEIGHT=30

mkdir -p "$RESULTS"

echo "[e2e] SDK devices: $(ls /root/.Garmin/ConnectIQ/Devices 2>/dev/null | tr '\n' ' ')"
echo "[e2e] CONNECTIQ_HOME=${CONNECTIQ_HOME:-unset}"

# Dump the edge530 simulator.json so button coordinate space is visible in CI logs.
echo "[e2e] All simulator.json files found:"
find /root/.Garmin/ConnectIQ /opt/connectiq-sdk /opt/garmin 2>/dev/null \
    -name "simulator.json" | head -20 || true
_sim_json=$(find /root/.Garmin/ConnectIQ /opt/connectiq-sdk /opt/garmin 2>/dev/null \
    -name "simulator.json" -path "*[Ee]dge*530*" | head -1 || true)
if [ -n "$_sim_json" ]; then
    echo "[e2e] simulator.json → $_sim_json"
    cat "$_sim_json"
else
    echo "[e2e] edge530 simulator.json not found"
fi

# ── Python3 guard ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[e2e] python3 not found — installing..."
    apt-get update -qq && apt-get install -y --quiet python3 >/dev/null
fi

# ── Ensure simulator finds SDK at the hardcoded ~/.Garmin/ConnectIQ path ─────
if [ ! -e /root/.Garmin/ConnectIQ/share ]; then
    echo "[e2e] Symlinking SDK share → ~/.Garmin/ConnectIQ/share"
    ln -s "${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share" /root/.Garmin/ConnectIQ/share
fi

echo "[e2e] ── Setup ──────────────────────────────────────────────────────"

# ── Copy widget source to a writable temp dir ────────────────────────────────
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

# ── Patch simulator.json: remove behavior from UP/DOWN buttons ───────────────
# edge530 simulator.json assigns behavior:"nextPage"/"previousPage" to the
# up/down buttons.  In the widget loop this triggers carousel navigation at the
# system level; with only one widget loaded the navigation attempt crashes the
# runtime (blue exception triangle) before any delegate code runs.
# Removing the behavior field makes the simulator silently ignore those button
# presses instead of crashing.  Scrolling via physical simulator buttons is
# therefore not exercised in CI; real-device button presses are unaffected
# (simulator.json is simulator-only).
python3 - <<'PYPATCH'
import json, sys, glob

paths = []
for p in [
    "/root/.Garmin/ConnectIQ/Devices/edge530/simulator.json",
    "/root/.Garmin/ConnectIQ/Devices/Edge530/simulator.json",
]:
    paths += glob.glob(p)
paths += glob.glob("/root/.Garmin/ConnectIQ/*530*/simulator.json")

if not paths:
    print("[e2e] WARNING: no edge530 simulator.json found — skipping patch", flush=True)
    sys.exit(0)

for path in paths:
    with open(path) as f:
        data = json.load(f)
    changed = []
    for key in data.get("keys", []):
        if key.get("id") in ("up", "down") and "behavior" in key:
            changed.append(key["id"])
            del key["behavior"]
    if changed:
        with open(path, "w") as f:
            json.dump(data, f)
        print(f"[e2e] Patched {path}: removed behavior from {changed}", flush=True)
    else:
        print(f"[e2e] {path}: up/down have no behavior field (already clean)", flush=True)
PYPATCH

# ── Start CIQ Simulator ──────────────────────────────────────────────────────
# Redirect simulator stdout so that Monkey C System.println() output is captured.
DISPLAY=$DISP simulator >"${RESULTS}/simulator.log" 2>&1 &
SIM_PID=$!
sleep 5   # wait for simulator to be ready

# ── Helpers ──────────────────────────────────────────────────────────────────
win() {
    # Pick the largest window named "CIQ Simulator" — avoids menu-bar sub-windows.
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
    if [ -z "$w" ]; then return; fi

    DISPLAY=$DISP xdotool windowactivate --sync "$w" 2>/dev/null || true
    sleep 0.3

    local geom ww wh
    geom=$(DISPLAY=$DISP xdotool getwindowgeometry "$w" 2>/dev/null) || geom=""
    ww=$(echo "$geom" | grep -oP 'Geometry: \K[0-9]+' 2>/dev/null || echo 446)
    wh=$(echo "$geom" | grep -oP 'Geometry: [0-9]+x\K[0-9]+' 2>/dev/null || echo 591)
    echo "[e2e] simulator window: ${ww}x${wh}"

    # On the very first load the simulator needs ~12 s to fully initialise.
    # Subsequent scenario loads only need a short pause (simulator already running).
    if [ "$_SIM_WARMED_UP" = "false" ]; then
        echo "[e2e] First activate — waiting 12 s for simulator warmup"
        sleep 12
        _SIM_WARMED_UP=true
    else
        echo "[e2e] Subsequent activate — waiting 3 s for app reload"
        sleep 3
    fi

    # Discover the canvas viewport window (used for screenshot cropping only).
    # Also log ALL child windows so the X11 tree is visible in CI logs.
    CANVAS_WID=""
    local best_area=99999999
    echo "[e2e] All simulator X11 windows (pid=$SIM_PID):"
    while IFS= read -r cw; do
        local cg cw_w cw_h carea
        cg=$(DISPLAY=$DISP xdotool getwindowgeometry "$cw" 2>/dev/null) || continue
        cw_w=$(echo "$cg" | grep -oP 'Geometry: \K[0-9]+' 2>/dev/null || echo 0)
        cw_h=$(echo "$cg" | grep -oP 'Geometry: [0-9]+x\K[0-9]+' 2>/dev/null || echo 0)
        local cpos
        cpos=$(echo "$cg" | grep -oP 'Position: \K[0-9,]+' 2>/dev/null || echo "?")
        echo "[e2e]   wid=$cw  pos=(${cpos})  geom=${cw_w}x${cw_h}$([ "$cw" = "$w" ] && echo " [MAIN]" || echo "")"
        [ "$cw" = "$w" ] && continue
        carea=$(( ${cw_w:-0} * ${cw_h:-0} ))
        if [ "$carea" -gt 100 ] && [ "$carea" -lt "$best_area" ]; then
            best_area=$carea
            CANVAS_WID=$cw
        fi
    done < <(DISPLAY=$DISP xdotool search --pid "$SIM_PID" 2>/dev/null)
    if [ -n "$CANVAS_WID" ]; then
        local _cwg
        _cwg=$(DISPLAY=$DISP xdotool getwindowgeometry "$CANVAS_WID" 2>/dev/null) || _cwg="?"
        echo "[e2e] canvas (smallest child) wid=$CANVAS_WID  $_cwg"
    else
        echo "[e2e] no canvas child found"
    fi

    # Save full-window snapshot (used for button position visualisation).
    DISPLAY=$DISP import -window "$w" "${RESULTS}/diag_window_full.png" 2>/dev/null || true

    # Print pixel colours at known button positions and scan the left-side frame
    # to identify where UP/DOWN button bumps actually are.
    if [ -f "${RESULTS}/diag_window_full.png" ]; then
        for _pentry in "337,182:SELECT" "23,297:UP_+20" "23,277:UP_raw" "23,377:DOWN_+20" "23,357:DOWN_raw" "337,377:BACK"; do
            _ppx="${_pentry%%:*}"; _ppl="${_pentry##*:}"
            _ppxv=$(convert "${RESULTS}/diag_window_full.png" \
                -crop "1x1+$(echo "$_ppx"|cut -d, -f1)+$(echo "$_ppx"|cut -d, -f2)" \
                +repage txt:- 2>/dev/null \
                | grep -oP '#[0-9A-Fa-f]{6}' | head -1) || _ppxv="?"
            echo "[e2e] pixel@${_ppl}(${_ppx})=${_ppxv}"
        done
        # Scan left-side (x=23) from y=200 to y=480 in 10px steps to locate bumps.
        echo -n "[e2e] left-side scan (x=23):"
        for _sy in 200 210 220 230 240 250 260 270 280 290 300 310 320 330 340 350 360 370 380 390 400 410 420 430 440 450 460 470 480; do
            _sc=$(convert "${RESULTS}/diag_window_full.png" \
                -crop "1x1+23+${_sy}" +repage txt:- 2>/dev/null \
                | grep -oP '#[0-9A-Fa-f]{6}' | head -1) || _sc="?"
            printf " y%d=%s" "${_sy}" "${_sc}"
        done
        echo ""
    fi

    # Set button click positions (window-relative pixels, set once).
    # For edge530: hardcoded from reference screenshot with manually placed green
    # dot markers at each physical button bump (run detect_green_dots.py to recalibrate).
    #
    # Edge 530 button layout (window-relative coords from calibration image):
    #   Left  upper  (22, 300)  = UP
    #   Left  lower  (24, 382)  = DOWN
    #   Right upper  (337,182)  = ACKNOWLEDGE / SELECT
    #   Right lower  (338,380)  = BACK
    #   Bottom left  (82, 538)  = LAP
    #   Bottom right (276,540)  = START / GO
    if [ -z "${SIM_DOWN_X}" ]; then
        case "$DEVICE" in
            edge530)
                # Coordinates from simulator.json + 20px Y offset.
                # The simulator window has a ~20px Qt toolbar above the frame
                # image, so all frame image Y coordinates need +20 to get the
                # actual window pixel coordinate.
                # JSON enter: x=329,y=130,w=16,h=65 → frame center (337,162) → window (337,182) ✓
                # JSON up:    x=14, y=250,w=18,h=55 → frame center (23,277)  → window (23,297)
                # JSON down:  x=14, y=330,w=18,h=55 → frame center (23,357)  → window (23,377)
                SIM_UP_X=23;   SIM_UP_Y=297
                SIM_DOWN_X=23; SIM_DOWN_Y=377
                ;;
            *)
                # Dynamic brightness-peak detection for unknown devices.
                local _rx=0 _ry=0 _cw_w="${ww:-200}" _cw_h="${wh:-200}"
                if [ -n "$CANVAS_WID" ]; then
                    local _cg _cpos _wpos
                    _cg=$(DISPLAY=$DISP xdotool getwindowgeometry "$CANVAS_WID" 2>/dev/null) || _cg=""
                    _cpos=$(echo "$_cg" | grep -oP 'Position: \K[0-9,]+' 2>/dev/null) || _cpos="0,0"
                    _wpos=$(DISPLAY=$DISP xdotool getwindowgeometry "$w" 2>/dev/null \
                            | grep -oP 'Position: \K[0-9,]+' 2>/dev/null) || _wpos="0,0"
                    _rx=$(( $(echo "$_cpos"|cut -d, -f1) - $(echo "$_wpos"|cut -d, -f1) ))
                    _ry=$(( $(echo "$_cpos"|cut -d, -f2) - $(echo "$_wpos"|cut -d, -f2) ))
                    _cw_w=$(echo "$_cg" | grep -oP 'Geometry: \K[0-9]+' 2>/dev/null || echo 200)
                    _cw_h=$(echo "$_cg" | grep -oP 'Geometry: [0-9]+x\K[0-9]+' 2>/dev/null || echo 200)
                fi
                local _detect_out
                _detect_out=$(python3 "$APP_DIR/test/detect_buttons.py" \
                    "${RESULTS}/diag_window_full.png" \
                    "${_rx}" "${_ry}" "${_cw_w}" "${_cw_h}" \
                    2>"${RESULTS}/detect_buttons.log") || true
                echo "$_detect_out" >> "${RESULTS}/detect_buttons.log"
                eval "$( echo "$_detect_out" | grep '^SIM_' )" 2>/dev/null || true
                ;;
        esac

        echo "[e2e] ── Button positions: UP=(${SIM_UP_X:-?},${SIM_UP_Y:-?})  DOWN=(${SIM_DOWN_X:-?},${SIM_DOWN_Y:-?}) ──"

        # Annotate the full-window snapshot with all button crosshairs and the
        # device-screen bounding box.  Colours per button role:
        #   Blue   = UP (left upper)       Red    = DOWN (left lower)
        #   Yellow = SELECT/ACK (right u.) Magenta= BACK (right lower)
        #   Green  = START/GO (bottom R)   Orange = LAP (bottom L)
        # Cyan rect = device screen; the triangle-check region is in CROPPED
        # coordinates, so it is not drawn here.
        if [ -f "${RESULTS}/diag_window_full.png" ]; then
            local ux="${SIM_UP_X:-22}"   uy="${SIM_UP_Y:-300}"
            local dx="${SIM_DOWN_X:-338}" dy="${SIM_DOWN_Y:-380}"
            convert "${RESULTS}/diag_window_full.png" \
                -strokewidth 1 -fill none -stroke '#00ffcc' \
                -draw "rectangle 60,100 340,475" \
                -strokewidth 2 -fill none -stroke '#4499ff' \
                -draw "circle ${ux},${uy} $((ux+10)),${uy}" \
                -draw "line $((ux-14)),${uy} $((ux+14)),${uy}" \
                -draw "line ${ux},$((uy-14)) ${ux},$((uy+14))" \
                -strokewidth 2 -fill none -stroke '#ff4444' \
                -draw "circle ${dx},${dy} $((dx+10)),${dy}" \
                -draw "line $((dx-14)),${dy} $((dx+14)),${dy}" \
                -draw "line ${dx},$((dy-14)) ${dx},$((dy+14))" \
                -strokewidth 2 -fill none -stroke '#ffee00' \
                -draw "circle 337,182 347,182" \
                -draw "line 323,182 351,182" \
                -draw "line 337,168 337,196" \
                -strokewidth 2 -fill none -stroke '#ff44ff' \
                -draw "circle 338,380 348,380" \
                -draw "line 324,380 352,380" \
                -draw "line 338,366 338,394" \
                -strokewidth 2 -fill none -stroke '#00ff88' \
                -draw "circle 276,540 286,540" \
                -draw "line 262,540 290,540" \
                -draw "line 276,526 276,554" \
                -strokewidth 2 -fill none -stroke '#ff8800' \
                -draw "circle 82,538 92,538" \
                -draw "line 68,538 96,538" \
                -draw "line 82,524 82,552" \
                "${RESULTS}/00_button_positions.png" 2>/dev/null && \
                echo "[e2e] Button positions image → 00_button_positions.png" || true
        fi
    fi
}

press() {
    local w; w=$(win)
    echo "[e2e] keypress: $* (wid=$w)"
    DISPLAY=$DISP xdotool windowfocus "$w" key --clearmodifiers "$@" 2>/dev/null || true
}

# _click_button X Y
# Click at absolute screen coordinates using XTest (spontaneous events).
# In Xvfb with no window manager the simulator window is always at (0,0), so
# window-relative coords from simulator.json equal absolute screen coords.
# windowfocus is irrelevant for mouse clicks — XTest delivers them to whatever
# window is under the cursor, not the focused window.
_click_button() {
    local abs_x="$1" abs_y="$2"
    echo "[e2e]   click abs=(${abs_x},${abs_y})"
    DISPLAY=$DISP xdotool mousemove --sync "$abs_x" "$abs_y" \
        click --clearmodifiers 1 2>/dev/null || true
}

# enter_widget — click SELECT to transition the widget from carousel-browsing
# mode to full-view mode.  Must be called before any scroll Down/Up clicks.
#
# In full-view mode, behavior:"nextPage"/"previousPage" on UP/DOWN calls
# onNextPage()/onPreviousPage() on the delegate (our scrollDown/scrollUp).
# In carousel mode the same behavior crashes with a single widget loaded
# (the simulator tries to navigate to a nonexistent second widget).
#
# KEY_ENTER (SELECT) is intentionally unmapped in our Monkey C code so this
# click is always a no-op at the app level — it is safe to call at any time,
# before or after the HTTP response.
enter_widget() {
    case "$DEVICE" in
        edge530)
            echo "[e2e] enter_widget → click SELECT (337,182) during LOADING"
            _click_button 337 182
            ;;
        *)
            local w; w=$(win)
            echo "[e2e] enter_widget → key Return"
            DISPLAY=$DISP xdotool windowfocus "$w" key --clearmodifiers Return 2>/dev/null || true
            ;;
    esac
    sleep 1
}

# select_course — click SELECT a second time (after enter_widget already
# transitioned the widget from the carousel to full-view mode).
# behavior:"onSelect" generates KEY_ENTER via onKey().  enter_widget fires the
# first click while the app is still in STATE_LOADING_LIST (mock delay ensures
# this), so the KEY_ENTER there is a no-op.  By the time select_course is
# called the HTTP response has arrived and state is STATE_LIST_READY, so
# KEY_ENTER triggers selectCourse().
# On real Edge devices the carousel-entry SELECT is consumed by the system and
# never forwarded to onKey(), so KEY_ENTER → selectCourse() is safe there too.
select_course() {
    case "$DEVICE" in
        edge530)
            echo "[e2e] select_course → click SELECT (337,182)"
            _click_button 337 182
            ;;
        *)
            local w; w=$(win)
            echo "[e2e] select_course → key Return"
            DISPLAY=$DISP xdotool windowfocus "$w" key --clearmodifiers Return 2>/dev/null || true
            ;;
    esac
    sleep 0.2
}

scroll() {
    local dir="$1"

    # Physical button click on the device frame — routes through simulator.json
    # behavior dispatch.  In full-view mode (after enter_widget), behavior:
    # "nextPage" calls onNextPage() → scrollDown(), and "previousPage" calls
    # onPreviousPage() → scrollUp().  enter_widget() must be called first to
    # transition the widget from carousel mode to full-view mode; otherwise
    # behavior:"nextPage" crashes (single-widget carousel navigation).
    if [ "$dir" = "Down" ] && [ -n "${SIM_DOWN_X}" ] && [ -n "${SIM_DOWN_Y}" ]; then
        echo "[e2e] scroll Down → click (${SIM_DOWN_X},${SIM_DOWN_Y})"
        _click_button "${SIM_DOWN_X}" "${SIM_DOWN_Y}"
        sleep 0.2
        return
    fi
    if [ "$dir" = "Up" ] && [ -n "${SIM_UP_X}" ] && [ -n "${SIM_UP_Y}" ]; then
        echo "[e2e] scroll Up → click (${SIM_UP_X},${SIM_UP_Y})"
        _click_button "${SIM_UP_X}" "${SIM_UP_Y}"
        sleep 0.2
        return
    fi

    local w; w=$(win)
    echo "[e2e] scroll $dir → key fallback (no button coords for $DEVICE)"
    DISPLAY=$DISP xdotool windowfocus "$w" key --clearmodifiers "$dir" 2>/dev/null || true
    sleep 0.2
}

screenshot() {
    local name="$1"
    local w; w=$(win)
    if [ -z "$w" ]; then
        echo "[e2e] WARN: no simulator window — skipping $name"
        return
    fi

    # Crop the device-screen region from the simulator window and resize it to
    # the device's native resolution so Monkey C drawing coords (LIST_TOP=26,
    # ITEM_HEIGHT=30, etc.) map 1:1 onto image pixels.
    case "$DEVICE" in
        edge530)
            # edge530 device screen lives at (60,100) sized 280x375 in the 446x591
            # simulator window. Resize to native 246x322.
            DISPLAY=$DISP import -window "$w" \
                -crop "280x375+60+100" +repage \
                -resize "246x322!" \
                "${RESULTS}/${name}.png"
            ;;
        *)
            DISPLAY=$DISP import -window "$w" "${RESULTS}/${name}.png"
            ;;
    esac
    echo "[e2e] Screenshot: ${name}.png"
}

start_mock() {
    local new_mode="$1"
    local new_delay="${2:-0}"
    if [ -n "$MOCK_PID" ]; then
        kill "$MOCK_PID" 2>/dev/null || true
        sleep 1
    fi
    python3 "$APP_DIR/test/mock_server.py" --port "$PORT" --mode "$new_mode" --delay "$new_delay" &
    MOCK_PID=$!
    sleep 1
    echo "[e2e] Mock server PID=$MOCK_PID  mode=$new_mode  delay=${new_delay}s"
}

load_app() {
    local label="${1:-}"
    if [ -n "$APP_PID" ]; then
        kill "$APP_PID" 2>/dev/null || true
        sleep 1
    fi
    # Mark scenario boundary in the log so Monkey C println output is easy to attribute.
    printf '\n[e2e] ══ load_app %s ══\n' "${label:-?}" >> "${RESULTS}/simulator.log"
    # monkeydo stdout also carries some runtime messages; append to same log.
    # 300 s timeout: each scenario needs ~18-50 s; 30 s was too short and caused
    # monkeydo to drop the simulator connection mid-test, producing false crash triangles.
    DISPLAY=$DISP timeout 300s monkeydo test-results/build/app.prg "$DEVICE" \
        >>"${RESULTS}/simulator.log" 2>&1 &
    APP_PID=$!
    echo "[e2e] App loaded (PID=$APP_PID) — Monkey C log → ${RESULTS}/simulator.log"
}

wait_for_http() {
    # Allow time for: app init + Communications.makeWebRequest + server response + onUpdate
    sleep 15
}

# ── Pixel-level screenshot assertions ────────────────────────────────────────
#
# Garmin colour constants used in CourseListView.mc:
#   COLOR_BLUE  = #0000FF  (selected row fill via fillRectangle)
#   COLOR_GREEN = #00FF00  (navigating state text)
#   COLOR_RED   = #FF0000  (error state text)
#
# Row layout (from CourseListView.mc constants):
#   Row i top = LIST_TOP + i * ITEM_HEIGHT  (LIST_TOP=26, ITEM_HEIGHT=30)
#
# Why relative comparison for blue rows:
#   The simulator window chrome contributes a constant ~900 blue pixels to the
#   row-1 region and ~3500 to the row-0 region in every screenshot (edge530
#   simulator has blue UI chrome that overlaps these y-coordinates).  A simple
#   "has N blue px" test is not discriminating enough.  Instead we compare the
#   selected row against an adjacent unselected row: the fill adds ~2600 extra
#   blue pixels, so selected ≈ 3–4× the unselected count.  Threshold: 2×.

# _count_color NAME X1 Y1 X2 Y2 COLOR → stdout count
_count_color() {
    local name="$1" x1="$2" y1="$3" x2="$4" y2="$5" color="$6"
    local file="${RESULTS}/${name}.png"
    [ -f "$file" ] || { echo 0; return; }
    local w=$((x2-x1)) h=$((y2-y1))
    convert "$file" \
        -crop "${w}x${h}+${x1}+${y1}" +repage \
        -fuzz 25% -fill white -opaque "$color" \
        -fill black +opaque white \
        -format "%[fx:int(mean*w*h+0.5)]" info: 2>/dev/null || echo 0
}

# assert_row_selected NAME SEL_ROW REF_ROW LABEL
#   Asserts that SEL_ROW has ≥2× the blue pixel count of REF_ROW.
assert_row_selected() {
    local name="$1" sel_row="$2" ref_row="$3" label="${4:-}"
    local sel_y1=$((LIST_TOP + sel_row * ITEM_HEIGHT + 1))
    local sel_y2=$((sel_y1 + ITEM_HEIGHT - 2))
    local ref_y1=$((LIST_TOP + ref_row * ITEM_HEIGHT + 1))
    local ref_y2=$((ref_y1 + ITEM_HEIGHT - 2))

    local sel_count ref_count
    sel_count=$(_count_color "$name" 10 "$sel_y1" 190 "$sel_y2" "blue")
    ref_count=$(_count_color "$name" 10 "$ref_y1" 190 "$ref_y2" "blue")

    local threshold=$(( ref_count * 2 ))
    if [ "${sel_count:-0}" -gt "$threshold" ]; then
        echo "[assert] PASS '$label' — row${sel_row}=${sel_count} >> row${ref_row}=${ref_count} (threshold ${threshold}) blue px"
    else
        echo "[assert] FAIL '$label' — row${sel_row}=${sel_count} not >> row${ref_row}=${ref_count} (threshold ${threshold})"
        local sc=$(( (10+190)/2 )) sy=$(( (sel_y1+sel_y2)/2 ))
        local rc=$(( (10+190)/2 )) ry=$(( (ref_y1+ref_y2)/2 ))
        local sp rp
        sp=$(convert "${RESULTS}/${name}.png" -crop "1x1+${sc}+${sy}" +repage txt:- 2>/dev/null | tail -1) || sp="?"
        rp=$(convert "${RESULTS}/${name}.png" -crop "1x1+${rc}+${ry}" +repage txt:- 2>/dev/null | tail -1) || rp="?"
        echo "[assert]   sel   centre (${sc},${sy}): ${sp}"
        echo "[assert]   ref   centre (${rc},${ry}): ${rp}"
        ASSERT_FAILED=true
    fi
}

# assert_has_color NAME X1 Y1 X2 Y2 COLOR LABEL [MIN_COUNT]
#   Sets ASSERT_FAILED if the pixel count for COLOR in [X1,Y1→X2,Y2] is below
#   MIN_COUNT (default 1).  Use MIN_COUNT > 1 to reject false positives: the
#   device-frame chrome in the screenshot crop can produce ~499 near-green
#   pixels even when no green app content is present, so navigating-state
#   assertions require ≥600 to distinguish real green text from that noise.
assert_has_color() {
    local name="$1" x1="$2" y1="$3" x2="$4" y2="$5" color="$6" label="${7:-}" min_count="${8:-1}"
    local count
    count=$(_count_color "$name" "$x1" "$y1" "$x2" "$y2" "$color")
    if [ "${count:-0}" -ge "$min_count" ]; then
        echo "[assert] PASS '$label' — ${count} ${color} px in ${name} [${x1},${y1}→${x2},${y2}] (≥${min_count})"
    else
        echo "[assert] FAIL '$label' — ${count:-0} ${color} px in ${name} at [${x1},${y1}→${x2},${y2}] (need ≥${min_count})"
        local cx=$(( (x1+x2)/2 )) cy=$(( (y1+y2)/2 ))
        local px
        px=$(convert "${RESULTS}/${name}.png" -crop "1x1+${cx}+${cy}" +repage txt:- 2>/dev/null | tail -1) || px="?"
        echo "[assert]   centre pixel (${cx},${cy}): ${px}"
        ASSERT_FAILED=true
    fi
}

# assert_no_error_triangle NAME LABEL
#   Detects the Monkey C exception screen (large blue triangle).
#   Region: native (60,120)-(190,200) — below the list rows (y=26-176) but
#   inside where the triangle apex sits in 246x322 device coords.
#   Threshold 70: observed counts — no-triangle: 0-44 px; triangle: 101 px.
#   Always writes NAME_tricheck.png annotating the checked region.
assert_no_error_triangle() {
    local name="$1" label="${2:-}"
    local file="${RESULTS}/${name}.png"
    local count=0
    if [ -f "$file" ]; then
        count=$(_count_color "$name" 60 120 190 200 "blue")
        # Annotate a copy of the screenshot with the checked region outlined
        convert "$file" \
            -strokewidth 2 -fill '#0000ff22' -stroke '#00ccff' \
            -draw "rectangle 60,120 190,200" \
            "${RESULTS}/${name}_tricheck.png" 2>/dev/null || true
    fi
    if [ "${count:-0}" -lt 70 ]; then
        echo "[assert] PASS '$label' — no exception triangle (${count} blue px in (60,120)-(190,200))"
    else
        echo "[assert] FAIL '$label' — exception triangle detected (${count} blue px in (60,120)-(190,200))"
        ASSERT_FAILED=true
    fi
}

# assert_screenshots_differ NAME1 NAME2 LABEL
#   Fails when the two screenshots look the same (UI did not visually change).
assert_screenshots_differ() {
    local name1="$1" name2="$2" label="${3:-}"
    local f1="${RESULTS}/${name1}.png" f2="${RESULTS}/${name2}.png"
    if [ ! -f "$f1" ] || [ ! -f "$f2" ]; then
        echo "[assert] FAIL '$label' — one or both screenshots missing (${name1}, ${name2})"
        ASSERT_FAILED=true
        return
    fi
    local diff
    diff=$(convert "$f1" "$f2" -metric AE -fuzz 5% -compare -format "%[distortion]" info: 2>/dev/null) || diff=0
    if [ "${diff:-0}" -gt 500 ]; then
        echo "[assert] PASS '$label' — screenshots differ by ${diff} px"
    else
        echo "[assert] FAIL '$label' — screenshots look the same (diff=${diff} px ≤ 500)"
        ASSERT_FAILED=true
    fi
}

# ════════════════════════════════════════════════════════════════════════════
# Scenario A — Happy path: navigate to first course (no scroll)
# ════════════════════════════════════════════════════════════════════════════
# Mock delay (15 s) ensures the HTTP response hasn't arrived yet when
# enter_widget fires its SELECT click, so KEY_ENTER is a no-op at that point
# (selectCourse() guards on STATE_LIST_READY).  After wait_for_http the list
# is loaded and the second SELECT click (select_course) triggers navigation.
echo "[e2e] ── Scenario A: navigate first course ───────────────────────"
start_mock normal 15
load_app A
activate
enter_widget    # SELECT click while still in STATE_LOADING_LIST — no-op at app level
wait_for_http   # HTTP response arrives during this sleep; state → LIST_READY

screenshot "01_course_list"
assert_no_error_triangle "01_course_list" "01: no exception"
assert_row_selected "01_course_list" 0 1 "row0 is highlighted on initial load"

select_course   # second SELECT click → KEY_ENTER → selectCourse()
sleep 20
screenshot "02_navigating_first"
assert_no_error_triangle "02_navigating_first" "02: no exception"
# The resize from 280x375→246x322 darkens the pure #00FF00 text to ~#00B700 (28%
# channel shift), which is just outside the 25% fuzz window.  Observed count is
# ~442 px.  Threshold of 200 gives headroom while staying above any chrome noise.
assert_has_color "02_navigating_first" 20 62 180 92 "#00FF00" "navigating state shows green text" 200

# ════════════════════════════════════════════════════════════════════════════
# Scenario B — Scroll attempt + navigate
# Note: physical simulator DOWN button clicks do not generate scroll events in
# the simulator (behavior removed by PYPATCH to prevent carousel crash).
# The DOWN clicks here verify no-crash behaviour; actual row selection is not
# asserted since the simulator cannot scroll.
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario B: scroll attempt, navigate ───────────────────"
start_mock normal 15
load_app B
activate
enter_widget
wait_for_http

scroll Down
sleep 1
screenshot "03_course_list_after_down"
assert_no_error_triangle "03_course_list_after_down" "03: no exception after Down"

select_course
sleep 20
screenshot "04_navigating"
assert_no_error_triangle "04_navigating" "04: no exception"
assert_has_color "04_navigating" 20 62 180 92 "#00FF00" "navigating state shows green text" 200

# ════════════════════════════════════════════════════════════════════════════
# Scenario C — Server error (HTTP 500)
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario C: server error ────────────────────────────────"
start_mock error 15
load_app C
activate
enter_widget
wait_for_http
screenshot "05_error_state"
assert_no_error_triangle "05_error_state" "05: no exception"
assert_has_color "05_error_state" 20 62 180 90 "#FF0000" "error state shows red text"

# ════════════════════════════════════════════════════════════════════════════
# Scenario D — Empty course list
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario D: empty courses ───────────────────────────────"
start_mock empty 15
load_app D
activate
enter_widget
wait_for_http
screenshot "06_empty_courses"
assert_no_error_triangle "06_empty_courses" "06: no exception"
assert_has_color "06_empty_courses" 20 62 180 90 "#FF0000" "empty list shows error state with red text"

# ════════════════════════════════════════════════════════════════════════════
# Scenario E — 8 courses: two pages (LIST_ROWS = 5)
# Note: DOWN clicks do not scroll in the simulator (PYPATCH removes behavior).
# The test verifies no-crash and that the first page renders correctly.
# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── Scenario E: multi-page course list (8 courses) ─────────"
start_mock many 15
load_app E
activate
enter_widget
wait_for_http

screenshot "07_multipage_p1"
assert_no_error_triangle "07_multipage_p1" "07: no exception"
assert_row_selected "07_multipage_p1" 0 1 "multipage p1: row0 highlighted"

# Five Down clicks — no-ops in simulator (PYPATCH), but must not crash.
for n in 1 2 3 4 5; do
    scroll Down
    sleep 0.4
done
sleep 1
screenshot "08_multipage_after_downs"
assert_no_error_triangle "08_multipage_after_downs" "08: no exception after 5 Downs"

# ════════════════════════════════════════════════════════════════════════════
echo "[e2e] ── All scenarios complete ──────────────────────────────────"

# Dump Monkey C / simulator log so it appears in the HTML report via run.log.
# System.println() calls in the Monkey C app go to the simulator process's stdout
# which was redirected to simulator.log; monkeydo also appends its own output there.
echo "[e2e] ── Monkey C / simulator log ────────────────────────────────"
if [ -f "${RESULTS}/simulator.log" ]; then
    cat "${RESULTS}/simulator.log"
else
    echo "[e2e] (simulator.log not found — no Monkey C output captured)"
fi
echo "[e2e] ── end simulator log ─────────────────────────────────────"

if [ "$ASSERT_FAILED" = "true" ]; then
    echo "[e2e] FAIL: One or more pixel assertions failed — see above for details"
    exit 1
fi
echo "[e2e] PASS: All pixel assertions passed"
