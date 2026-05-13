import math
import os
import struct
import threading
import xml.etree.ElementTree as ET

from garminconnect import Garmin

_client: Garmin | None = None
_lock = threading.Lock()

# Garmin Connect API endpoints (unofficial; may change without notice)
_COURSE_LIST_PATH = "/course-service/course/"
_COURSE_GPX_PATH = "/course-service/course/{id}/gpx"


def _get_client() -> Garmin:
    global _client
    with _lock:
        if _client is None:
            email = os.environ["GARMIN_EMAIL"]
            password = os.environ["GARMIN_PASSWORD"]
            _client = Garmin(email, password)
            _client.login()
    return _client


def _reset_client() -> None:
    global _client
    with _lock:
        _client = None


def get_courses(limit: int = 10) -> list[dict]:
    client = _get_client()
    try:
        data = client.connectapi(
            _COURSE_LIST_PATH,
            params={"start": 0, "limit": limit, "courseType": "ALL"},
        )
    except Exception:
        _reset_client()
        raise

    # API may return "courseList" or "courses" depending on version
    raw = data.get("courseList", data.get("courses", []))
    return [
        {
            "id": str(c["id"]),
            "name": c.get("courseName", c.get("name", f"Course {c['id']}")),
            "distanceKm": round(
                c.get("totalDistance", c.get("distance", 0)) / 1000, 2
            ),
        }
        for c in raw
        if c.get("id")
    ]


def get_course_points(course_id: str, thin_m: int = 15) -> list[dict]:
    client = _get_client()
    try:
        response = client.garth.get(
            "connect", _COURSE_GPX_PATH.format(id=course_id)
        )
        gpx_bytes = response.content
    except Exception:
        _reset_client()
        raise
    return thin_points(_parse_gpx(gpx_bytes), thin_m)


def _parse_gpx(gpx_bytes: bytes) -> list[dict]:
    # Only extract lat/lon — Navigation.startNavigation() has no use for elevation
    # or timestamps, and omitting them keeps the JSON payload smaller.
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    root = ET.fromstring(gpx_bytes)
    points = []
    for trkpt in root.findall(".//gpx:trkpt", ns):
        points.append({
            "lat": float(trkpt.attrib["lat"]),
            "lon": float(trkpt.attrib["lon"]),
        })
    return points


def encode_points_binary(points: list[dict]) -> bytes:
    """Pack lat/lon pairs as big-endian int32 scaled by 1e7.

    8 bytes per point. Precision: 1e-7 degrees ≈ 11 mm — sufficient for
    navigation. int32 covers ±214 degrees, so all valid lat/lon fit.
    """
    return struct.pack(f">{2 * len(points)}i", *[
        v for p in points
        for v in (round(p["lat"] * 1e7), round(p["lon"] * 1e7))
    ])


def thin_points(points: list[dict], min_m: float = 15) -> list[dict]:
    if not points:
        return []
    if len(points) == 1:
        return list(points)
    result = [points[0]]
    for p in points[1:-1]:
        last = result[-1]
        if haversine_m(last["lat"], last["lon"], p["lat"], p["lon"]) >= min_m:
            result.append(p)
    result.append(points[-1])
    return result


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
