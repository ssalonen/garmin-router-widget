"""End-to-end OAuth journey through the real HTTP stack.

Only the garth boundary is faked (conftest.FakeAuth). Everything else — routing,
the authorize/login/mfa forms, the redirect with the auth code, the token
exchange, and an authenticated course fetch — is exercised exactly as the widget
+ Garmin Connect Mobile webview would drive it.

    makeOAuthRequest → GET /oauth/authorize   (webview opens on phone)
                       POST /oauth/login       (user enters Garmin creds)
                       [POST /oauth/mfa]        (user enters phone code)
                    → 302 redirect_uri?code=…  (CIQ intercepts, hands code to widget)
    widget          → POST /api/token {code}   → access_token
                    → GET  /api/courses (X-Api-Key: access_token)
"""
import base64
import re
import struct
from urllib.parse import parse_qs, urlparse

from .conftest import CLIENT_ID, REDIRECT_URI


def _decode_ascii85_points(text: str) -> list[dict]:
    data = base64.a85decode(text, adobe=False)
    return [
        {
            "lat": struct.unpack(">i", data[i:i+4])[0] / 1e7,
            "lon": struct.unpack(">i", data[i+4:i+8])[0] / 1e7,
        }
        for i in range(0, len(data) - 7, 8)
    ]


def _authorize(client):
    r = client.get(
        f"/oauth/authorize?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&state=st8"
    )
    assert r.status_code == 200
    return r


def _code_from_redirect(resp) -> str:
    assert resp.status_code == 302
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["state"] == ["st8"]
    return q["code"][0]


def test_e2e_full_flow_no_mfa(client, fake_auth):
    fake_auth.session.courses = [
        {"id": "111222333", "name": "Morning Trail", "distanceKm": 12.3},
    ]
    fake_auth.session.points = [{"lat": 60.1699, "lon": 24.9384}]

    _authorize(client)

    login = client.post(
        "/oauth/login",
        data={"email": "rider@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "st8"},
        follow_redirects=False,
    )
    code = _code_from_redirect(login)

    token = client.post("/api/token", json={"code": code}).json()["access_token"]
    hdr = {"X-Api-Key": token}

    courses = client.get("/api/courses", headers=hdr)
    assert courses.status_code == 200
    assert courses.json()["courses"][0]["name"] == "Morning Trail"

    points = client.get("/api/course/111222333", headers=hdr)
    assert points.status_code == 200
    decoded = _decode_ascii85_points(points.text)
    assert abs(decoded[0]["lat"] - 60.1699) < 1e-6


def test_e2e_full_flow_with_mfa(client, fake_auth):
    fake_auth.mfa = True
    fake_auth.session.courses = [{"id": "9", "name": "MFA Route", "distanceKm": 3.0}]

    _authorize(client)

    login = client.post(
        "/oauth/login",
        data={"email": "rider@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "st8"},
        follow_redirects=False,
    )
    assert login.status_code == 200  # MFA form, not a redirect
    sid = re.search(r'name="mfa_session_id"\s+value="([^"]+)"', login.text).group(1)

    mfa = client.post(
        "/oauth/mfa",
        data={"mfa_code": "654321", "mfa_session_id": sid,
              "redirect_uri": REDIRECT_URI, "state": "st8"},
        follow_redirects=False,
    )
    code = _code_from_redirect(mfa)
    assert fake_auth.resumed_with[1] == "654321"

    token = client.post("/api/token", json={"code": code}).json()["access_token"]
    courses = client.get("/api/courses", headers={"X-Api-Key": token})
    assert courses.status_code == 200
    assert courses.json()["courses"][0]["name"] == "MFA Route"


def test_e2e_two_users_get_isolated_sessions(client, provider, fake_auth):
    """Two independent logins mint two distinct api_keys → two token blobs."""
    code1 = _code_from_redirect(client.post(
        "/oauth/login",
        data={"email": "a@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "st8"},
        follow_redirects=False,
    ))
    code2 = _code_from_redirect(client.post(
        "/oauth/login",
        data={"email": "b@example.com", "password": "pw",
              "redirect_uri": REDIRECT_URI, "state": "st8"},
        follow_redirects=False,
    ))
    key1 = client.post("/api/token", json={"code": code1}).json()["access_token"]
    key2 = client.post("/api/token", json={"code": code2}).json()["access_token"]
    assert key1 != key2
    # each key resolves to its own stored blob
    assert provider._tokens.get(key1) == "blob::a@example.com"
    assert provider._tokens.get(key2) == "blob::b@example.com"
