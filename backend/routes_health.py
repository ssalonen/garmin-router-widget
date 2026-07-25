"""Liveness and readiness endpoints.

/health  — process is up (no Garmin dependency).
/ready   — a token blob is present and loads into a session; 503 when the
           account hasn't been connected via /setup.

Note: /ready reflects "is a session loadable", NOT "are the tokens still
accepted by Garmin". It does not call Garmin (that would rate-limit and defeat
cheap polling), and the session is cached — so tokens that have expired
server-side still read as ready here. Actual expiry surfaces on a real course
request as 503 (GarminAuthError). Use /ready for "is the backend set up", not as
a live auth-validity check.
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
    # get_session raises 503 if no token blob is present or it won't load.
    return {"ready": True}
