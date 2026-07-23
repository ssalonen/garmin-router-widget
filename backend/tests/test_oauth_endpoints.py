"""HTTP-level tests for the OAuth provider endpoints.

Covers the browser-facing authorize/login/mfa forms and the machine-facing
token exchange. garth is faked (conftest.FakeAuth), so the Garmin login is
simulated but every route, redirect, and status code is real.
"""
from urllib.parse import parse_qs, urlparse

from .conftest import CLIENT_ID, REDIRECT_URI


def _authorize_url(redirect=REDIRECT_URI, client=CLIENT_ID, state="xyz"):
    return f"/oauth/authorize?response_type=code&client_id={client}&redirect_uri={redirect}&state={state}"


# ── GET /oauth/authorize ─────────────────────────────────────────────────────

def test_authorize_renders_login_form(client):
    r = client.get(_authorize_url())
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text.lower()
    assert "password" in body and "email" in body
    # carries redirect_uri + state forward so POST /oauth/login can complete
    assert REDIRECT_URI in r.text
    assert "xyz" in r.text


def test_authorize_rejects_unregistered_redirect(client):
    r = client.get(_authorize_url(redirect="https://evil.example.com/steal"))
    assert r.status_code == 400


def test_authorize_rejects_unknown_client(client):
    r = client.get(_authorize_url(client="not-our-widget"))
    assert r.status_code == 400


# ── POST /oauth/login ────────────────────────────────────────────────────────

def test_login_success_redirects_with_code(client, fake_auth):
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = urlparse(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == REDIRECT_URI
    q = parse_qs(loc.query)
    assert q["state"] == ["xyz"]
    assert q["code"][0]  # non-empty authorization code
    assert fake_auth.begin_calls == [("u@example.com", "pw")]


def test_login_rejects_tampered_redirect(client):
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "pw",
              "redirect_uri": "https://evil.example.com/cb", "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_login_bad_credentials_reshows_form_with_error(client, fake_auth):
    fake_auth.begin_error = Exception("invalid credentials")
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "wrong",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "text/html" in r.headers["content-type"]
    # form is re-rendered so the user can retry
    assert "password" in r.text.lower()


def test_login_mfa_renders_mfa_form(client, fake_auth):
    fake_auth.mfa = True
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text.lower()
    assert "code" in body  # MFA code entry
    # session id + redirect + state carried into the MFA form
    assert "mfa_session_id" in r.text
    assert REDIRECT_URI in r.text and "xyz" in r.text


# ── POST /oauth/mfa ──────────────────────────────────────────────────────────

def _start_mfa(client, fake_auth):
    fake_auth.mfa = True
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    # extract mfa_session_id from the hidden field in the returned form
    import re
    m = re.search(r'name="mfa_session_id"\s+value="([^"]+)"', r.text)
    assert m, "mfa_session_id not found in MFA form"
    return m.group(1)


def test_mfa_success_redirects_with_code(client, fake_auth):
    sid = _start_mfa(client, fake_auth)
    r = client.post(
        "/oauth/mfa",
        data={"mfa_code": "123456", "mfa_session_id": sid,
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code"][0]
    assert q["state"] == ["xyz"]
    assert fake_auth.resumed_with[1] == "123456"


def test_mfa_expired_session_is_400(client, fake_auth):
    fake_auth.mfa = True
    r = client.post(
        "/oauth/mfa",
        data={"mfa_code": "123456", "mfa_session_id": "expired-or-unknown",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    assert r.status_code == 400


# ── POST /api/token ──────────────────────────────────────────────────────────

def _code_from_login(client):
    r = client.post(
        "/oauth/login",
        data={"email": "u@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "xyz"},
        follow_redirects=False,
    )
    return parse_qs(urlparse(r.headers["location"]).query)["code"][0]


def test_token_exchange_returns_access_token(client):
    code = _code_from_login(client)
    r = client.post("/api/token", json={"code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"


def test_token_exchange_code_is_single_use(client):
    code = _code_from_login(client)
    assert client.post("/api/token", json={"code": code}).status_code == 200
    assert client.post("/api/token", json={"code": code}).status_code == 400


def test_token_exchange_unknown_code_is_400(client):
    assert client.post("/api/token", json={"code": "never-issued"}).status_code == 400


def test_access_token_works_on_courses(client, fake_auth):
    """The token minted via the full flow authenticates the course endpoint."""
    fake_auth.session.courses = [{"id": "1", "name": "Loop", "distanceKm": 5.0}]
    code = _code_from_login(client)
    token = client.post("/api/token", json={"code": code}).json()["access_token"]
    r = client.get("/api/courses", headers={"X-Api-Key": token})
    assert r.status_code == 200
    assert r.json()["courses"][0]["id"] == "1"
