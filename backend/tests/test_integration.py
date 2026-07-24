"""End-to-end through the real get_session path: token file on disk → garth
session → course endpoint. Only the garth boundary (session_from_tokens) is
faked, so the file read, session caching, and response encoding are all real.
"""
import base64
import struct
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from garmin import GarminSession


def _decode_ascii85_points(text: str) -> list[dict]:
    data = base64.a85decode(text, adobe=False)
    return [
        {
            "lat": struct.unpack(">i", data[i:i+4])[0] / 1e7,
            "lon": struct.unpack(">i", data[i+4:i+8])[0] / 1e7,
        }
        for i in range(0, len(data) - 7, 8)
    ]


def test_integration_token_file_to_courses(tmp_path, monkeypatch):
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("THE-BLOB")
    monkeypatch.setattr(main, "_TOKEN_FILE", str(token_file))
    main._reset_session()

    fake_client = MagicMock()
    fake_client.connectapi.return_value = [
        {"courseId": 111222333, "courseName": "Morning Trail", "distanceInMeters": 12345.0},
    ]
    captured = {}

    def fake_session_from_tokens(blob):
        captured["blob"] = blob
        return GarminSession(fake_client)

    monkeypatch.setattr("garmin.session_from_tokens", fake_session_from_tokens)

    r = TestClient(main.app).get("/api/courses")
    assert r.status_code == 200
    assert r.json()["courses"][0]["name"] == "Morning Trail"
    assert captured["blob"] == "THE-BLOB"  # the on-disk blob was loaded
    main._reset_session()


def test_integration_course_points_ascii85(tmp_path, monkeypatch):
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("THE-BLOB")
    monkeypatch.setattr(main, "_TOKEN_FILE", str(token_file))
    main._reset_session()

    fake_client = MagicMock()
    fake_client.connectapi.return_value = {"geoPoints": [
        {"latitude": 60.1699, "longitude": 24.9384},
    ]}
    monkeypatch.setattr("garmin.session_from_tokens", lambda blob: GarminSession(fake_client))

    r = TestClient(main.app).get("/api/course/111222333")
    assert r.status_code == 200
    decoded = _decode_ascii85_points(r.text)
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6
    main._reset_session()


def test_integration_missing_token_file_returns_503(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "_TOKEN_FILE", str(tmp_path / "does-not-exist.blob"))
    main._reset_session()
    assert TestClient(main.app).get("/api/courses").status_code == 503
    main._reset_session()


def test_integration_web_setup_then_serve(tmp_path, monkeypatch):
    """Full bootstrap: POST /setup/login writes the token file, and a
    subsequent /api/courses loads it and serves courses. Only garth is faked."""
    import main
    from garmin import GarminSession, LoginResult

    token_file = tmp_path / "tokens.blob"
    monkeypatch.setattr(main, "_TOKEN_FILE", str(token_file))
    main._reset_session()
    main._setup_service = None  # rebuild the service against the patched path

    monkeypatch.setattr("garmin.begin_login",
                        lambda email, password: LoginResult(token_blob=f"BLOB::{email}"))
    fake_client = MagicMock()
    fake_client.connectapi.return_value = [
        {"courseId": 7, "courseName": "Web Loop", "distanceInMeters": 4200.0},
    ]
    monkeypatch.setattr("garmin.session_from_tokens", lambda blob: GarminSession(fake_client))

    c = TestClient(main.app)

    setup = c.post("/setup/login", data={"email": "rider@example.com", "password": "pw"})
    assert setup.status_code == 200
    assert token_file.read_text() == "BLOB::rider@example.com"

    courses = c.get("/api/courses")
    assert courses.status_code == 200
    assert courses.json()["courses"][0]["name"] == "Web Loop"

    main._reset_session()
    main._setup_service = None
