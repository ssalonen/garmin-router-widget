import math
import os
import struct
import threading

from garminconnect import Garmin

_client: Garmin | None = None
_lock = threading.Lock()

# Garmin Connect API endpoints (unofficial; may change without notice)
_COURSE_LIST_PATH = "/course-service/course/favorites/"
_COURSE_PATH = "/course-service/course/{id}"


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
    return [
        {
            "id": str(c["courseId"]),
            "name": c.get("courseName", c.get("name", f"Course {c['courseId']}")),
            "distanceKm": round(
                c.get("distanceInMeters", c.get("totalDistance", c.get("distance", 0))) / 1000, 2
            ),
        }
        for c in data
        if c.get("courseId")
    ]


def get_course_points(course_id: str, thin_m: int = 15) -> list[dict]:
    client = _get_client()
    try:
        response = client.connectapi(
            _COURSE_PATH.format(id=course_id)
        )
        points = [{"lat": pt["latitude"], "lon": pt["longitude"]} for pt in response.get("geoPoints", [])]
        return thin_points(points, thin_m)
    except Exception:
        _reset_client()
        raise

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
