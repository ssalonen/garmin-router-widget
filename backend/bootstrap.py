"""Web bootstrap for the single Garmin account.

Drives the garth login from a browser page: enter Garmin email/password,
complete phone MFA if prompted, and the resulting token blob is written to the
token file the backend reads. Transport (HTML forms and routes) lives in
routes_setup.py; this module is the logic and is unit-testable without HTTP.
"""
import os
import secrets
import tempfile
import threading
import time
from typing import Any, Callable

import garmin


class ExpiredLogin(Exception):
    """The MFA login session is unknown or has expired."""


class PendingLogins:
    """In-memory MFA continuations between the credential step and the code
    step, keyed by an opaque session id. In memory only and short-lived: a live
    garth session is not meaningfully serialisable, and MFA completes in
    minutes."""

    def __init__(self, ttl_seconds: int = 600, now: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._now = now
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[Any, float]] = {}

    def put(self, context: Any) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep()  # reclaim abandoned MFA sessions so the map stays bounded
            self._sessions[sid] = (context, self._now() + self._ttl)
        return sid

    def pop(self, sid: str) -> Any | None:
        with self._lock:
            entry = self._sessions.pop(sid, None)
        if entry is None:
            return None
        context, expires_at = entry
        if self._now() > expires_at:
            return None
        return context

    def _sweep(self) -> None:
        # Caller holds _lock. Drop entries whose TTL has elapsed — otherwise an
        # abandoned MFA (user never submits the code) would pin a live garth
        # client until process exit.
        now = self._now()
        expired = [sid for sid, (_, exp) in self._sessions.items() if now > exp]
        for sid in expired:
            del self._sessions[sid]


class SetupOutcome:
    def __init__(self, done: bool = False, mfa_session_id: str | None = None):
        self.done = done
        self.mfa_session_id = mfa_session_id


class SetupService:
    def __init__(self, token_file: str, auth=garmin, pending: PendingLogins | None = None):
        self._token_file = token_file
        self._auth = auth
        self._pending = pending or PendingLogins()

    def begin(self, email: str, password: str) -> SetupOutcome:
        result = self._auth.begin_login(email, password)
        if result.needs_mfa:
            return SetupOutcome(mfa_session_id=self._pending.put(result.mfa_context))
        self._save(result.token_blob)
        return SetupOutcome(done=True)

    def complete_mfa(self, mfa_session_id: str, mfa_code: str) -> SetupOutcome:
        context = self._pending.pop(mfa_session_id)
        if context is None:
            raise ExpiredLogin()
        blob = self._auth.resume_login(context, mfa_code)
        self._save(blob)
        return SetupOutcome(done=True)

    def _save(self, blob: str) -> None:
        # Write to a temp file that is 0600 from creation (mkstemp), then
        # atomically replace — no world-readable window, and a crash mid-write
        # can't truncate the existing token file.
        directory = os.path.dirname(self._token_file) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tokens-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(blob)
            os.replace(tmp, self._token_file)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
