#!/usr/bin/env python3
"""Mock backend for garmin-router-widget E2E tests.

Usage:
  python3 mock_server.py [--port PORT] [--mode normal|empty|error]

Modes:
  normal  - 3 courses + binary course-point payloads (default)
  empty   - 0 courses (triggers "No courses found" error state)
  error   - HTTP 500 on every request (triggers network error state)
"""

import base64
import json
import struct
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# ── Parse CLI args ──────────────────────────────────────────────────────────
port = 8765
mode = "normal"
i = 1
while i < len(sys.argv):
    if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
        port = int(sys.argv[i + 1])
        i += 2
    elif sys.argv[i] == "--mode" and i + 1 < len(sys.argv):
        mode = sys.argv[i + 1]
        i += 2
    else:
        i += 1

# ── Mock data ───────────────────────────────────────────────────────────────
COURSES = [
    {"id": "111222333", "name": "Morning Trail", "distanceKm": 12.3},
    {"id": "444555666", "name": "Lakeside Loop",  "distanceKm":  8.1},
    {"id": "777888999", "name": "Hill Climb",     "distanceKm":  5.7},
]


def _pack_points(pts):
    """Pack (lat, lon) pairs as big-endian int32 * 1e7."""
    buf = b""
    for lat, lon in pts:
        buf += struct.pack(">i", round(lat * 1e7))
        buf += struct.pack(">i", round(lon * 1e7))
    return buf


def _encode_points(pts):
    """ASCII85-encode packed course points for text/plain transport."""
    return base64.a85encode(_pack_points(pts), adobe=False).decode("ascii")


COURSE_POINTS = {
    "111222333": _encode_points([
        (60.1699, 24.9384), (60.1750, 24.9450), (60.1780, 24.9500),
    ]),
    "444555666": _encode_points([
        (60.1800, 25.0000), (60.1900, 25.0100),
    ]),
    "777888999": _encode_points([
        (60.2000, 25.0200), (60.2100, 25.0300), (60.2200, 25.0400),
    ]),
}


# ── Request handler ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[mock] {fmt % args}", flush=True)

    def do_GET(self):  # noqa: N802
        if mode == "error":
            self.send_response(500)
            self.end_headers()
            return

        path = urlparse(self.path).path

        if path == "/api/courses":
            courses = [] if mode == "empty" else COURSES
            body = json.dumps({"courses": courses}).encode()
            self._respond(200, "application/json", body)

        elif path.startswith("/api/course/"):
            course_id = path.split("/")[-1]
            encoded = COURSE_POINTS.get(course_id)
            if encoded:
                self._respond(200, "text/plain; charset=ascii", encoded.encode("ascii"))
            else:
                self.send_response(404)
                self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"[mock] Listening on http://127.0.0.1:{port}  mode={mode}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock] Stopped", flush=True)
