"""Garmin Connect access, split into two concerns:

  - Auth seam (begin_login / resume_login / session_from_tokens): the *only*
    place that drives garth's SSO OAuth flow. Returns opaque token blobs so the
    rest of the app never touches credentials.
  - GarminSession: course reads against an already-authenticated client.
  - Pure encoders: the wire format for the widget.

garth performs the real Garmin OAuth1+OAuth2 token exchange under the hood;
`return_on_mfa` surfaces the phone-delivered MFA step so the web login flow can
complete it interactively.
"""
import base64
import struct

from garminconnect import Garmin, GarminConnectAuthenticationError


class GarminAuthError(Exception):
    """The stored Garmin tokens are no longer valid (expired/revoked) and the
    account must be reconnected via /setup. Distinct from a transient upstream
    error so the widget can show a re-auth message instead of a generic one."""

# Garmin Connect API endpoints (unofficial; may change without notice)
_COURSE_LIST_PATH = "/course-service/course/favorites/"
_COURSE_PATH = "/course-service/course/{id}"

_MFA_REQUIRED = "needs_mfa"


class LoginResult:
    """Outcome of begin_login: either a token blob, or an MFA continuation.

    mfa_context is opaque to callers — it carries the live garth client plus the
    client_state resume_login needs, and must be held server-side (in memory)
    until the user supplies the code from their phone.
    """

    def __init__(self, token_blob: str | None = None, mfa_context: object | None = None):
        self.token_blob = token_blob
        self.mfa_context = mfa_context

    @property
    def needs_mfa(self) -> bool:
        return self.mfa_context is not None


def begin_login(email: str, password: str) -> LoginResult:
    client = Garmin(email=email, password=password, return_on_mfa=True)
    status, client_state = client.login()
    if status == _MFA_REQUIRED:
        return LoginResult(mfa_context=(client, client_state))
    return LoginResult(token_blob=client.client.dumps())


def resume_login(mfa_context: object, mfa_code: str) -> str:
    client, client_state = mfa_context  # type: ignore[misc]
    client.resume_login(client_state, mfa_code)
    return client.client.dumps()


def session_from_tokens(token_blob: str) -> "GarminSession":
    client = Garmin()
    client.login(token_blob)  # blob > 512 chars → garth loads() the session
    return GarminSession(client)


def _first_present(d: dict, keys: tuple, default=None):
    """First value among keys that is present AND non-null.

    The unofficial course API varies field names and sometimes returns JSON
    null; dict.get with a default only handles a *missing* key, so a present-
    but-null value (e.g. distanceInMeters: null) would slip through and crash
    (None / 1000) or become a null name. This treats null like missing.
    """
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


class GarminSession:
    """Course reads for one authenticated Garmin account."""

    def __init__(self, client: Garmin):
        self._client = client

    def _connectapi(self, path: str, **kwargs):
        try:
            return self._client.connectapi(path, **kwargs)
        except GarminConnectAuthenticationError as e:
            # Tokens expired/revoked (garth's silent OAuth2 refresh failed) →
            # surface as a re-auth signal, not a generic upstream error.
            raise GarminAuthError(str(e)) from e

    def get_courses(self, limit: int = 10) -> list[dict]:
        data = self._connectapi(
            _COURSE_LIST_PATH,
            params={"start": 0, "limit": limit, "courseType": "ALL"},
        )
        courses = []
        for c in data:
            course_id = c.get("courseId")
            if not course_id:
                continue
            name = _first_present(c, ("courseName", "name"))
            distance_m = _first_present(c, ("distanceInMeters", "totalDistance", "distance"), 0)
            courses.append({
                "id": str(course_id),
                "name": name if name is not None else f"Course {course_id}",
                "distanceKm": round(distance_m / 1000, 2),
            })
        return courses

    def get_course_points(self, course_id: str) -> list[dict]:
        response = self._connectapi(_COURSE_PATH.format(id=course_id))
        return [
            {"lat": pt["latitude"], "lon": pt["longitude"]}
            for pt in response.get("geoPoints", [])
        ]


def encode_points_binary(points: list[dict]) -> bytes:
    """Pack lat/lon pairs as big-endian int32 scaled by 1e7.

    8 bytes per point. Precision: 1e-7 degrees ≈ 11 mm — sufficient for
    navigation. int32 covers ±214 degrees, so all valid lat/lon fit.
    """
    return struct.pack(f">{2 * len(points)}i", *[
        v for p in points
        for v in (round(p["lat"] * 1e7), round(p["lon"] * 1e7))
    ])


def encode_points_ascii85(points: list[dict]) -> str:
    """ASCII85-encode packed course points for text/plain transport.

    25% overhead vs raw binary (vs 33% for base64). Our 8-byte-per-point
    binary data is always 4-byte aligned, so no partial groups or padding
    occur. Wire format: base64.a85encode(binary, adobe=False) — no <~ ~>
    markers, pure ASCII chars 33-117.
    """
    return base64.a85encode(encode_points_binary(points), adobe=False).decode("ascii")
