import struct
import pytest


SAMPLE_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk><trkseg>
    <trkpt lat="60.1699" lon="24.9384"><ele>20.0</ele></trkpt>
    <trkpt lat="60.1700" lon="24.9385"><ele>20.1</ele></trkpt>
    <trkpt lat="60.1800" lon="24.9500"><ele>25.0</ele></trkpt>
  </trkseg></trk>
</gpx>"""


# --- /api/courses (JSON) ---

def test_list_courses_returns_formatted_data(client, mock_garmin):
    mock_garmin.connectapi.return_value = {
        "courseList": [
            {"id": 111222333, "courseName": "Morning Trail", "totalDistance": 12345.0},
            {"id": 444555666, "courseName": "Lakeside Loop", "totalDistance": 8100.0},
        ]
    }
    response = client.get("/api/courses")
    assert response.status_code == 200
    data = response.json()
    assert len(data["courses"]) == 2
    assert data["courses"][0]["id"] == "111222333"
    assert data["courses"][0]["name"] == "Morning Trail"
    assert data["courses"][0]["distanceKm"] == pytest.approx(12.35, abs=0.01)
    assert data["courses"][1]["id"] == "444555666"


def test_list_courses_empty_list(client, mock_garmin):
    mock_garmin.connectapi.return_value = {"courseList": []}
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert response.json()["courses"] == []


def test_list_courses_garmin_error_returns_502(client, mock_garmin):
    mock_garmin.connectapi.side_effect = Exception("Garmin API error")
    response = client.get("/api/courses")
    assert response.status_code == 502


def test_get_course_garmin_error_returns_502(client, mock_garmin):
    mock_garmin.garth.get.side_effect = Exception("Course not found")
    response = client.get("/api/course/999")
    assert response.status_code == 502


# --- encode_points_binary (pure function) ---

def _decode(data: bytes) -> list[dict]:
    """Test helper mirroring the widget's decodeBinaryPoints."""
    points = []
    for i in range(0, len(data) - 7, 8):
        lat = struct.unpack(">i", data[i:i+4])[0] / 1e7
        lon = struct.unpack(">i", data[i+4:i+8])[0] / 1e7
        points.append({"lat": lat, "lon": lon})
    return points


def test_encode_binary_roundtrip_positive():
    from garmin import encode_points_binary
    pts = [{"lat": 60.1699, "lon": 24.9384}]
    decoded = _decode(encode_points_binary(pts))
    assert decoded[0]["lat"] == pytest.approx(60.1699, abs=1e-6)
    assert decoded[0]["lon"] == pytest.approx(24.9384, abs=1e-6)


def test_encode_binary_roundtrip_negative():
    # Southern hemisphere + western longitude — stresses sign handling
    from garmin import encode_points_binary
    pts = [{"lat": -33.8688, "lon": -70.6693}]
    decoded = _decode(encode_points_binary(pts))
    assert decoded[0]["lat"] == pytest.approx(-33.8688, abs=1e-6)
    assert decoded[0]["lon"] == pytest.approx(-70.6693, abs=1e-6)


def test_encode_binary_byte_length():
    from garmin import encode_points_binary
    pts = [{"lat": 60.0, "lon": 24.0}, {"lat": 61.0, "lon": 25.0}]
    assert len(encode_points_binary(pts)) == 16  # 2 points × 8 bytes


def test_encode_binary_empty():
    from garmin import encode_points_binary
    assert encode_points_binary([]) == b""


# --- thin_points (pure function) ---

def test_thin_points_keeps_first_and_last():
    from garmin import thin_points
    points = [
        {"lat": 60.0001, "lon": 24.0001},
        {"lat": 60.0001, "lon": 24.0001},  # same location, filtered
        {"lat": 60.0010, "lon": 24.0010},
    ]
    result = thin_points(points, min_m=15)
    assert result[0] == points[0]
    assert result[-1] == points[-1]


def test_thin_points_removes_close_intermediates():
    from garmin import thin_points
    # ~11m spacing — below 15m threshold
    points = [{"lat": 60.0 + i * 0.00001, "lon": 24.0} for i in range(10)]
    result = thin_points(points, min_m=15)
    assert result[0] == points[0]
    assert result[-1] == points[-1]
    assert len(result) == 2


def test_thin_points_keeps_distant_intermediates():
    from garmin import thin_points
    points = [
        {"lat": 60.0000, "lon": 24.0000},
        {"lat": 60.0010, "lon": 24.0000},  # ~111m — kept
        {"lat": 60.0020, "lon": 24.0000},
    ]
    result = thin_points(points, min_m=15)
    assert len(result) == 3


def test_thin_points_single_point():
    from garmin import thin_points
    assert thin_points([{"lat": 60.0, "lon": 24.0}], min_m=15) == [{"lat": 60.0, "lon": 24.0}]


def test_thin_points_empty():
    from garmin import thin_points
    assert thin_points([], min_m=15) == []


# --- haversine ---

def test_haversine_known_distance():
    from garmin import haversine_m
    d = haversine_m(60.0, 24.0, 61.0, 24.0)
    assert d == pytest.approx(111_195, rel=0.01)
