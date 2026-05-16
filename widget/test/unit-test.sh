#!/usr/bin/env bash
# Unit-test runner for garmin-router-widget.
# Called from CI instead of the built-in tester.sh so we can fix issues
# without rebuilding the Docker image.
#
# Usage (inside container):
#   unit-test.sh [DEVICE] [CERT_PATH]

set -euo pipefail

DEVICE=${1:-edge530}
CERT=${2:-}

# ── Developer certificate ─────────────────────────────────────────────────────
if [ -z "$CERT" ] || [ ! -f "$CERT" ]; then
    CERT=/tmp/developer_key.der
    openssl genrsa -out /tmp/developer_key.pem 4096 2>/dev/null
    openssl pkcs8 -topk8 -inform PEM -outform DER \
        -in /tmp/developer_key.pem -out "$CERT" -nocrypt 2>/dev/null
fi

# ── Diagnostics ───────────────────────────────────────────────────────────────
echo "[unit] CONNECTIQ_HOME=${CONNECTIQ_HOME:-unset}"
echo "[unit] Device dir: $(ls /root/.Garmin/ConnectIQ/Devices/${DEVICE}/ 2>/dev/null | tr '\n' ' ')"
echo "[unit] SDK share: $(ls ${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share/ 2>/dev/null | tr '\n' ' ')"
echo "[unit] ~/.Garmin/ConnectIQ top-level: $(ls /root/.Garmin/ConnectIQ/ 2>/dev/null | tr '\n' ' ')"

# ── Compile unit tests ────────────────────────────────────────────────────────
echo "Compiling unit tests for ${DEVICE}..."
monkeyc \
    --warn \
    -f monkey.jungle \
    -d "$DEVICE" \
    -t \
    -o /tmp/unit-test.prg \
    -y "$CERT"

# ── Virtual display ───────────────────────────────────────────────────────────
echo "Running unit tests..."
Xvfb :99 -screen 0 1024x768x24 &
XVFB_PID=$!
export DISPLAY=:99
sleep 1

# ── Ensure simulator finds SDK share at the hardcoded ~/.Garmin path ──────────
# The simulator looks for share/simulator/ at ~/.Garmin/ConnectIQ/share/
# (hardcoded) in addition to CONNECTIQ_HOME. Without this symlink it hangs
# during startup and never opens its IPC socket.
if [ ! -e /root/.Garmin/ConnectIQ/share ]; then
    echo "[unit] Symlinking SDK share → ~/.Garmin/ConnectIQ/share"
    ln -s "${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share" /root/.Garmin/ConnectIQ/share
fi

# ── Start simulator ───────────────────────────────────────────────────────────
simulator &
SIM_PID=$!
trap "kill $SIM_PID $XVFB_PID 2>/dev/null; exit" INT TERM EXIT

# ── Wait for simulator IPC socket ─────────────────────────────────────────────
echo "Waiting for simulator socket..."
SOCKET_FOUND=false
for i in $(seq 1 30); do
    # Exclude X11 display sockets — only look for the CIQ IPC socket
    if ls /tmp/.ciq* 2>/dev/null | grep -q . || \
       find /tmp -maxdepth 2 -type s ! -path '/tmp/.X11-unix/*' 2>/dev/null | grep -q .; then
        echo "Simulator socket found after ${i}s"
        SOCKET_FOUND=true
        break
    fi
    if ! kill -0 "$SIM_PID" 2>/dev/null; then
        echo "ERROR: simulator exited prematurely"
        exit 1
    fi
    sleep 1
done

echo "Simulator process status: $(kill -0 $SIM_PID 2>/dev/null && echo running || echo dead)"
echo "Socket files: $(find /tmp -maxdepth 2 -type s ! -path '/tmp/.X11-unix/*' 2>/dev/null | tr '\n' ' ' || echo none)"

if [ "$SOCKET_FOUND" = false ]; then
    echo "WARNING: no CIQ socket found after 30s — attempting monkeydo anyway"
fi

# ── Run tests (60s timeout to avoid CI hangs) ─────────────────────────────────
# -t tells monkeydo to execute (:test) functions and exit with pass/fail;
# without it the app runs as a normal app and hangs forever.
timeout 60s monkeydo /tmp/unit-test.prg "$DEVICE" -t
