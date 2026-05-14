"""
Integration tests — exercise the full HTTP request/response pipeline.

These patch at the garmin function level (not the Garmin Connect HTTP level),
so they test: routing + serialisation + response format, without needing
real Garmin credentials.
"""
import struct
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def http_client():
    return TestClient(app)


def _decode_binary(data: bytes) -> list[dict]:
    """Python mirror of the widget's decodeBinaryPoints for assertion use."""
    points = []
    for i in range(0, len(data) - 7, 8):
        lat = struct.unpack(">i", data[i:i+4])[0] / 1e7
        lon = struct.unpack(">i", data[i+4:i+8])[0] / 1e7
        points.append({"lat": lat, "lon": lon})
    return points


# Coordinates chosen to exercise positive, negative, and high-byte values
INTEGRATION_POINTS = [
    {"lat":  60.1699, "lon":  24.9384},   # Helsinki, all positive
    {"lat": -33.8688, "lon": 151.2093},   # Sydney, negative lat + lon > 127
    {"lat":  -1.2921, "lon": -36.8219},   # Nairobi-ish, both negative
]


def test_integration_course_binary_roundtrip(http_client):
    """get_course_points → binary HTTP response → decoded coords match input."""
    with patch("garmin.get_course_points", return_value=INTEGRATION_POINTS):
        response = http_client.get("/api/course/123456789")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert len(response.content) == len(INTEGRATION_POINTS) * 8

    decoded = _decode_binary(response.content)
    for original, got in zip(INTEGRATION_POINTS, decoded):
        assert got["lat"] == pytest.approx(original["lat"], abs=1e-6)
        assert got["lon"] == pytest.approx(original["lon"], abs=1e-6)


def test_integration_course_empty_route(http_client):
    """Zero points encodes to zero bytes."""
    with patch("garmin.get_course_points", return_value=[]):
        response = http_client.get("/api/course/123456789")
    assert response.status_code == 200
    assert response.content == b""


def test_integration_courses_list_shape(http_client):
    """GET /api/courses returns exactly the shape the widget parser expects."""
    fake_courses = [
        {"id": "111222333", "name": "Morning Trail", "distanceKm": 12.3},
        {"id": "444555666", "name": "Lakeside Loop",  "distanceKm":  8.1},
    ]
    with patch("garmin.get_courses", return_value=fake_courses):
        response = http_client.get("/api/courses")

    assert response.status_code == 200
    data = response.json()
    assert "courses" in data
    for course in data["courses"]:
        assert set(course.keys()) == {"id", "name", "distanceKm"}
        assert isinstance(course["id"], str)
        assert isinstance(course["name"], str)
        assert isinstance(course["distanceKm"], (int, float))
