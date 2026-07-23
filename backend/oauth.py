"""OAuth-provider orchestration.

Ties the persistence layer (store.py) to the garth auth seam (garmin.py) and
enforces the client_id / redirect_uri allowlist. Deliberately transport-free:
FastAPI wiring lives in main.py, so this whole pipeline is unit-testable
without HTTP.

Flow (authorization-code grant, backend fronting Garmin):
  begin_login → (auth_code)                     when no MFA
             → (mfa_session_id) → complete_mfa → (auth_code)
  redeem_code(auth_code) → api_key
  session_for_api_key(api_key) → GarminSession
"""
import os
from dataclasses import dataclass

import garmin
from store import AuthCodeStore, PendingLoginStore, TokenStore


class ExpiredLogin(Exception):
    """The MFA login session is unknown or has expired."""


@dataclass
class OAuthConfig:
    client_id: str
    redirect_uris: set[str]


class LoginOutcome:
    def __init__(self, auth_code: str | None = None, mfa_session_id: str | None = None):
        self.auth_code = auth_code
        self.mfa_session_id = mfa_session_id

    @property
    def needs_mfa(self) -> bool:
        return self.mfa_session_id is not None


class OAuthProvider:
    def __init__(self, token_store, code_store, pending_store, config, auth=garmin):
        self._tokens = token_store
        self._codes = code_store
        self._pending = pending_store
        self._config = config
        self._auth = auth

    # ── authorization request validation ────────────────────────────────
    def validate_authorization(self, client_id: str, redirect_uri: str) -> bool:
        return (
            client_id == self._config.client_id
            and redirect_uri in self._config.redirect_uris
        )

    # ── credential + MFA steps ───────────────────────────────────────────
    def begin_login(self, email: str, password: str) -> LoginOutcome:
        result = self._auth.begin_login(email, password)
        if result.needs_mfa:
            return LoginOutcome(mfa_session_id=self._pending.put(result.mfa_context))
        return LoginOutcome(auth_code=self._issue(result.token_blob))

    def complete_mfa(self, login_session_id: str, mfa_code: str) -> str:
        context = self._pending.pop(login_session_id)
        if context is None:
            raise ExpiredLogin()
        token_blob = self._auth.resume_login(context, mfa_code)
        return self._issue(token_blob)

    def _issue(self, token_blob: str) -> str:
        api_key = self._tokens.put(token_blob)
        return self._codes.issue(api_key)

    # ── token exchange + resolution ──────────────────────────────────────
    def redeem_code(self, code: str) -> str | None:
        return self._codes.redeem(code)

    def session_for_api_key(self, api_key: str):
        blob = self._tokens.get(api_key)
        if blob is None:
            return None
        return self._auth.session_from_tokens(blob)


def config_from_env() -> OAuthConfig:
    redirect_uris = {
        u.strip()
        for u in os.environ.get(
            "OAUTH_REDIRECT_URIS",
            "https://example.com/oauth/callback",
        ).split(",")
        if u.strip()
    }
    return OAuthConfig(
        client_id=os.environ.get("OAUTH_CLIENT_ID", "garmin-router-widget"),
        redirect_uris=redirect_uris,
    )


def provider_from_env() -> OAuthProvider:
    return OAuthProvider(
        token_store=TokenStore(os.environ.get("TOKEN_STORE_DIR", "./tokens")),
        code_store=AuthCodeStore(),
        pending_store=PendingLoginStore(),
        config=config_from_env(),
    )
