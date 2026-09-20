#!/usr/bin/env python3
"""Mock backend for garmin-router-widget E2E tests.

Usage:
  python3 mock_server.py [--port PORT] [--mode MODE] [--delay SECS]

Modes:
  normal   - 3 courses; /api/course/{id} serves a lean FIT course (default)
  full     - as normal, but FIT records carry timestamp+distance (17 B/pt)
  corrupt  - as normal, but the FIT body is deliberately damaged. The control
             case: a device that stores this is not validating anything, so
             the positive results would mean nothing.
  many     - 8 courses (two screenfuls of 5 rows each)
  empty    - 0 courses (triggers "No courses found" error state)
  error    - HTTP 500 on every request (triggers network error state)

--delay SECS
  Add an artificial delay (float, seconds) before responding to /api/courses
  and HTTP-500 error responses.  Used in e2e tests to ensure the widget is
  still in STATE_LOADING_LIST when the SELECT (enter_widget) click fires,
  which prevents KEY_ENTER from triggering selectCourse() prematurely.
  Course requests (/api/course/{id}) are NOT delayed so that the
  download screenshot still completes within the existing sleep.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Import the backend's real FIT encoder rather than reimplementing it: the
# point of the FIT scenarios is to prove the bytes the backend would actually
# send are the bytes the device accepts.  In the repo it sits at ../../backend;
# in the test container widget/ is mounted at /app and backend/ at /backend.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, "..", "..", "backend"), "/backend"):
    if os.path.isfile(os.path.join(_cand, "fit.py")):
        sys.path.insert(0, _cand)
        break
import fit  # noqa: E402

# ── Parse CLI args ──────────────────────────────────────────────────────────
port = 8765
mode = "normal"
delay = 0.0
i = 1
while i < len(sys.argv):
    if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
        port = int(sys.argv[i + 1])
        i += 2
    elif sys.argv[i] == "--mode" and i + 1 < len(sys.argv):
        mode = sys.argv[i + 1]
        i += 2
    elif sys.argv[i] == "--delay" and i + 1 < len(sys.argv):
        delay = float(sys.argv[i + 1])
        i += 2
    else:
        i += 1

# ── Course catalogue ────────────────────────────────────────────────────────
# 3-course set (normal mode) + 5 additional (many mode)

COURSES_NORMAL = [
    {"id": "111222333", "name": "Morning Trail",  "distanceKm": 12.3},
    {"id": "444555666", "name": "Lakeside Loop",  "distanceKm":  8.1},
    {"id": "777888999", "name": "Hill Climb",      "distanceKm":  5.7},
]

COURSES_EXTRA = [
    {"id": "101010101", "name": "Mountain Ridge",  "distanceKm": 18.4},
    {"id": "202020202", "name": "Forest Trail",    "distanceKm":  9.2},
    {"id": "303030303", "name": "Coastal Path",    "distanceKm": 14.6},
    {"id": "404040404", "name": "River Loop",      "distanceKm":  7.8},
    {"id": "505050505", "name": "Summit Run",      "distanceKm": 22.1},
]

COURSES_MANY = COURSES_NORMAL + COURSES_EXTRA  # 8 total → 2 pages of 5

# Raw (lat, lon) per course — the FIT bodies are generated from this.
COURSE_LATLON = {
    # Page 1 courses
    "111222333": [(60.1699, 24.9384), (60.1750, 24.9450), (60.1780, 24.9500)],
    "444555666": [(60.1800, 25.0000), (60.1900, 25.0100)],
    "777888999": [(60.2000, 25.0200), (60.2100, 25.0300), (60.2200, 25.0400)],
    "101010101": [(61.4978, 23.7610), (61.5100, 23.7800), (61.5200, 23.8000)],
    "202020202": [(60.4518, 22.2666), (60.4600, 22.2800)],
    # Page 2 courses
    "303030303": [(60.2052, 24.6559), (60.2100, 24.6700), (60.2200, 24.6900)],
    "404040404": [(60.2934, 25.0378), (60.3000, 25.0500)],
    "505050505": [(66.5039, 25.7294), (66.5100, 25.7400), (66.5200, 25.7600)],
}


# ── Request handler ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[mock] {fmt % args}", flush=True)

    def do_GET(self):  # noqa: N802
        if mode == "error":
            if delay > 0:
                time.sleep(delay)
            self.send_response(500)
            self.end_headers()
            return

        path = urlparse(self.path).path

        if path == "/api/courses":
            if delay > 0:
                time.sleep(delay)
            if mode == "empty":
                courses = []
            elif mode == "many":
                courses = COURSES_MANY
            else:  # normal, full, corrupt
                courses = COURSES_NORMAL
            body = json.dumps({"courses": courses}).encode()
            self._respond(200, "application/json", body)

        elif path.startswith("/api/course/"):
            course_id = path.split("/")[-1]
            pts = COURSE_LATLON.get(course_id)
            if not pts:
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(urlparse(self.path).query)
            name = qs.get("name", [f"Course {course_id}"])[0]
            blob = fit.encode_course_fit(
                name, [{"lat": la, "lon": lo} for la, lo in pts],
                lean=(mode != "full"),
            )
            if mode == "corrupt":
                # Corrupt the body while keeping the length: the control case
                # that proves the device is really parsing, not just accepting
                # any 200 response.
                blob = bytearray(blob)
                for i in range(14, min(len(blob), 40)):
                    blob[i] ^= 0xFF
                blob = bytes(blob)
            print(f"[mock] FIT {course_id} name={name!r} mode={mode} bytes={len(blob)}", flush=True)
            self._respond(200, "application/vnd.ant.fit", blob)

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
    print(f"[mock] Listening on http://127.0.0.1:{port}  mode={mode}  delay={delay}s", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock] Stopped", flush=True)
