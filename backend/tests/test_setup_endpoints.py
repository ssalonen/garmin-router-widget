"""HTTP-level tests for the web bootstrap pages (/setup, /setup/login,
/setup/mfa). garth is faked via conftest.FakeAuth."""
import re


# ── GET /setup ───────────────────────────────────────────────────────────────

def test_setup_page_renders_login_form(client):
    r = client.get("/setup")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text.lower()
    assert "email" in body and "password" in body


def test_setup_page_gated_by_setup_token(client, monkeypatch):
    monkeypatch.setenv("SETUP_TOKEN", "letmein")
    assert client.get("/setup").status_code == 403
    assert client.get("/setup", params={"token": "wrong"}).status_code == 403
    r = client.get("/setup", params={"token": "letmein"})
    assert r.status_code == 200
    assert "letmein" in r.text  # carried into the form for the POST


# ── POST /setup/login ────────────────────────────────────────────────────────

def test_login_success_writes_tokens_and_confirms(client, fake_auth, token_file):
    r = client.post("/setup/login", data={"email": "rider@example.com", "password": "pw"})
    assert r.status_code == 200
    assert fake_auth.begin_calls == [("rider@example.com", "pw")]
    with open(token_file) as fh:
        assert fh.read() == "blob::rider@example.com"


def test_login_bad_credentials_reshows_form(client, fake_auth):
    fake_auth.begin_error = Exception("invalid credentials")
    r = client.post("/setup/login", data={"email": "rider@example.com", "password": "bad"})
    assert r.status_code == 401
    assert "password" in r.text.lower()


def test_login_mfa_renders_mfa_form(client, fake_auth):
    fake_auth.mfa = True
    r = client.post("/setup/login", data={"email": "rider@example.com", "password": "pw"})
    assert r.status_code == 200
    assert "mfa_session_id" in r.text
    assert "code" in r.text.lower()


def test_login_rejects_bad_setup_token(client, monkeypatch):
    monkeypatch.setenv("SETUP_TOKEN", "letmein")
    r = client.post(
        "/setup/login",
        data={"email": "r@example.com", "password": "pw", "token": "wrong"},
    )
    assert r.status_code == 403


# ── POST /setup/mfa ──────────────────────────────────────────────────────────

def _start_mfa(client, fake_auth):
    fake_auth.mfa = True
    r = client.post("/setup/login", data={"email": "rider@example.com", "password": "pw"})
    return re.search(r'name="mfa_session_id"\s+value="([^"]+)"', r.text).group(1)


def test_mfa_success_writes_tokens(client, fake_auth, token_file):
    sid = _start_mfa(client, fake_auth)
    r = client.post("/setup/mfa", data={"mfa_code": "123456", "mfa_session_id": sid})
    assert r.status_code == 200
    assert fake_auth.resumed_with[1] == "123456"
    with open(token_file) as fh:
        assert fh.read() == "blob::after-mfa"


def test_mfa_expired_session_is_400(client, fake_auth):
    fake_auth.mfa = True
    r = client.post(
        "/setup/mfa",
        data={"mfa_code": "123456", "mfa_session_id": "unknown-or-expired"},
    )
    assert r.status_code == 400
