"""Shared test fixtures.

The single Garmin session is replaced by FakeSession via the get_session
dependency override, so no test touches the network, credentials, or a token
file. API_KEY defaults to unset (dev mode) unless a test sets it.
"""
import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture(autouse=True)
def _dev_mode(monkeypatch):
    # Default to auth-disabled unless a test opts in.
    monkeypatch.delenv("API_KEY", raising=False)


@pytest.fixture
def client(fake_session):
    from main import app, get_session
    app.dependency_overrides[get_session] = lambda: fake_session
    yield TestClient(app)
    app.dependency_overrides.clear()
