import base64
import struct
import pytest


# --- /api/courses (JSON) ---

def test_list_courses_returns_formatted_data(client, mock_garmin):
    mock_garmin.connectapi.return_value = [
        {"courseId": 111222333, "courseName": "Morning Trail", "distanceInMeters": 12345.0},
        {"courseId": 444555666, "courseName": "Lakeside Loop", "distanceInMeters": 8100.0},
    ]
    response = client.get("/api/courses")
    assert response.status_code == 200
    data = response.json()
    assert len(data["courses"]) == 2
    assert data["courses"][0]["id"] == "111222333"
    assert data["courses"][0]["name"] == "Morning Trail"
    assert data["courses"][0]["distanceKm"] == pytest.approx(12.35, abs=0.01)
    assert data["courses"][1]["id"] == "444555666"


def test_list_courses_empty_list(client, mock_garmin):
    mock_garmin.connectapi.return_value = []
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert response.json()["courses"] == []


def test_list_courses_garmin_error_returns_502(client, mock_garmin):
    mock_garmin.connectapi.side_effect = Exception("Garmin API error")
    response = client.get("/api/courses")
    assert response.status_code == 502


def test_get_course_garmin_error_returns_502(client, mock_garmin):
    mock_garmin.connectapi.side_effect = Exception("Course not found")
    response = client.get("/api/course/999")
    assert response.status_code == 502


def test_get_course_returns_text_plain_ascii85(client, mock_garmin):
    mock_garmin.connectapi.return_value = {"geoPoints": [
        {"latitude": 60.1699, "longitude": 24.9384},
    ]}
    response = client.get("/api/course/111")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    # Verify round-trip: ASCII85 decode → binary decode → original coordinates
    raw = base64.a85decode(response.text, adobe=False)
    lat = struct.unpack(">i", raw[0:4])[0] / 1e7
    lon = struct.unpack(">i", raw[4:8])[0] / 1e7
    assert lat == pytest.approx(60.1699, abs=1e-6)
    assert lon == pytest.approx(24.9384, abs=1e-6)


# --- encode_points_binary / encode_points_ascii85 (pure functions) ---

def _decode_binary(data: bytes) -> list[dict]:
    """Test helper mirroring the widget's decodeBinaryPoints."""
    points = []
    for i in range(0, len(data) - 7, 8):
        lat = struct.unpack(">i", data[i:i+4])[0] / 1e7
        lon = struct.unpack(">i", data[i+4:i+8])[0] / 1e7
        points.append({"lat": lat, "lon": lon})
    return points


# Golden vectors — exact bytes produced by encode_points_binary.
# If Python produces these bytes AND the Monkey C decoder accepts them,
# the wire format is proven end-to-end compatible.
#   Helsinki : lat= 60.1699, lon= 24.9384  → 0x23dd32b8 0x0edd4c40
#   Sydney   : lat=-33.8688, lon=151.2093  → 0xebd00800 0x5a20b548
GOLDEN_HELSINKI_BYTES  = bytes([35, 221, 50, 184, 14, 221, 76, 64])
GOLDEN_SYDNEY_BYTES    = bytes([235, 208, 8, 0, 90, 32, 181, 72])
# Corresponding ASCII85 strings (base64.a85encode(..., adobe=False))
GOLDEN_HELSINKI_A85 = ",Mb,b%c'fD"
GOLDEN_SYDNEY_A85   = "ld,n;=s14D"


def test_encode_binary_golden_helsinki():
    from garmin import encode_points_binary
    assert encode_points_binary([{"lat": 60.1699, "lon": 24.9384}]) == GOLDEN_HELSINKI_BYTES


def test_encode_binary_golden_sydney():
    from garmin import encode_points_binary
    assert encode_points_binary([{"lat": -33.8688, "lon": 151.2093}]) == GOLDEN_SYDNEY_BYTES


def test_encode_ascii85_golden_helsinki():
    from garmin import encode_points_ascii85
    assert encode_points_ascii85([{"lat": 60.1699, "lon": 24.9384}]) == GOLDEN_HELSINKI_A85


def test_encode_ascii85_golden_sydney():
    from garmin import encode_points_ascii85
    assert encode_points_ascii85([{"lat": -33.8688, "lon": 151.2093}]) == GOLDEN_SYDNEY_A85


def test_encode_ascii85_roundtrip_positive():
    from garmin import encode_points_ascii85
    pts = [{"lat": 60.1699, "lon": 24.9384}]
    raw = base64.a85decode(encode_points_ascii85(pts), adobe=False)
    decoded = _decode_binary(raw)
    assert decoded[0]["lat"] == pytest.approx(60.1699, abs=1e-6)
    assert decoded[0]["lon"] == pytest.approx(24.9384, abs=1e-6)


def test_encode_ascii85_roundtrip_negative():
    from garmin import encode_points_ascii85
    pts = [{"lat": -33.8688, "lon": -70.6693}]
    raw = base64.a85decode(encode_points_ascii85(pts), adobe=False)
    decoded = _decode_binary(raw)
    assert decoded[0]["lat"] == pytest.approx(-33.8688, abs=1e-6)
    assert decoded[0]["lon"] == pytest.approx(-70.6693, abs=1e-6)


def test_encode_ascii85_empty():
    from garmin import encode_points_ascii85
    assert encode_points_ascii85([]) == ""


def test_encode_binary_byte_length():
    from garmin import encode_points_binary
    pts = [{"lat": 60.0, "lon": 24.0}, {"lat": 61.0, "lon": 25.0}]
    assert len(encode_points_binary(pts)) == 16  # 2 points × 8 bytes


def test_encode_binary_empty():
    from garmin import encode_points_binary
    assert encode_points_binary([]) == b""
