"""Garmin Route Loader backend — application assembly.

Single-account course proxy: authenticates to Garmin with OAuth tokens minted
once via /setup (no password in env, MFA supported), and serves the widget's
course list/points. Wiring lives in deps.py; routes are split across
routes_setup / routes_courses / routes_health.
"""
from fastapi import FastAPI

import routes_courses
import routes_health
import routes_setup

app = FastAPI(title="Garmin Route Loader Backend")
app.include_router(routes_health.router)
app.include_router(routes_setup.router)
app.include_router(routes_courses.router)
