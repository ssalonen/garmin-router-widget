"""Shared test fixtures.

The single Garmin session and the setup service are both replaced via
dependency overrides, so no test touches the network, credentials, or a real
token file. API_KEY defaults to unset (dev mode) unless a test sets it.
"""
import pytest
from fastapi.testclient import TestClient

from garmin import LoginResult


class FakeSession:
    def __init__(self):
        self.courses: list[dict] = []
        self.points: list[dict] = []
        self.raise_exc: Exception | None = None

    def get_courses(self, limit=10, offset=0):
        if self.raise_exc:
            raise self.raise_exc
        return self.courses

    def get_course_points(self, course_id):
        if self.raise_exc:
            raise self.raise_exc
        return self.points


class FakeAuth:
    """Scriptable stand-in for the garmin auth seam used by SetupService."""

    def __init__(self):
        self.mfa = False
        self.begin_error: Exception | None = None
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


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def fake_auth():
    return FakeAuth()


@pytest.fixture
def token_file(tmp_path):
    return str(tmp_path / "tokens.blob")


@pytest.fixture
def setup_service(fake_auth, token_file):
    from bootstrap import PendingLogins, SetupService
    return SetupService(token_file, auth=fake_auth, pending=PendingLogins())


@pytest.fixture(autouse=True)
def _dev_mode(monkeypatch):
    # Default to the api-key gate disabled and setup disabled unless a test
    # opts in (setup is default-closed).
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("SETUP_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def _clean_module_state():
    # Reset the process-global session/setup-service caches around every test so
    # a session built by the real get_session (integration tests) can't leak
    # into a later test.
    import deps
    deps.reset_session()
    deps._setup_service = None
    yield
    deps.reset_session()
    deps._setup_service = None


@pytest.fixture
def client(fake_session, setup_service):
    import deps
    from main import app
    app.dependency_overrides[deps.get_session] = lambda: fake_session
    app.dependency_overrides[deps.get_setup_service] = lambda: setup_service
    yield TestClient(app)
    app.dependency_overrides.clear()
