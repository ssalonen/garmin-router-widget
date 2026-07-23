"""Course endpoints now require a per-user api_key (X-Api-Key) that resolves to
a Garmin session. These tests drive the HTTP layer with a seeded key."""
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


# ── auth gate ────────────────────────────────────────────────────────────────

def test_courses_without_api_key_is_401(client):
    assert client.get("/api/courses").status_code == 401


def test_courses_with_unknown_api_key_is_401(client):
    r = client.get("/api/courses", headers={"X-Api-Key": "bogus"})
    assert r.status_code == 401


def test_course_points_without_api_key_is_401(client):
    assert client.get("/api/course/123").status_code == 401


# ── happy path ────────────────────────────────────────────────────────────────

def test_courses_with_valid_key_returns_list(client, seeded_session):
    api_key, session = seeded_session
    session.courses = [
        {"id": "111222333", "name": "Morning Trail", "distanceKm": 12.3},
        {"id": "444555666", "name": "Lakeside Loop", "distanceKm": 8.1},
    ]
    r = client.get("/api/courses", headers={"X-Api-Key": api_key})
    assert r.status_code == 200
    data = r.json()
    assert len(data["courses"]) == 2
    assert data["courses"][0]["id"] == "111222333"


def test_courses_empty_list(client, seeded_session):
    api_key, session = seeded_session
    session.courses = []
    r = client.get("/api/courses", headers={"X-Api-Key": api_key})
    assert r.status_code == 200
    assert r.json()["courses"] == []


def test_course_points_ascii85_roundtrip(client, seeded_session):
    api_key, session = seeded_session
    session.points = [
        {"lat": 60.1699, "lon": 24.9384},
        {"lat": -33.8688, "lon": 151.2093},
    ]
    r = client.get("/api/course/111", headers={"X-Api-Key": api_key})
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    decoded = _decode_ascii85_points(r.text)
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6
    assert abs(decoded[1]["lon"] - 151.2093) < 1e-6


# ── upstream Garmin failure ────────────────────────────────────────────────────

def test_courses_garmin_error_returns_502(client, seeded_session):
    api_key, session = seeded_session
    session.raise_exc = Exception("Garmin API error")
    r = client.get("/api/courses", headers={"X-Api-Key": api_key})
    assert r.status_code == 502


def test_course_points_garmin_error_returns_502(client, seeded_session):
    api_key, session = seeded_session
    session.raise_exc = Exception("Course not found")
    r = client.get("/api/course/999", headers={"X-Api-Key": api_key})
    assert r.status_code == 502
