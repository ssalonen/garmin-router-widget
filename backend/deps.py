"""Shared application state and FastAPI dependencies.

Centralises the single cached Garmin session, the setup-service singleton, and
the widget→backend API-key gate, so the route modules stay thin. All the module
globals here are process-local — see NOTES.md on the single-worker constraint.
"""
import os
import secrets
import threading

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

import garmin
from bootstrap import SetupService

# Path to the Garmin token blob written by /setup, resolved once at import from
# GARMIN_TOKEN_FILE. (Unlike API_KEY/SETUP_TOKEN, which are read per-request,
# this is fixed at startup; tests override get_session/get_setup_service or
# monkeypatch this module attribute directly.)
TOKEN_FILE = os.environ.get("GARMIN_TOKEN_FILE", "garmin_tokens.blob")

# 503 detail shared by every "reconnect the Garmin account" path (no tokens,
# invalid tokens, or expired-at-call-time). The widget keys off the 503 status.
REAUTH_DETAIL = "Garmin login expired. Visit /setup to reconnect your account."

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

_session: garmin.GarminSession | None = None
_lock = threading.Lock()

_setup_service: SetupService | None = None


def require_api_key(key: str | None = Security(_api_key_header)) -> None:
    """Optional widget→backend shared secret. Read API_KEY dynamically."""
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return  # unset → auth disabled (dev / trusted-network mode)
    if key is None or not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_session() -> garmin.GarminSession:
    """Lazily build the single Garmin session from the on-disk token blob.

    Overridden in tests. Cached so the tokens are loaded once per process.
    """
    global _session
    with _lock:
        if _session is None:
            try:
                with open(TOKEN_FILE, encoding="utf-8") as fh:
                    blob = fh.read()
            except FileNotFoundError:
                raise HTTPException(
                    status_code=503,
                    detail="Backend not connected. Visit /setup to connect your Garmin account.",
                )
            try:
                _session = garmin.session_from_tokens(blob)
            except Exception:
                # Present but unusable (corrupt/truncated/expired) → defined 503,
                # and leave _session unset so a later /setup can recover.
                raise HTTPException(
                    status_code=503,
                    detail="Stored Garmin tokens are invalid. Visit /setup to reconnect.",
                )
    return _session


def reset_session() -> None:
    global _session
    with _lock:
        _session = None


def get_setup_service() -> SetupService:
    """App-level setup service, lazily built. Overridden in tests."""
    global _setup_service
    if _setup_service is None:
        _setup_service = SetupService(TOKEN_FILE)
    return _setup_service
