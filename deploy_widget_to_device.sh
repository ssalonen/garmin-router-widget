#!/usr/bin/env bash
# Copy a compiled widget.prg to a connected Garmin device.
#
# Refuses to copy a build that still has placeholder/dummy config baked in —
# i.e. widget/resources/settings/properties.xml's defaults (apiKey=change-me,
# backendUrl unset/example/mock) weren't actually overridden by the
# gitignored widget/resources/settings/properties_PROD.xml at build time.
#
# Usage:
#   deploy_widget_to_device.sh [PRG_PATH] [DEVICE_MOUNT]
#
#   PRG_PATH      Defaults to widget/bin/widget.prg
#   DEVICE_MOUNT  Defaults to auto-detected /run/media/*/GARMIN or /media/*/GARMIN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRG="${1:-$SCRIPT_DIR/widget/bin/widget.prg}"
DEVICE_ROOT="${2:-}"

if [ ! -f "$PRG" ]; then
    echo "error: $PRG not found — build it first, e.g.:" >&2
    echo "  (cd widget && monkeyc -f monkey.jungle -d edge530 -o bin/widget.prg -y developer_key -l 3)" >&2
    exit 1
fi

# ── Dummy-config guard ───────────────────────────────────────────────────────
# These strings only end up in the compiled binary if the placeholder
# properties.xml value made it into the build instead of being overridden by
# properties_PROD.xml.
DUMMY_PATTERNS=(
    "change-me"                # placeholder apiKey
    "your-server.example.com"  # placeholder backendUrl
    "127.0.0.1"                # e2e mock-server URL, should never end up in a real build
)

# Captured once into a variable rather than piped per-check: piping into
# `grep -q` races the producer against grep's early exit (SIGPIPE), which
# under `pipefail` can intermittently report failure even on a match.
prg_strings="$(strings "$PRG")"

PROD_PROPS="$SCRIPT_DIR/widget/resources/settings/properties_PROD.xml"

fail=0
for pattern in "${DUMMY_PATTERNS[@]}"; do
    if grep -qF "$pattern" <<< "$prg_strings"; then
        echo "error: $PRG still contains placeholder value '$pattern'" >&2
        fail=1
    fi
done

if ! grep -qE "^https://" <<< "$prg_strings"; then
    echo "error: $PRG has no https:// backendUrl baked in at all" >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo "" >&2
    if [ -f "$PROD_PROPS" ]; then
        echo "How to fix:" >&2
        echo "  1. Edit $PROD_PROPS and set real apiKey/backendUrl values" >&2
        echo "     (it exists but its values weren't picked up by this build — make sure it wasn't left empty/reverted)." >&2
        echo "  2. Rebuild, wiping cached resources so the edit actually takes effect:" >&2
        echo "       rm -rf widget/gen widget/internal-mir" >&2
        echo "       (cd widget && monkeyc -f monkey.jungle -d edge530 -o bin/widget.prg -y developer_key -l 3)" >&2
        echo "  3. Re-run this script." >&2
    else
        echo "How to fix:" >&2
        echo "  1. Create $PROD_PROPS (gitignored, never committed) with your real values:" >&2
        echo "       <properties>" >&2
        echo "           <property id=\"backendUrl\" type=\"string\">https://your-real-backend</property>" >&2
        echo "           <property id=\"apiKey\" type=\"string\">your-real-api-key</property>" >&2
        echo "       </properties>" >&2
        echo "  2. Rebuild:" >&2
        echo "       (cd widget && monkeyc -f monkey.jungle -d edge530 -o bin/widget.prg -y developer_key -l 3)" >&2
        echo "  3. Re-run this script." >&2
    fi
    exit 1
fi

echo "[deploy] $PRG has no dummy apiKey/backendUrl — OK"

# ── Locate the device ────────────────────────────────────────────────────────
if [ -z "$DEVICE_ROOT" ]; then
    for candidate in /run/media/*/GARMIN /media/*/GARMIN; do
        if [ -d "$candidate/Garmin/Apps" ]; then
            DEVICE_ROOT="$candidate"
            break
        fi
    done
fi

if [ -z "$DEVICE_ROOT" ] || [ ! -d "$DEVICE_ROOT/Garmin/Apps" ]; then
    echo "error: no Garmin device found — mount it, or pass the mount path as \$2" >&2
    exit 1
fi

# ── Copy ─────────────────────────────────────────────────────────────────────
DEST="$DEVICE_ROOT/Garmin/Apps/widget.prg"
cp -v "$PRG" "$DEST"
sync
echo "[deploy] copied to $DEST"

# Uninstalling via the device menu removes the .prg but leaves this file
# behind, so a reinstall silently reloads whatever config was baked into the
# *first-ever* sideload. Clear it so the fresh .prg's compiled defaults apply.
SETTINGS_FILE="$DEVICE_ROOT/Garmin/Apps/SETTINGS/widget.SET"
if [ -f "$SETTINGS_FILE" ]; then
    rm -v "$SETTINGS_FILE"
    sync
    echo "[deploy] cleared stale on-device settings ($SETTINGS_FILE) so compiled defaults take effect"
fi
