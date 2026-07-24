"""Liveness and readiness endpoints.

/health  — process is up (no Garmin dependency).
/ready   — the Garmin session is loadable (tokens present and valid); returns
           503 otherwise, so operators can monitor auth state without making a
           real course request.
"""
from fastapi import APIRouter, Depends

import garmin
from deps import get_session

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(session: garmin.GarminSession = Depends(get_session)):
    # If get_session can't load a valid session it raises 503 before we get here.
    return {"ready": True}
