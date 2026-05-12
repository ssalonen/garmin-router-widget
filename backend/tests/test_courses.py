import pytest


SAMPLE_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk><trkseg>
    <trkpt lat="60.1699" lon="24.9384"><ele>20.0</ele></trkpt>
    <trkpt lat="60.1700" lon="24.9385"><ele>20.1</ele></trkpt>
    <trkpt lat="60.1800" lon="24.9500"><ele>25.0</ele></trkpt>
  </trkseg></trk>
</gpx>"""


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
    assert "detail" in response.json()


def test_get_course_returns_first_and_last_points(client, mock_garmin):
    mock_garmin.garth.get.return_value.content = SAMPLE_GPX
    response = client.get("/api/course/111222333")
    assert response.status_code == 200
    data = response.json()
    assert len(data["points"]) >= 2
    assert data["points"][0]["lat"] == pytest.approx(60.1699, abs=1e-4)
    assert data["points"][-1]["lat"] == pytest.approx(60.1800, abs=1e-4)


def test_get_course_thins_dense_points(client, mock_garmin):
    # Second point is ~12m from first — below 40m threshold — should be removed
    mock_garmin.garth.get.return_value.content = SAMPLE_GPX
    response = client.get("/api/course/111222333")
    data = response.json()
    assert len(data["points"]) == 2  # first + last; middle filtered


def test_get_course_garmin_error_returns_502(client, mock_garmin):
    mock_garmin.garth.get.side_effect = Exception("Course not found")
    response = client.get("/api/course/999")
    assert response.status_code == 502


# --- thin_points unit tests (pure function, no HTTP) ---

def test_thin_points_keeps_first_and_last():
    from garmin import thin_points
    points = [
        {"lat": 60.0001, "lon": 24.0001, "alt": 0.0},
        {"lat": 60.0001, "lon": 24.0001, "alt": 0.0},  # same location, filtered
        {"lat": 60.0010, "lon": 24.0010, "alt": 5.0},
    ]
    result = thin_points(points, min_m=40)
    assert result[0] == points[0]
    assert result[-1] == points[-1]


def test_thin_points_removes_close_intermediates():
    from garmin import thin_points
    # All intermediate points within 10m of each other; only first+last survive
    points = [{"lat": 60.0 + i * 0.00001, "lon": 24.0, "alt": 0.0} for i in range(10)]
    result = thin_points(points, min_m=40)
    assert result[0] == points[0]
    assert result[-1] == points[-1]
    assert len(result) == 2


def test_thin_points_keeps_distant_intermediates():
    from garmin import thin_points
    points = [
        {"lat": 60.0000, "lon": 24.0000, "alt": 0.0},
        {"lat": 60.0010, "lon": 24.0000, "alt": 0.0},  # ~111m away → kept
        {"lat": 60.0020, "lon": 24.0000, "alt": 0.0},
    ]
    result = thin_points(points, min_m=40)
    assert len(result) == 3


def test_thin_points_single_point():
    from garmin import thin_points
    points = [{"lat": 60.0, "lon": 24.0, "alt": 0.0}]
    result = thin_points(points, min_m=40)
    assert result == points


def test_thin_points_empty():
    from garmin import thin_points
    assert thin_points([], min_m=40) == []


# --- haversine unit test ---

def test_haversine_known_distance():
    from garmin import haversine_m
    # One degree of latitude ≈ 111 km
    d = haversine_m(60.0, 24.0, 61.0, 24.0)
    assert d == pytest.approx(111_195, rel=0.01)
