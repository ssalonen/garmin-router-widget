"""Tests for the web bootstrap service (setup.py).

The garth seam is faked; these cover the two-step login logic (credentials,
then phone MFA) and that a completed login writes the single token file.
"""
import pytest

from bootstrap import ExpiredLogin, PendingLogins, SetupService
from garmin import LoginResult


class FakeAuth:
    def __init__(self, *, mfa=False, begin_error=None):
        self._mfa = mfa
        self._begin_error = begin_error
        self.resumed_with = None

    def begin_login(self, email, password):
        if self._begin_error:
            raise self._begin_error
        if self._mfa:
            return LoginResult(mfa_context=("live-client", {"csrf": "x"}))
        return LoginResult(token_blob=f"blob::{email}")

    def resume_login(self, mfa_context, code):
        self.resumed_with = (mfa_context, code)
        return "blob::after-mfa"


def _service(tmp_path, auth):
    return SetupService(str(tmp_path / "tokens.blob"), auth=auth, pending=PendingLogins())


# ── begin: no MFA ────────────────────────────────────────────────────────────

def test_begin_without_mfa_writes_token_file(tmp_path):
    svc = _service(tmp_path, FakeAuth())
    outcome = svc.begin("rider@example.com", "pw")
    assert outcome.done is True
    assert outcome.mfa_session_id is None
    assert (tmp_path / "tokens.blob").read_text() == "blob::rider@example.com"


def test_begin_bad_credentials_raises(tmp_path):
    svc = _service(tmp_path, FakeAuth(begin_error=Exception("bad creds")))
    with pytest.raises(Exception, match="bad creds"):
        svc.begin("rider@example.com", "wrong")
    assert not (tmp_path / "tokens.blob").exists()  # nothing written on failure


# ── begin: MFA branch ────────────────────────────────────────────────────────

def test_begin_with_mfa_defers_and_writes_nothing(tmp_path):
    svc = _service(tmp_path, FakeAuth(mfa=True))
    outcome = svc.begin("rider@example.com", "pw")
    assert outcome.done is False
    assert outcome.mfa_session_id
    assert not (tmp_path / "tokens.blob").exists()


def test_complete_mfa_writes_token_file(tmp_path):
    auth = FakeAuth(mfa=True)
    svc = _service(tmp_path, auth)
    sid = svc.begin("rider@example.com", "pw").mfa_session_id
    outcome = svc.complete_mfa(sid, "123456")
    assert outcome.done is True
    assert auth.resumed_with == (("live-client", {"csrf": "x"}), "123456")
    assert (tmp_path / "tokens.blob").read_text() == "blob::after-mfa"


def test_complete_mfa_unknown_session_raises(tmp_path):
    svc = _service(tmp_path, FakeAuth(mfa=True))
    with pytest.raises(ExpiredLogin):
        svc.complete_mfa("no-such-session", "123456")


def test_mfa_session_is_single_use(tmp_path):
    svc = _service(tmp_path, FakeAuth(mfa=True))
    sid = svc.begin("rider@example.com", "pw").mfa_session_id
    svc.complete_mfa(sid, "123456")
    with pytest.raises(ExpiredLogin):
        svc.complete_mfa(sid, "123456")


def test_token_file_written_owner_only(tmp_path):
    svc = _service(tmp_path, FakeAuth())
    svc.begin("rider@example.com", "pw")
    mode = (tmp_path / "tokens.blob").stat().st_mode
    assert (mode & 0o077) == 0


def test_save_overwrites_and_leaves_no_temp_files(tmp_path):
    # A second sign-in (token refresh) must replace the blob atomically, with no
    # stray temp file left in the directory.
    SetupService(str(tmp_path / "tokens.blob"), auth=FakeAuth(), pending=PendingLogins()) \
        .begin("first@example.com", "pw")
    SetupService(str(tmp_path / "tokens.blob"), auth=FakeAuth(), pending=PendingLogins()) \
        .begin("second@example.com", "pw")
    assert (tmp_path / "tokens.blob").read_text() == "blob::second@example.com"
    assert [p.name for p in tmp_path.iterdir()] == ["tokens.blob"]


# ── PendingLogins ────────────────────────────────────────────────────────────

def test_pending_roundtrip_and_single_use():
    p = PendingLogins()
    sid = p.put(("ctx",))
    assert p.pop(sid) == ("ctx",)
    assert p.pop(sid) is None


def test_pending_expires():
    clock = {"t": 0.0}
    p = PendingLogins(ttl_seconds=60, now=lambda: clock["t"])
    sid = p.put(object())
    clock["t"] = 61
    assert p.pop(sid) is None


def test_pending_sweeps_abandoned_sessions_on_put():
    # An abandoned MFA (never popped) must not linger once expired: a later put
    # sweeps it, so the map does not grow unbounded.
    clock = {"t": 0.0}
    p = PendingLogins(ttl_seconds=60, now=lambda: clock["t"])
    p.put(object())            # abandoned
    assert len(p._sessions) == 1
    clock["t"] = 61
    p.put(object())            # triggers sweep of the expired one
    assert len(p._sessions) == 1  # only the fresh entry remains
