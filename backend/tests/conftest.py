"""Shared test fixtures.

The garth seam is replaced by FakeAuth so no test touches the network or real
credentials. The FastAPI app resolves its OAuthProvider through the
`get_provider` dependency, which tests override with a provider wired to
FakeAuth and a temp-dir TokenStore.
"""
import pytest
from fastapi.testclient import TestClient

from garmin import LoginResult
from oauth import OAuthConfig, OAuthProvider
from store import AuthCodeStore, PendingLoginStore, TokenStore

REDIRECT_URI = "https://backend.example.com/oauth/callback"
CLIENT_ID = "garmin-router-widget"


class FakeSession:
    def __init__(self):
        self.courses: list[dict] = []
        self.points: list[dict] = []
        self.raise_exc: Exception | None = None

    def get_courses(self, limit=10):
        if self.raise_exc:
            raise self.raise_exc
        return self.courses

    def get_course_points(self, course_id):
        if self.raise_exc:
            raise self.raise_exc
        return self.points


class FakeAuth:
    """Stand-in for the garmin module's auth seam, fully scriptable."""

    def __init__(self):
        self.mfa = False
        self.begin_error: Exception | None = None
        self.session = FakeSession()
        self.begin_calls: list[tuple[str, str]] = []
        self.resumed_with = None

    def begin_login(self, email, password):
        self.begin_calls.append((email, password))
        if self.begin_error:
            raise self.begin_error
        if self.mfa:
            return LoginResult(mfa_context=("live-client", {"csrf": "x"}))
        return LoginResult(token_blob=f"blob::{email}")

    def resume_login(self, mfa_context, mfa_code):
        self.resumed_with = (mfa_context, mfa_code)
        return "blob::after-mfa"

    def session_from_tokens(self, blob):
        return self.session


@pytest.fixture
def fake_auth():
    return FakeAuth()


@pytest.fixture
def provider(tmp_path, fake_auth):
    return OAuthProvider(
        token_store=TokenStore(str(tmp_path / "tokens")),
        code_store=AuthCodeStore(),
        pending_store=PendingLoginStore(),
        config=OAuthConfig(client_id=CLIENT_ID, redirect_uris={REDIRECT_URI}),
        auth=fake_auth,
    )


@pytest.fixture
def client(provider):
    from main import app, get_provider
    app.dependency_overrides[get_provider] = lambda: provider
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_session(provider, fake_auth):
    """Seed a valid api_key whose session is the scriptable FakeSession.

    Returns (api_key, fake_session) so tests can set .courses/.points/.raise_exc.
    """
    api_key = provider._tokens.put("blob::seeded")
    return api_key, fake_auth.session
