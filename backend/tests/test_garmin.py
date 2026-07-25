"""Tests for the garth auth seam and GarminSession (garmin.py).

garminconnect.Garmin is mocked everywhere here — no network, no credentials.
This pins the contract garmin.py relies on:
  - Garmin(..., return_on_mfa=True).login() -> (status, client_state)
  - Garmin.resume_login(client_state, code)
  - Garmin.client.dumps() / Garmin().login(token_blob)
"""
from unittest.mock import MagicMock, patch

import pytest

import garmin


# ── begin_login ─────────────────────────────────────────────────────────────

def test_begin_login_clean_returns_token_blob():
    fake = MagicMock()
    fake.login.return_value = (None, None)          # no MFA
    fake.client.dumps.return_value = "TOKEN-BLOB"
    with patch("garmin.Garmin", return_value=fake) as ctor:
        result = garmin.begin_login("user@example.com", "pw")
    ctor.assert_called_once()
    assert ctor.call_args.kwargs["return_on_mfa"] is True
    assert result.needs_mfa is False
    assert result.token_blob == "TOKEN-BLOB"


def test_begin_login_mfa_returns_continuation():
    fake = MagicMock()
    fake.login.return_value = ("needs_mfa", {"csrf": "abc"})
    with patch("garmin.Garmin", return_value=fake):
        result = garmin.begin_login("user@example.com", "pw")
    assert result.needs_mfa is True
    assert result.token_blob is None
    # continuation carries what resume_login needs
    assert result.mfa_context is not None


# ── resume_login ────────────────────────────────────────────────────────────

def test_resume_login_completes_and_dumps_tokens():
    fake = MagicMock()
    fake.login.return_value = ("needs_mfa", {"csrf": "abc"})
    fake.client.dumps.return_value = "TOKEN-AFTER-MFA"
    with patch("garmin.Garmin", return_value=fake):
        result = garmin.begin_login("user@example.com", "pw")
        blob = garmin.resume_login(result.mfa_context, "123456")
    fake.resume_login.assert_called_once_with({"csrf": "abc"}, "123456")
    assert blob == "TOKEN-AFTER-MFA"


# ── session_from_tokens ─────────────────────────────────────────────────────

def test_session_from_tokens_loads_blob():
    fake = MagicMock()
    with patch("garmin.Garmin", return_value=fake):
        session = garmin.session_from_tokens("TOKEN-BLOB")
    fake.login.assert_called_once_with("TOKEN-BLOB")
    assert isinstance(session, garmin.GarminSession)


# ── GarminSession data methods ──────────────────────────────────────────────

def test_session_get_courses_shapes_data():
    client = MagicMock()
    client.connectapi.return_value = [
        {"courseId": 111222333, "courseName": "Morning Trail", "distanceInMeters": 12345.0},
        {"courseId": 444555666, "courseName": "Lakeside Loop", "distanceInMeters": 8100.0},
    ]
    session = garmin.GarminSession(client)
    courses = session.get_courses(limit=10)
    assert courses == [
        {"id": "111222333", "name": "Morning Trail", "distanceKm": pytest.approx(12.35, abs=0.01)},
        {"id": "444555666", "name": "Lakeside Loop", "distanceKm": pytest.approx(8.1, abs=0.01)},
    ]


def test_session_get_course_points_extracts_lat_lon():
    client = MagicMock()
    client.connectapi.return_value = {"geoPoints": [
        {"latitude": 60.1699, "longitude": 24.9384},
        {"latitude": 60.1750, "longitude": 24.9450},
    ]}
    session = garmin.GarminSession(client)
    pts = session.get_course_points("111")
    assert pts == [
        {"lat": 60.1699, "lon": 24.9384},
        {"lat": 60.1750, "lon": 24.9450},
    ]


def test_session_get_courses_propagates_error():
    client = MagicMock()
    client.connectapi.side_effect = Exception("Garmin API error")
    session = garmin.GarminSession(client)
    with pytest.raises(Exception, match="Garmin API error"):
        session.get_courses()


def test_session_converts_auth_error_to_garmin_auth_error():
    from garminconnect import GarminConnectAuthenticationError
    client = MagicMock()
    client.connectapi.side_effect = GarminConnectAuthenticationError("401 expired")
    session = garmin.GarminSession(client)
    with pytest.raises(garmin.GarminAuthError):
        session.get_courses()
    with pytest.raises(garmin.GarminAuthError):
        session.get_course_points("123")


# ── get_courses field fallbacks (unofficial API's shifting field names) ───────

def test_get_courses_name_falls_back_to_name_then_synthetic():
    client = MagicMock()
    client.connectapi.return_value = [
        {"courseId": 1, "name": "Alt Field", "distanceInMeters": 1000.0},  # courseName missing
        {"courseId": 2, "distanceInMeters": 1000.0},                       # both missing
    ]
    out = garmin.GarminSession(client).get_courses()
    assert out[0]["name"] == "Alt Field"
    assert out[1]["name"] == "Course 2"


def test_get_courses_distance_fallback_chain():
    client = MagicMock()
    client.connectapi.return_value = [
        {"courseId": 1, "courseName": "A", "totalDistance": 2000.0},   # distanceInMeters missing
        {"courseId": 2, "courseName": "B", "distance": 3000.0},        # only 'distance'
        {"courseId": 3, "courseName": "C"},                            # none → 0
    ]
    out = garmin.GarminSession(client).get_courses()
    assert out[0]["distanceKm"] == 2.0
    assert out[1]["distanceKm"] == 3.0
    assert out[2]["distanceKm"] == 0


def test_get_courses_null_fields_fall_back_and_do_not_crash():
    # JSON null (present-but-null) must be treated like a missing key, not
    # passed through — otherwise None/1000 raises and None becomes the name.
    client = MagicMock()
    client.connectapi.return_value = [
        {"courseId": 9, "courseName": None, "distanceInMeters": None},
    ]
    out = garmin.GarminSession(client).get_courses()
    assert out[0]["name"] == "Course 9"
    assert out[0]["distanceKm"] == 0


def test_get_courses_skips_entries_without_id():
    client = MagicMock()
    client.connectapi.return_value = [
        {"name": "no id"},
        {"courseId": 7, "courseName": "Keep", "distanceInMeters": 0.0},
    ]
    out = garmin.GarminSession(client).get_courses()
    assert len(out) == 1
    assert out[0]["id"] == "7"


def test_get_course_points_empty_or_missing_geopoints():
    client = MagicMock()
    client.connectapi.return_value = {}  # no geoPoints key
    assert garmin.GarminSession(client).get_course_points("1") == []


# ── garth contract pin: guard against a garminconnect upgrade breaking the seam

def test_garth_seam_contract_matches_real_garminconnect():
    """The faked seam is only trustworthy if the real library still exposes what
    begin_login/resume_login/session_from_tokens depend on."""
    import inspect

    from garminconnect import Garmin as RealGarmin

    assert "return_on_mfa" in inspect.signature(RealGarmin.__init__).parameters
    assert hasattr(RealGarmin, "login")
    assert hasattr(RealGarmin, "resume_login")
    # Construction is offline (no login() call) — verify the token (de)serialisers.
    g = RealGarmin(email="x", password="y")
    assert hasattr(g.client, "dumps")
    assert hasattr(g.client, "loads")
