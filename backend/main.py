import os

from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import Response

import garmin

app = FastAPI(title="Garmin Route Loader Backend")

_API_KEY = os.environ.get("API_KEY", "")
_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if not _API_KEY:
        return  # API_KEY not set → auth disabled (dev mode)
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/api/courses")
def list_courses(limit: int = Query(default=10, le=50), _: None = Security(_require_api_key)):
    try:
        courses = garmin.get_courses(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"courses": courses}


@app.get("/api/course/{course_id}")
def get_course(course_id: str, _: None = Security(_require_api_key)):
    try:
        points = garmin.get_course_points(course_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return Response(
        content=garmin.encode_points_binary(points),
        media_type="application/octet-stream",
    )
