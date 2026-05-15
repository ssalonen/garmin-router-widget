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
trap "kill $XVFB_PID 2>/dev/null; exit" INT TERM EXIT
export DISPLAY=:99
sleep 1

monkeydo /tmp/unit-test.prg "$DEVICE"
