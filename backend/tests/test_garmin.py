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
