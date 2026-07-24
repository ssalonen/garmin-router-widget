"""End-to-end through the real get_session path: token file on disk → garth
session → course endpoint. Only the garth boundary (session_from_tokens) is
faked, so the file read, session caching, and response encoding are all real.

State (token file, cached session, setup-service) lives in deps; these tests
patch it there and drive the real app.
"""
import base64
import struct
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from garmin import GarminSession

SETUP_TOKEN = "test-setup-token"


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
    import deps
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("THE-BLOB")
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    deps.reset_session()

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
    deps.reset_session()


def test_integration_course_points_ascii85(tmp_path, monkeypatch):
    import deps
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("THE-BLOB")
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    deps.reset_session()

    fake_client = MagicMock()
    fake_client.connectapi.return_value = {"geoPoints": [
        {"latitude": 60.1699, "longitude": 24.9384},
    ]}
    monkeypatch.setattr("garmin.session_from_tokens", lambda blob: GarminSession(fake_client))

    r = TestClient(main.app).get("/api/course/111222333")
    assert r.status_code == 200
    decoded = _decode_ascii85_points(r.text)
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6
    deps.reset_session()


def test_integration_missing_token_file_returns_503(tmp_path, monkeypatch):
    import deps
    import main
    monkeypatch.setattr(deps, "TOKEN_FILE", str(tmp_path / "does-not-exist.blob"))
    deps.reset_session()
    assert TestClient(main.app).get("/api/courses").status_code == 503
    deps.reset_session()


def test_integration_web_setup_then_serve(tmp_path, monkeypatch):
    """Full bootstrap: POST /setup/login writes the token file, and a
    subsequent /api/courses loads it and serves courses. Only garth is faked."""
    import deps
    import main
    from garmin import LoginResult

    token_file = tmp_path / "tokens.blob"
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SETUP_TOKEN", SETUP_TOKEN)
    deps.reset_session()
    deps._setup_service = None  # rebuild the service against the patched path

    monkeypatch.setattr("garmin.begin_login",
                        lambda email, password: LoginResult(token_blob=f"BLOB::{email}"))
    fake_client = MagicMock()
    fake_client.connectapi.return_value = [
        {"courseId": 7, "courseName": "Web Loop", "distanceInMeters": 4200.0},
    ]
    monkeypatch.setattr("garmin.session_from_tokens", lambda blob: GarminSession(fake_client))

    c = TestClient(main.app)

    setup = c.post("/setup/login",
                   data={"email": "rider@example.com", "password": "pw", "token": SETUP_TOKEN})
    assert setup.status_code == 200
    assert token_file.read_text() == "BLOB::rider@example.com"

    courses = c.get("/api/courses")
    assert courses.status_code == 200
    assert courses.json()["courses"][0]["name"] == "Web Loop"

    deps.reset_session()
    deps._setup_service = None


def test_integration_corrupt_blob_returns_503(tmp_path, monkeypatch):
    """A present-but-invalid token blob is a defined 503, not a raw 500."""
    import deps
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("CORRUPT-NOT-A-REAL-BLOB")
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    deps.reset_session()

    def boom(blob):
        raise ValueError("not a valid garth token")

    monkeypatch.setattr("garmin.session_from_tokens", boom)
    assert TestClient(main.app).get("/api/courses").status_code == 503
    assert deps._session is None  # failed load is not cached
    deps.reset_session()


def test_integration_garmin_error_resets_and_reloads_session(tmp_path, monkeypatch):
    """502 on a Garmin error must evict the cached session so the next request
    rebuilds from disk (token-expiry recovery)."""
    import deps
    import main
    token_file = tmp_path / "tokens.blob"
    token_file.write_text("BLOB")
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    deps.reset_session()

    bad = MagicMock()
    bad.connectapi.side_effect = Exception("garmin down")
    good = MagicMock()
    good.connectapi.return_value = []
    sessions = iter([GarminSession(bad), GarminSession(good)])
    calls = {"n": 0}

    def loader(blob):
        calls["n"] += 1
        return next(sessions)

    monkeypatch.setattr("garmin.session_from_tokens", loader)
    c = TestClient(main.app)

    assert c.get("/api/courses").status_code == 502
    assert calls["n"] == 1
    # session was reset → second call rebuilds and succeeds
    assert c.get("/api/courses").status_code == 200
    assert calls["n"] == 2
    deps.reset_session()


def test_integration_resetup_evicts_cached_session(tmp_path, monkeypatch):
    """Re-running /setup while a session is already cached must swap it for the
    freshly-authenticated one."""
    import deps
    import main
    from garmin import LoginResult

    token_file = tmp_path / "tokens.blob"
    token_file.write_text("BLOB1")
    monkeypatch.setattr(deps, "TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SETUP_TOKEN", SETUP_TOKEN)
    deps.reset_session()
    deps._setup_service = None

    def loader(blob):
        client = MagicMock()
        client.connectapi.return_value = [
            {"courseId": 1, "courseName": blob, "distanceInMeters": 0.0},
        ]
        return GarminSession(client)

    monkeypatch.setattr("garmin.session_from_tokens", loader)
    monkeypatch.setattr("garmin.begin_login",
                        lambda email, password: LoginResult(token_blob="BLOB2"))
    c = TestClient(main.app)

    assert c.get("/api/courses").json()["courses"][0]["name"] == "BLOB1"
    assert c.post("/setup/login",
                  data={"email": "a@example.com", "password": "pw", "token": SETUP_TOKEN}).status_code == 200
    assert token_file.read_text() == "BLOB2"
    assert c.get("/api/courses").json()["courses"][0]["name"] == "BLOB2"

    deps.reset_session()
    deps._setup_service = None
