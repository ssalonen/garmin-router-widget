#!/usr/bin/env bash
set -euo pipefail

DEVICE=${1:-edge530}
CERT=${2:-}

if [ -z "$CERT" ] || [ ! -f "$CERT" ]; then
    CERT=/tmp/developer_key.der
    openssl genrsa -out /tmp/developer_key.pem 4096 2>/dev/null
    openssl pkcs8 -topk8 -inform PEM -outform DER \
        -in /tmp/developer_key.pem -out "$CERT" -nocrypt 2>/dev/null
fi

echo "Compiling unit tests for ${DEVICE}..."
echo "[diag] CONNECTIQ_HOME=${CONNECTIQ_HOME:-unset}"
echo "[diag] Device dir: $(ls /root/.Garmin/ConnectIQ/Devices/${DEVICE}/ 2>/dev/null | tr '\n' ' ')"
echo "[diag] SDK share: $(ls ${CONNECTIQ_HOME:-/opt/connectiq-sdk}/share/ 2>/dev/null | tr '\n' ' ')"
monkeyc \
    --warn \
    -f monkey.jungle \
    -d "$DEVICE" \
    -t \
    -o /tmp/unit-test.prg \
    -y "$CERT"

echo "Running unit tests..."
Xvfb :99 -screen 0 1024x768x24 &
XVFB_PID=$!
export DISPLAY=:99
sleep 1

simulator &
SIM_PID=$!
trap "kill $SIM_PID $XVFB_PID 2>/dev/null; exit" INT TERM EXIT

# Wait up to 20s for the simulator to create its communication socket.
echo "Waiting for simulator socket..."
for i in $(seq 1 20); do
    if ls /tmp/.ciq* /tmp/apple* 2>/dev/null | grep -q .; then
        echo "Simulator socket found after ${i}s"
        break
    fi
    # Also check if the simulator process already died
    if ! kill -0 "$SIM_PID" 2>/dev/null; then
        echo "ERROR: simulator exited prematurely"
        exit 1
    fi
    sleep 1
done
echo "Simulator process status: $(kill -0 $SIM_PID 2>/dev/null && echo running || echo dead)"
echo "Socket files: $(ls /tmp/.ciq* /tmp/apple* 2>/dev/null || echo none)"

monkeydo /tmp/unit-test.prg "$DEVICE"
