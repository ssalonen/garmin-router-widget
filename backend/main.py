"""FastAPI app: single-account course proxy.

Authenticates to Garmin with garth tokens minted once by login.py (no password
in env, MFA supported). The widget reaches the backend with an optional shared
X-Api-Key secret; the backend then talks to Garmin as the one account whose
tokens are on disk.
"""
import os
import threading

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.responses import PlainTextResponse
from fastapi.security.api_key import APIKeyHeader

import garmin

app = FastAPI(title="Garmin Route Loader Backend")

_TOKEN_FILE = os.environ.get("GARMIN_TOKEN_FILE", "garmin_tokens.blob")

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

_session: garmin.GarminSession | None = None
_lock = threading.Lock()


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
