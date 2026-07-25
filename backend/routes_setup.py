"""Web bootstrap routes: one-time Garmin sign-in (email/password + phone MFA).

Default-closed: /setup is disabled unless SETUP_TOKEN is configured, since these
pages accept a Garmin password and overwrite the account's tokens. The setup
token is submitted as a form field on POST (never a URL query param), so it does
not leak into access logs / history. GET /setup just serves the form.
"""
import os
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse

import templates
from bootstrap import ExpiredLogin, SetupService
from deps import get_setup_service, reset_session

router = APIRouter(tags=["setup"])


def _setup_secret() -> str:
    return os.environ.get("SETUP_TOKEN", "")


def _ensure_setup_enabled() -> None:
    if not _setup_secret():
        raise HTTPException(
            status_code=403,
            detail="Setup is disabled. Set SETUP_TOKEN on the backend to enable /setup.",
        )


def require_setup_token(provided: str) -> None:
    _ensure_setup_enabled()
    if not secrets.compare_digest(provided or "", _setup_secret()):
        raise HTTPException(status_code=403, detail="Invalid setup token")


@router.get("/setup", response_class=HTMLResponse)
def setup_page():
    _ensure_setup_enabled()
    return HTMLResponse(templates.login_form())


@router.post("/setup/login")
def setup_login(
    email: str = Form(...),
    password: str = Form(...),
    token: str = Form(default=""),
    service: SetupService = Depends(get_setup_service),
):
    require_setup_token(token)
    try:
        outcome = service.begin(email, password)
    except Exception:
        return HTMLResponse(
            templates.login_form(error="Sign-in failed. Re-enter the setup token and your credentials."),
            status_code=401,
        )
    if not outcome.done:
        return HTMLResponse(templates.mfa_form(outcome.mfa_session_id, token))
    reset_session()  # pick up the freshly written tokens on the next request
    return HTMLResponse(templates.done_page())


@router.post("/setup/mfa")
def setup_mfa(
    mfa_code: str = Form(...),
    mfa_session_id: str = Form(...),
    token: str = Form(default=""),
    service: SetupService = Depends(get_setup_service),
):
    require_setup_token(token)
    try:
        service.complete_mfa(mfa_session_id, mfa_code)
    except ExpiredLogin:
        raise HTTPException(status_code=400, detail="Setup session expired; start over at /setup")
    except Exception:
        return HTMLResponse(
            templates.mfa_form(mfa_session_id, token, error="Incorrect code. Try again."),
            status_code=401,
        )
    reset_session()
    return HTMLResponse(templates.done_page())
