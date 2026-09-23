#!/usr/bin/env bash
# Run the widget's Docker-based checks locally, the same way CI does.
#
# The Connect IQ SDK cannot be installed on a normal machine (license +
# device profiles + a headless simulator), so CI builds a Docker image with
# it baked in (.github/docker/connectiq-builder.Dockerfile, published to
# ghcr.io/ssalonen/garmin-router-widget/connectiq-builder) and runs every
# widget check inside it. This script runs the exact same containers.
#
# Usage:
#   ./dev.sh unit [DEVICE]          # Monkey C unit tests (default device: edge530)
#   ./dev.sh e2e  [DEVICE]          # E2E screenshot tests against a mock backend
#   ./dev.sh backend                # Python backend tests (uv, no Docker needed)
#
# First time, or if ghcr.io/.../connectiq-builder is private to you:
#   gh auth refresh -h github.com -s read:packages
#   gh auth token | docker login ghcr.io -u <your-github-user> --password-stdin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CIQ_IMAGE="ghcr.io/ssalonen/garmin-router-widget/connectiq-builder:9.1.0"

cmd="${1:-}"
device="${2:-edge530}"

case "$cmd" in
    unit)
        docker run --rm \
            -v "$SCRIPT_DIR/widget:/app" \
            --workdir /app \
            -e CONNECTIQ_HOME=/opt/connectiq-sdk \
            --entrypoint /bin/bash \
            "$CIQ_IMAGE" \
            /app/test/unit-test.sh "$device"
        ;;
    e2e)
        mkdir -p "$SCRIPT_DIR/widget/test-results/e2e"
        docker run --rm \
            -v "$SCRIPT_DIR/widget:/app" \
            -v "$SCRIPT_DIR/backend:/backend:ro" \
            --workdir /app \
            -e CONNECTIQ_HOME=/opt/connectiq-sdk \
            --entrypoint /bin/bash \
            "$CIQ_IMAGE" \
            /app/test/e2e.sh "$device" "" 2>&1 | tee "$SCRIPT_DIR/widget/test-results/e2e/run.log"
        exit "${PIPESTATUS[0]}"
        ;;
    backend)
        (cd "$SCRIPT_DIR/backend" && uv run --group dev pytest -v --tb=short)
        ;;
    *)
        echo "usage: $0 {unit|e2e|backend} [device]" >&2
        exit 1
        ;;
esac
