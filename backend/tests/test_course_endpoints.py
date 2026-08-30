"""Course endpoints backed by the single Garmin session, plus the optional
shared X-Api-Key secret."""
import base64
import struct


def _decode_ascii85_points(text: str) -> list[dict]:
    data = base64.a85decode(text, adobe=False)
    points = []
    for i in range(0, len(data) - 7, 8):
        lat = struct.unpack(">i", data[i:i+4])[0] / 1e7
        lon = struct.unpack(">i", data[i+4:i+8])[0] / 1e7
        points.append({"lat": lat, "lon": lon})
    return points


# ── happy path (dev mode: no API_KEY) ────────────────────────────────────────

def test_courses_returns_list(client, fake_session):
    fake_session.courses = [
        {"id": "111222333", "name": "Morning Trail", "distanceKm": 12.3},
        {"id": "444555666", "name": "Lakeside Loop", "distanceKm": 8.1},
    ]
    r = client.get("/api/courses")
    assert r.status_code == 200
    assert r.json()["courses"][0]["id"] == "111222333"


def test_courses_empty_list(client, fake_session):
    fake_session.courses = []
    r = client.get("/api/courses")
    assert r.status_code == 200
    assert r.json()["courses"] == []


def test_courses_forwards_limit_to_session(client, fake_session):
    captured = {}

    def get_courses(limit=10, offset=0):
        captured["limit"] = limit
        return []

    fake_session.get_courses = get_courses
    assert client.get("/api/courses?limit=25").status_code == 200
    assert captured["limit"] == 25


def test_courses_limit_over_cap_is_422(client):
    assert client.get("/api/courses?limit=999").status_code == 422


def test_courses_limit_zero_is_422(client):
    assert client.get("/api/courses?limit=0").status_code == 422


def test_courses_offset_negative_is_422(client):
    assert client.get("/api/courses?offset=-1").status_code == 422


# ── pagination: offset forwarded to session ──────────────────────────────────

def test_courses_forwards_offset_to_session(client, fake_session):
    captured = {}

    def get_courses(limit=10, offset=0):
        captured["limit"] = limit
        captured["offset"] = offset
        return []

    fake_session.get_courses = get_courses
    assert client.get("/api/courses?limit=5&offset=10").status_code == 200
    assert captured["limit"] == 5
    assert captured["offset"] == 10


def test_courses_second_page_results(client, fake_session):
    """Simulate fetching page 2: the session returns the next 5 courses."""
    fake_session.courses = [
        {"id": str(i), "name": f"Course {i}", "distanceKm": 5.0} for i in range(6, 11)
    ]
    r = client.get("/api/courses?limit=5&offset=5")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["courses"]]
    assert ids == ["6", "7", "8", "9", "10"]


def test_courses_last_page_empty(client, fake_session):
    """Requesting past the last item returns an empty list, not an error."""
    fake_session.courses = []
    r = client.get("/api/courses?limit=5&offset=100")
    assert r.status_code == 200
    assert r.json()["courses"] == []


def test_course_points_ascii85_roundtrip(client, fake_session):
    fake_session.points = [
        {"lat": 60.1699, "lon": 24.9384},
        {"lat": -33.8688, "lon": 151.2093},
    ]
    r = client.get("/api/course/111")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    decoded = _decode_ascii85_points(r.text)
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6
    assert abs(decoded[1]["lon"] - 151.2093) < 1e-6


# ── upstream Garmin failure → 502 ────────────────────────────────────────────

def test_courses_garmin_error_returns_502(client, fake_session):
    fake_session.raise_exc = Exception("Garmin API error")
    assert client.get("/api/courses").status_code == 502


def test_course_points_garmin_error_returns_502(client, fake_session):
    fake_session.raise_exc = Exception("Course not found")
    assert client.get("/api/course/999").status_code == 502


# ── expired/invalid Garmin tokens → 503 (widget shows a re-auth message) ──────

def test_courses_auth_expired_returns_503(client, fake_session):
    import garmin
    fake_session.raise_exc = garmin.GarminAuthError("tokens expired")
    r = client.get("/api/courses")
    assert r.status_code == 503


def test_course_points_auth_expired_returns_503(client, fake_session):
    import garmin
    fake_session.raise_exc = garmin.GarminAuthError("tokens expired")
    assert client.get("/api/course/1").status_code == 503


# ── shared-secret API key gate ───────────────────────────────────────────────

def test_api_key_required_when_set(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    assert client.get("/api/courses").status_code == 401


def test_api_key_accepts_correct_key(client, fake_session, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    fake_session.courses = []
    r = client.get("/api/courses", headers={"X-Api-Key": "s3cret"})
    assert r.status_code == 200


def test_api_key_rejects_wrong_key(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    r = client.get("/api/courses", headers={"X-Api-Key": "nope"})
    assert r.status_code == 401
