"""FastAPI app: single-account course proxy.

Authenticates to Garmin with garth tokens minted once by login.py (no password
in env, MFA supported). The widget reaches the backend with an optional shared
X-Api-Key secret; the backend then talks to Garmin as the one account whose
tokens are on disk.
"""
import os
import threading

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Security
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security.api_key import APIKeyHeader

import garmin
from setup import ExpiredLogin, SetupService

app = FastAPI(title="Garmin Route Loader Backend")

_TOKEN_FILE = os.environ.get("GARMIN_TOKEN_FILE", "garmin_tokens.blob")

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

_session: garmin.GarminSession | None = None
_lock = threading.Lock()

_setup_service: SetupService | None = None


def get_setup_service() -> SetupService:
    """App-level setup service, lazily built. Overridden in tests."""
    global _setup_service
    if _setup_service is None:
        _setup_service = SetupService(_TOKEN_FILE)
    return _setup_service


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    # Read API_KEY dynamically so it is configurable per-process/test.
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return  # unset → auth disabled (dev / trusted-network mode)
    if key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_session() -> garmin.GarminSession:
    """Lazily build the single Garmin session from the on-disk token blob.

    Overridden in tests. Cached so garth loads the tokens once per process.
    """
    global _session
    with _lock:
        if _session is None:
            try:
                with open(_TOKEN_FILE, encoding="utf-8") as fh:
                    blob = fh.read()
            except FileNotFoundError:
                raise HTTPException(
                    status_code=503,
                    detail="Backend not authenticated. Run login.py to mint Garmin tokens.",
                )
            _session = garmin.session_from_tokens(blob)
    return _session


def _reset_session() -> None:
    global _session
    with _lock:
        _session = None


# ── Web bootstrap (one-time Garmin sign-in) ──────────────────────────────────

_SETUP_STYLE = (
    "body{font-family:sans-serif;max-width:22rem;margin:2rem auto;padding:0 1rem}"
    "input{width:100%;padding:.6rem;margin:.4rem 0;box-sizing:border-box}"
    "button{width:100%;padding:.7rem;font-size:1rem}.err{color:#b00}"
)


def _check_setup_token(provided: str) -> None:
    expected = os.environ.get("SETUP_TOKEN", "")
    if expected and provided != expected:
        raise HTTPException(status_code=403, detail="Invalid setup token")


def _login_form(token: str, error: str = "") -> str:
    err = f'<p class="err">{error}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect your Garmin account</title><style>{_SETUP_STYLE}</style></head>
<body><h2>Connect your Garmin account</h2>{err}
<form method="post" action="/setup/login">
<input type="email" name="email" placeholder="Garmin email" required autofocus>
<input type="password" name="password" placeholder="Password" required>
<input type="hidden" name="token" value="{token}">
<button type="submit">Connect</button></form>
<p><small>Your password is used only to mint Garmin access tokens and is never
stored.</small></p></body></html>"""


def _mfa_form(mfa_session_id: str, token: str, error: str = "") -> str:
    err = f'<p class="err">{error}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enter security code</title><style>{_SETUP_STYLE}</style></head>
<body><h2>Enter security code</h2>
<p>Garmin sent a verification code to your phone or email.</p>{err}
<form method="post" action="/setup/mfa">
<input type="text" name="mfa_code" placeholder="6-digit code" inputmode="numeric"
       autocomplete="one-time-code" required autofocus>
<input type="hidden" name="mfa_session_id" value="{mfa_session_id}">
<input type="hidden" name="token" value="{token}">
<button type="submit">Verify</button></form></body></html>"""


def _done_page() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Connected</title><style>{_SETUP_STYLE}</style></head>
<body><h2>✅ Connected</h2>
<p>Garmin tokens saved. The widget can now load your courses.</p></body></html>"""


@app.get("/setup", response_class=HTMLResponse)
def setup_page(token: str = Query(default="")):
    _check_setup_token(token)
    return HTMLResponse(_login_form(token))


@app.post("/setup/login")
def setup_login(
    email: str = Form(...),
    password: str = Form(...),
    token: str = Form(default=""),
    service: SetupService = Depends(get_setup_service),
):
    _check_setup_token(token)
    try:
        outcome = service.begin(email, password)
    except Exception:
        return HTMLResponse(
            _login_form(token, error="Sign-in failed. Check your credentials."),
            status_code=401,
        )
    if not outcome.done:
        return HTMLResponse(_mfa_form(outcome.mfa_session_id, token))
    _reset_session()  # pick up the freshly written tokens on the next request
    return HTMLResponse(_done_page())


@app.post("/setup/mfa")
def setup_mfa(
    mfa_code: str = Form(...),
    mfa_session_id: str = Form(...),
    token: str = Form(default=""),
    service: SetupService = Depends(get_setup_service),
):
    _check_setup_token(token)
    try:
        service.complete_mfa(mfa_session_id, mfa_code)
    except ExpiredLogin:
        raise HTTPException(status_code=400, detail="Setup session expired; start over at /setup")
    except Exception:
        return HTMLResponse(
            _mfa_form(mfa_session_id, token, error="Incorrect code. Try again."),
            status_code=401,
        )
    _reset_session()
    return HTMLResponse(_done_page())


# ── Course endpoints ─────────────────────────────────────────────────────────

@app.get("/api/courses")
def list_courses(
    limit: int = Query(default=10, le=50),
    _: None = Security(_require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    try:
        courses = session.get_courses(limit=limit)
    except Exception as e:
        _reset_session()  # tokens may have expired; force reload next call
        raise HTTPException(status_code=502, detail=str(e))
    return {"courses": courses}


@app.get("/api/course/{course_id}", response_class=PlainTextResponse)
def get_course(
    course_id: str,
    _: None = Security(_require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    try:
        points = session.get_course_points(course_id)
    except Exception as e:
        _reset_session()
        raise HTTPException(status_code=502, detail=str(e))
    return PlainTextResponse(
        content=garmin.encode_points_ascii85(points),
        media_type="text/plain; charset=ascii",
    )
