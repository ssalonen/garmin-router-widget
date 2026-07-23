"""Pure encoder tests — wire format between backend and widget.

Endpoint behaviour lives in test_course_endpoints.py; these cover only the
credential-free pure functions in garmin.py.
"""
import base64
import struct


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
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6
    assert abs(decoded[0]["lon"] - 24.9384) < 1e-6


def test_encode_ascii85_roundtrip_negative():
    from garmin import encode_points_ascii85
    pts = [{"lat": -33.8688, "lon": -70.6693}]
    raw = base64.a85decode(encode_points_ascii85(pts), adobe=False)
    decoded = _decode_binary(raw)
    assert abs(decoded[0]["lat"] - (-33.8688)) < 1e-6
    assert abs(decoded[0]["lon"] - (-70.6693)) < 1e-6


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
