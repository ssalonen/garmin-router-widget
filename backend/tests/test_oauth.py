"""Tests for the OAuth provider orchestration (oauth.py).

The garth seam is faked (FakeAuth) so these tests cover only provider logic:
client/redirect validation, the login → code → token → session pipeline, and
the MFA branch. No network, no HTTP.
"""
import pytest

from oauth import ExpiredLogin, OAuthConfig, OAuthProvider
from store import AuthCodeStore, PendingLoginStore, TokenStore


class FakeSession:
    def __init__(self, blob):
        self.blob = blob


class FakeAuth:
    """Stand-in for the garmin module's auth seam."""

    def __init__(self, *, mfa=False):
        self._mfa = mfa
        self.resumed_with = None

    def begin_login(self, email, password):
        from garmin import LoginResult
        if self._mfa:
            return LoginResult(mfa_context=("live-client", {"csrf": "x"}))
        return LoginResult(token_blob=f"blob-for-{email}")

    def resume_login(self, mfa_context, mfa_code):
        self.resumed_with = (mfa_context, mfa_code)
        return "blob-after-mfa"

    def session_from_tokens(self, blob):
        return FakeSession(blob)


@pytest.fixture
def config():
    return OAuthConfig(
        client_id="garmin-router-widget",
        redirect_uris={"https://backend.example.com/oauth/callback"},
    )


def make_provider(tmp_path, config, auth):
    return OAuthProvider(
        token_store=TokenStore(str(tmp_path)),
        code_store=AuthCodeStore(),
        pending_store=PendingLoginStore(),
        config=config,
        auth=auth,
    )


# ── authorization request validation ────────────────────────────────────────

def test_validate_authorization_accepts_known_client_and_redirect(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    assert p.validate_authorization("garmin-router-widget",
                                    "https://backend.example.com/oauth/callback")


def test_validate_authorization_rejects_unknown_client(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    assert not p.validate_authorization("someone-else",
                                        "https://backend.example.com/oauth/callback")


def test_validate_authorization_rejects_unregistered_redirect(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    assert not p.validate_authorization("garmin-router-widget",
                                        "https://evil.example.com/steal")


# ── clean login → code → token → session ────────────────────────────────────

def test_login_without_mfa_issues_redeemable_code(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    outcome = p.begin_login("user@example.com", "pw")
    assert outcome.needs_mfa is False
    assert outcome.auth_code

    api_key = p.redeem_code(outcome.auth_code)
    assert api_key
    session = p.session_for_api_key(api_key)
    assert isinstance(session, FakeSession)
    assert session.blob == "blob-for-user@example.com"


def test_code_is_single_use(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    outcome = p.begin_login("user@example.com", "pw")
    assert p.redeem_code(outcome.auth_code)
    assert p.redeem_code(outcome.auth_code) is None


def test_session_for_unknown_api_key_is_none(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth())
    assert p.session_for_api_key("not-a-real-key") is None


# ── MFA branch ──────────────────────────────────────────────────────────────

def test_login_with_mfa_returns_session_id_then_completes(tmp_path, config):
    auth = FakeAuth(mfa=True)
    p = make_provider(tmp_path, config, auth)

    outcome = p.begin_login("user@example.com", "pw")
    assert outcome.needs_mfa is True
    assert outcome.mfa_session_id
    assert outcome.auth_code is None

    code = p.complete_mfa(outcome.mfa_session_id, "123456")
    assert auth.resumed_with == (("live-client", {"csrf": "x"}), "123456")

    api_key = p.redeem_code(code)
    session = p.session_for_api_key(api_key)
    assert session.blob == "blob-after-mfa"


def test_complete_mfa_with_bad_session_raises(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth(mfa=True))
    with pytest.raises(ExpiredLogin):
        p.complete_mfa("no-such-session", "123456")


def test_mfa_session_is_single_use(tmp_path, config):
    p = make_provider(tmp_path, config, FakeAuth(mfa=True))
    outcome = p.begin_login("user@example.com", "pw")
    p.complete_mfa(outcome.mfa_session_id, "123456")
    with pytest.raises(ExpiredLogin):
        p.complete_mfa(outcome.mfa_session_id, "123456")
