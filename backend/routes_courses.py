"""Course endpoints: per the single Garmin session, gated by the optional
X-Api-Key shared secret."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import PlainTextResponse

import garmin
from deps import REAUTH_DETAIL, get_session, require_api_key, reset_session

logger = logging.getLogger("garmin_backend")

router = APIRouter(prefix="/api", tags=["courses"])


@router.get("/courses")
def list_courses(
    limit: int = Query(default=10, le=50),
    _: None = Security(require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    try:
        courses = session.get_courses(limit=limit)
    except garmin.GarminAuthError:
        reset_session()
        raise HTTPException(status_code=503, detail=REAUTH_DETAIL)
    except Exception:
        logger.exception("Garmin course-list fetch failed")
        reset_session()  # transient upstream error; force reload next call
        raise HTTPException(status_code=502, detail="Upstream error from Garmin")
    return {"courses": courses}


@router.get("/course/{course_id}", response_class=PlainTextResponse)
def get_course(
    course_id: str,
    _: None = Security(require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    try:
        points = session.get_course_points(course_id)
    except garmin.GarminAuthError:
        reset_session()
        raise HTTPException(status_code=503, detail=REAUTH_DETAIL)
    except Exception:
        logger.exception("Garmin course-points fetch failed")
        reset_session()
        raise HTTPException(status_code=502, detail="Upstream error from Garmin")
    return PlainTextResponse(
        content=garmin.encode_points_ascii85(points),
        media_type="text/plain; charset=ascii",
    )
