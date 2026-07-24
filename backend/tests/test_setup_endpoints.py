"""HTTP-level tests for the web bootstrap pages (/setup, /setup/login,
/setup/mfa). garth is faked via conftest.FakeAuth."""
import re


# ── GET /setup ───────────────────────────────────────────────────────────────

def test_setup_page_renders_login_form(client):
    r = client.get("/setup")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Key off the actual inputs, not prose that happens to contain "password".
    assert 'type="password"' in r.text
    assert 'name="email"' in r.text


def test_setup_page_escapes_reflected_token(client):
    """token is attacker-controllable and reflected into the form — it must be
    HTML-escaped (reflected-XSS guard), even in the default open mode."""
    r = client.get("/setup", params={"token": '"><script>alert(1)</script>'})
    assert r.status_code == 200
    assert "<script>alert(1)" not in r.text
    assert "&lt;script&gt;" in r.text


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
    assert 'type="password"' in r.text       # form re-rendered for retry
    assert 'class="err"' in r.text           # and the error banner is actually shown


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


def test_mfa_rejects_bad_setup_token(client, monkeypatch):
    """The SETUP_TOKEN gate must guard /setup/mfa too, not only /setup/login."""
    monkeypatch.setenv("SETUP_TOKEN", "letmein")
    r = client.post(
        "/setup/mfa",
        data={"mfa_code": "123456", "mfa_session_id": "whatever", "token": "wrong"},
    )
    assert r.status_code == 403
