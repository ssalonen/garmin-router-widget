from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

import garmin
import storage

app = FastAPI(title="Garmin Route Loader Backend")


@app.get("/api/courses")
def list_courses(limit: int = Query(default=10, le=50)):
    try:
        courses = garmin.get_courses(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"courses": courses}


@app.get("/api/course/{course_id}")
def get_course(course_id: str, thin_m: int = Query(default=15, ge=5, le=500)):
    try:
        points = garmin.get_course_points(course_id, thin_m=thin_m)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return Response(
        content=garmin.encode_points_binary(points),
        media_type="application/octet-stream",
    )


@app.post("/api/log")
def receive_log(payload: dict):
    storage.save_log(payload)
    return {"ok": True}


@app.get("/api/logs")
def get_logs(
    n: int = Query(default=50, le=500),
    level: str | None = Query(default=None),
):
    return {"logs": storage.get_recent_logs(n=n, level_filter=level)}
