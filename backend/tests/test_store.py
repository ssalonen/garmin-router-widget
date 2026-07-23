"""Tests for the OAuth-provider persistence layer (store.py).

Three collaborators, all independent of Garmin and HTTP:
  - TokenStore       : api_key -> garth token blob, persisted to disk
  - AuthCodeStore    : one-time authorization code -> api_key, with TTL
  - PendingLoginStore: in-memory MFA continuation -> opaque context, with TTL
"""
import pytest

from store import AuthCodeStore, PendingLoginStore, TokenStore


# ── TokenStore ──────────────────────────────────────────────────────────────

def test_token_store_put_returns_opaque_api_key(tmp_path):
    store = TokenStore(str(tmp_path))
    key = store.put("garth-token-blob")
    assert isinstance(key, str)
    assert len(key) >= 24  # unguessable


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(str(tmp_path))
    key = store.put("garth-token-blob")
    assert store.get(key) == "garth-token-blob"


def test_token_store_distinct_keys(tmp_path):
    store = TokenStore(str(tmp_path))
    k1 = store.put("blob-1")
    k2 = store.put("blob-2")
    assert k1 != k2
    assert store.get(k1) == "blob-1"
    assert store.get(k2) == "blob-2"


def test_token_store_unknown_key_returns_none(tmp_path):
    store = TokenStore(str(tmp_path))
    assert store.get("does-not-exist") is None


def test_token_store_persists_across_instances(tmp_path):
    """A fresh TokenStore over the same dir sees previously written tokens —
    this is what lets the backend survive a restart without re-login."""
    key = TokenStore(str(tmp_path)).put("durable-blob")
    assert TokenStore(str(tmp_path)).get(key) == "durable-blob"


def test_token_store_update_replaces_blob(tmp_path):
    """Re-authenticating the same api_key (token refresh) overwrites in place."""
    store = TokenStore(str(tmp_path))
    key = store.put("old-blob")
    store.set(key, "new-blob")
    assert store.get(key) == "new-blob"


# ── AuthCodeStore ───────────────────────────────────────────────────────────

def test_auth_code_issue_and_redeem(tmp_path):
    codes = AuthCodeStore()
    code = codes.issue("api-key-123")
    assert isinstance(code, str) and len(code) >= 16
    assert codes.redeem(code) == "api-key-123"


def test_auth_code_is_single_use(tmp_path):
    codes = AuthCodeStore()
    code = codes.issue("api-key-123")
    assert codes.redeem(code) == "api-key-123"
    assert codes.redeem(code) is None  # second redeem fails


def test_auth_code_unknown_returns_none():
    codes = AuthCodeStore()
    assert codes.redeem("never-issued") is None


def test_auth_code_expires(monkeypatch):
    clock = {"t": 1000.0}
    codes = AuthCodeStore(ttl_seconds=60, now=lambda: clock["t"])
    code = codes.issue("api-key-123")
    clock["t"] = 1000.0 + 61
    assert codes.redeem(code) is None  # expired


def test_auth_code_valid_within_ttl(monkeypatch):
    clock = {"t": 1000.0}
    codes = AuthCodeStore(ttl_seconds=60, now=lambda: clock["t"])
    code = codes.issue("api-key-123")
    clock["t"] = 1000.0 + 59
    assert codes.redeem(code) == "api-key-123"


# ── PendingLoginStore ───────────────────────────────────────────────────────

def test_pending_login_roundtrip():
    pending = PendingLoginStore()
    ctx = object()  # opaque MFA continuation (a live garth client, in practice)
    sid = pending.put(ctx)
    assert isinstance(sid, str) and len(sid) >= 16
    assert pending.pop(sid) is ctx


def test_pending_login_is_single_use():
    pending = PendingLoginStore()
    sid = pending.put(object())
    pending.pop(sid)
    assert pending.pop(sid) is None


def test_pending_login_unknown_returns_none():
    pending = PendingLoginStore()
    assert pending.pop("nope") is None


def test_pending_login_expires():
    clock = {"t": 500.0}
    pending = PendingLoginStore(ttl_seconds=120, now=lambda: clock["t"])
    sid = pending.put(object())
    clock["t"] = 500.0 + 121
    assert pending.pop(sid) is None
