"""Course endpoints: per the single Garmin session, gated by the optional
X-Api-Key shared secret."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import Response

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


@router.get("/course/{course_id}")
def get_course_fit(
    course_id: str,
    name: str = Query(default="", max_length=63),
    lean: bool = Query(default=True),
    _: None = Security(require_api_key),
    session: garmin.GarminSession = Depends(get_session),
):
    """Serve the course as a FIT Course file.

    This is the only format the device can consume: the widget requests it with
    `HTTP_RESPONSE_CONTENT_TYPE_FIT`, and Connect IQ parses and stores it as
    device course content, reachable from Navigation > Courses. `name` comes
    from the widget (it already has it from the list response) and becomes the
    name shown in that menu.

    Records are lean by default — positions only, 9.16 B/pt, verified accepted
    by the edge530 simulator. `?lean=0` switches to full records (timestamp and
    distance, 17.16 B/pt) without a widget rebuild, which is the escape hatch
    if a physical device turns out to be stricter than the simulator.
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
