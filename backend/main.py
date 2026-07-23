"""FastAPI app: OAuth provider fronting Garmin, plus per-user course endpoints.

The widget drives makeOAuthRequest → the phone's Garmin Connect Mobile opens the
authorize page → the user signs in (email/password, then MFA code from the
phone) → we redirect back with an auth code → the widget exchanges it for an
access token (its X-Api-Key) → course reads run against that user's Garmin
session. No shared credentials; each user's Garmin tokens live server-side keyed
by their opaque api_key.
"""
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security.api_key import APIKeyHeader

import garmin
from oauth import ExpiredLogin, OAuthProvider, provider_from_env

app = FastAPI(title="Garmin Route Loader Backend")

_provider: OAuthProvider | None = None


def get_provider() -> OAuthProvider:
    """App-level provider, lazily built from env. Overridden in tests."""
    global _provider
    if _provider is None:
        _provider = provider_from_env()
    return _provider


# ── HTML forms (minimal, self-contained; rendered inside the phone webview) ──

def _login_form(redirect_uri: str, state: str, error: str = "") -> str:
    err = f'<p class="err">{error}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in with Garmin</title>
<style>body{{font-family:sans-serif;max-width:22rem;margin:2rem auto;padding:0 1rem}}
input{{width:100%;padding:.6rem;margin:.4rem 0;box-sizing:border-box}}
button{{width:100%;padding:.7rem;font-size:1rem}}.err{{color:#b00}}</style></head>
<body><h2>Sign in with Garmin</h2>{err}
<form method="post" action="/oauth/login">
<input type="email" name="email" placeholder="Garmin email" required autofocus>
<input type="password" name="password" placeholder="Password" required>
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<button type="submit">Sign in</button></form>
<p><small>Your credentials go only to Garmin to mint an access token; they are
not stored by this service.</small></p></body></html>"""


def _mfa_form(mfa_session_id: str, redirect_uri: str, state: str, error: str = "") -> str:
    err = f'<p class="err">{error}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enter security code</title>
<style>body{{font-family:sans-serif;max-width:22rem;margin:2rem auto;padding:0 1rem}}
input{{width:100%;padding:.6rem;margin:.4rem 0;box-sizing:border-box}}
button{{width:100%;padding:.7rem;font-size:1rem}}.err{{color:#b00}}</style></head>
<body><h2>Enter security code</h2>
<p>Garmin sent a verification code to your phone or email.</p>{err}
<form method="post" action="/oauth/mfa">
<input type="text" name="mfa_code" placeholder="6-digit code" inputmode="numeric"
       autocomplete="one-time-code" required autofocus>
<input type="hidden" name="mfa_session_id" value="{mfa_session_id}">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<button type="submit">Verify</button></form></body></html>"""


def _redirect_with_code(redirect_uri: str, code: str, state: str) -> RedirectResponse:
    query = urlencode({"code": code, "state": state})
    return RedirectResponse(url=f"{redirect_uri}?{query}", status_code=302)


# ── OAuth provider endpoints ─────────────────────────────────────────────────

@app.get("/oauth/authorize", response_class=HTMLResponse)
def authorize(
    response_type: str = Query(default="code"),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(default=""),
    provider: OAuthProvider = Depends(get_provider),
):
    if not provider.validate_authorization(client_id, redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid client_id or redirect_uri")
    return HTMLResponse(_login_form(redirect_uri, state))


@app.post("/oauth/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(default=""),
    provider: OAuthProvider = Depends(get_provider),
):
    # redirect_uri is attacker-controllable in a POST body — re-validate it.
    if not provider.validate_authorization(provider._config.client_id, redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    try:
        outcome = provider.begin_login(email, password)
    except Exception:
        return HTMLResponse(
            _login_form(redirect_uri, state, error="Sign-in failed. Check your credentials."),
            status_code=401,
        )
    if outcome.needs_mfa:
        return HTMLResponse(_mfa_form(outcome.mfa_session_id, redirect_uri, state))
    return _redirect_with_code(redirect_uri, outcome.auth_code, state)


@app.post("/oauth/mfa")
def mfa(
    mfa_code: str = Form(...),
    mfa_session_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(default=""),
    provider: OAuthProvider = Depends(get_provider),
):
    if not provider.validate_authorization(provider._config.client_id, redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    try:
        code = provider.complete_mfa(mfa_session_id, mfa_code)
    except ExpiredLogin:
        raise HTTPException(status_code=400, detail="Login session expired; start over")
    except Exception:
        return HTMLResponse(
            _mfa_form(mfa_session_id, redirect_uri, state, error="Incorrect code. Try again."),
            status_code=401,
        )
    return _redirect_with_code(redirect_uri, code, state)


@app.post("/api/token")
async def token(request: Request, provider: OAuthProvider = Depends(get_provider)):
    # Accept the code as JSON {"code": …} or form-encoded, whichever the widget sends.
    code = None
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        code = body.get("code") if isinstance(body, dict) else None
    else:
        form = await request.form()
        code = form.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    api_key = provider.redeem_code(code)
    if api_key is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"access_token": api_key, "token_type": "bearer"}


# ── Course endpoints (per-user, via X-Api-Key → Garmin session) ──────────────

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def require_session(
    api_key: str | None = Depends(_api_key_header),
    provider: OAuthProvider = Depends(get_provider),
):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Api-Key")
    session = provider.session_for_api_key(api_key)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return session


@app.get("/api/courses")
def list_courses(
    limit: int = Query(default=10, le=50),
    session=Depends(require_session),
):
    try:
        courses = session.get_courses(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"courses": courses}


@app.get("/api/course/{course_id}", response_class=PlainTextResponse)
def get_course(course_id: str, session=Depends(require_session)):
    try:
        points = session.get_course_points(course_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return PlainTextResponse(
        content=garmin.encode_points_ascii85(points),
        media_type="text/plain; charset=ascii",
    )
