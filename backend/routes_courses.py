"""Course endpoints: per the single Garmin session, gated by the optional
X-Api-Key shared secret."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import PlainTextResponse, Response

import fit
import garmin
from deps import REAUTH_DETAIL, get_session, require_api_key, reset_session

logger = logging.getLogger("garmin_backend")

router = APIRouter(prefix="/api", tags=["courses"])


@router.get("/courses")
def list_courses(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    _: None = Security(require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    try:
        courses = session.get_courses(limit=limit, offset=offset)
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


@router.get("/course/{course_id}/fit")
def get_course_fit(
    course_id: str,
    name: str = Query(default="", max_length=63),
    lean: bool = Query(default=False),
    _: None = Security(require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    """Serve the course as a FIT Course file.

    This is the format the device can actually consume: the widget requests it
    with `HTTP_RESPONSE_CONTENT_TYPE_FIT`, and Connect IQ parses and stores it
    as device course content. `name` comes from the widget (it already has it
    from the list response) and becomes the name shown in Navigation > Courses.

    `lean=1` omits per-record timestamp and distance — 9 B/pt instead of 17.
    Only use it if the device is confirmed to accept it.
    """
    try:
        points = session.get_course_points(course_id)
    except garmin.GarminAuthError:
        reset_session()
        raise HTTPException(status_code=503, detail=REAUTH_DETAIL)
    except Exception:
        logger.exception("Garmin course-points fetch failed")
        reset_session()
        raise HTTPException(status_code=502, detail="Upstream error from Garmin")

    if not points:
        raise HTTPException(status_code=404, detail="Course has no points")

    blob = fit.encode_course_fit(name or f"Course {course_id}", points, lean=lean)
    logger.info(
        "Encoded FIT course id=%s points=%d bytes=%d lean=%s",
        course_id, len(points), len(blob), lean,
    )
    return Response(
        content=blob,
        media_type="application/vnd.ant.fit",
        headers={"Content-Disposition": f'attachment; filename="course_{course_id}.fit"'},
    )
