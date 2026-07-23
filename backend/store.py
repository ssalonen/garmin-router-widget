"""Persistence for the OAuth provider.

Three small stores, deliberately separated by lifetime and durability:

  TokenStore        durable   on disk    api_key      -> garth token blob
  AuthCodeStore     seconds   in memory  auth code    -> api_key (one-time)
  PendingLoginStore minutes   in memory  login session-> MFA continuation

Only TokenStore is persisted: garth token blobs must survive a restart so the
backend keeps working without re-login. Auth codes and MFA continuations are
short-lived by design and intentionally evaporate on restart.
"""
import json
import os
import secrets
import threading
import time
from typing import Any, Callable


class TokenStore:
    """api_key -> garth token blob, persisted one file per key.

    The api_key is the bearer the widget sends as X-Api-Key; the blob is the
    opaque garth session string (`Garmin.client.dumps()`). Keeping them apart
    means the widget never holds Garmin tokens, only an indirection handle.
    """

    def __init__(self, directory: str):
        self._dir = directory
        self._lock = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, api_key: str) -> str:
        # api_key is url-safe base64 (no path separators) — safe as a filename.
        return os.path.join(self._dir, api_key + ".token")

    def put(self, token_blob: str) -> str:
        api_key = secrets.token_urlsafe(32)
        self.set(api_key, token_blob)
        return api_key

    def set(self, api_key: str, token_blob: str) -> None:
        with self._lock:
            tmp = self._path(api_key) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(token_blob)
            os.replace(tmp, self._path(api_key))

    def get(self, api_key: str) -> str | None:
        try:
            with open(self._path(api_key), encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return None


class AuthCodeStore:
    """One-time authorization codes with a short TTL (OAuth code grant)."""

    def __init__(self, ttl_seconds: int = 300, now: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._now = now
        self._lock = threading.Lock()
        self._codes: dict[str, tuple[str, float]] = {}

    def issue(self, api_key: str) -> str:
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._codes[code] = (api_key, self._now() + self._ttl)
        return code

    def redeem(self, code: str) -> str | None:
        with self._lock:
            entry = self._codes.pop(code, None)
        if entry is None:
            return None
        api_key, expires_at = entry
        if self._now() > expires_at:
            return None
        return api_key


class PendingLoginStore:
    """In-memory MFA continuations keyed by an opaque login-session id.

    Holds the live garth client (or any opaque context) between the credential
    step and the MFA-code step. In memory only: MFA must complete within
    minutes, and a live requests/garth session is not meaningfully serialisable.
    """

    def __init__(self, ttl_seconds: int = 600, now: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._now = now
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[Any, float]] = {}

    def put(self, context: Any) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
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
