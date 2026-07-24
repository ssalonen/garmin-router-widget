"""HTTP-level tests for the web bootstrap pages (/setup, /setup/login,
/setup/mfa). garth is faked via conftest.FakeAuth.

Setup is default-closed: SETUP_TOKEN must be configured and supplied. The
`enabled` autouse fixture sets it; TOKEN is threaded through each request.
"""
import re

import pytest

TOKEN = "letmein"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("SETUP_TOKEN", TOKEN)


# ── default-closed gate ──────────────────────────────────────────────────────

def test_setup_disabled_without_setup_token(client, monkeypatch):
    monkeypatch.delenv("SETUP_TOKEN", raising=False)
    assert client.get("/setup").status_code == 403
    assert client.post("/setup/login",
                       data={"email": "a@b.c", "password": "pw"}).status_code == 403


def test_setup_rejects_wrong_or_missing_token(client):
    assert client.get("/setup").status_code == 403                      # no token
    assert client.get("/setup", params={"token": "wrong"}).status_code == 403


# ── GET /setup ───────────────────────────────────────────────────────────────

def test_setup_page_renders_login_form(client):
    r = client.get("/setup", params={"token": TOKEN})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Key off the actual inputs, not prose that happens to contain "password".
    assert 'type="password"' in r.text
    assert 'name="email"' in r.text


def test_setup_page_escapes_reflected_token(client, monkeypatch):
    """token is reflected into the form — it must be HTML-escaped (XSS guard).
    Uses an XSS payload as the configured token so the gate passes."""
    payload = '"><script>alert(1)</script>'
    monkeypatch.setenv("SETUP_TOKEN", payload)
    r = client.get("/setup", params={"token": payload})
    assert r.status_code == 200
    assert "<script>alert(1)" not in r.text
    assert "&lt;script&gt;" in r.text


# ── POST /setup/login ────────────────────────────────────────────────────────

def test_login_success_writes_tokens_and_confirms(client, fake_auth, token_file):
    r = client.post("/setup/login",
                    data={"email": "rider@example.com", "password": "pw", "token": TOKEN})
    assert r.status_code == 200
    assert fake_auth.begin_calls == [("rider@example.com", "pw")]
    with open(token_file) as fh:
        assert fh.read() == "blob::rider@example.com"


def test_login_bad_credentials_reshows_form(client, fake_auth):
    fake_auth.begin_error = Exception("invalid credentials")
    r = client.post("/setup/login",
                    data={"email": "rider@example.com", "password": "bad", "token": TOKEN})
    assert r.status_code == 401
    assert 'type="password"' in r.text       # form re-rendered for retry
    assert 'class="err"' in r.text           # and the error banner is actually shown


def test_login_mfa_renders_mfa_form(client, fake_auth):
    fake_auth.mfa = True
    r = client.post("/setup/login",
                    data={"email": "rider@example.com", "password": "pw", "token": TOKEN})
    assert r.status_code == 200
    assert "mfa_session_id" in r.text
    assert "code" in r.text.lower()


def test_login_rejects_bad_setup_token(client):
    r = client.post("/setup/login",
                    data={"email": "r@example.com", "password": "pw", "token": "wrong"})
    assert r.status_code == 403


# ── POST /setup/mfa ──────────────────────────────────────────────────────────

def _start_mfa(client, fake_auth):
    fake_auth.mfa = True
    r = client.post("/setup/login",
                    data={"email": "rider@example.com", "password": "pw", "token": TOKEN})
    return re.search(r'name="mfa_session_id"\s+value="([^"]+)"', r.text).group(1)


def test_mfa_success_writes_tokens(client, fake_auth, token_file):
    sid = _start_mfa(client, fake_auth)
    r = client.post("/setup/mfa",
                    data={"mfa_code": "123456", "mfa_session_id": sid, "token": TOKEN})
    assert r.status_code == 200
    assert fake_auth.resumed_with[1] == "123456"
    with open(token_file) as fh:
        assert fh.read() == "blob::after-mfa"


def test_mfa_expired_session_is_400(client, fake_auth):
    fake_auth.mfa = True
    r = client.post("/setup/mfa",
                    data={"mfa_code": "123456", "mfa_session_id": "unknown-or-expired", "token": TOKEN})
    assert r.status_code == 400


def test_mfa_rejects_bad_setup_token(client):
    """The SETUP_TOKEN gate must guard /setup/mfa too, not only /setup/login."""
    r = client.post("/setup/mfa",
                    data={"mfa_code": "123456", "mfa_session_id": "whatever", "token": "wrong"})
    assert r.status_code == 403
