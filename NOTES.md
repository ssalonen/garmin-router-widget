# Development Notes

## Authentication

Single-account setup: the backend talks to Garmin as **one** account (yours),
using garth OAuth tokens minted once by `login.py`. No Garmin password lives in
the running service, and MFA is supported.

### Backend → Garmin Connect (one-time bootstrap)

```
uv run python login.py
   → enter Garmin email + password
   → [MFA] Garmin sends a code to your phone; enter it   ← phone-assisted
   → garth mints real Garmin OAuth1→OAuth2 tokens
   → token blob written to $GARMIN_TOKEN_FILE (0600)
```

garth (via the `garminconnect` library) performs the genuine Garmin SSO OAuth
token exchange; `return_on_mfa` + `resume_login` surface the phone-delivered MFA
step. The backend loads the saved blob at first request (`session_from_tokens`)
and reuses it; the OAuth1 token lasts ~1 year and the OAuth2 bearer
auto-refreshes. When it finally expires, re-run `login.py`. The password is used
only to mint tokens and is never stored.

Why not official Garmin OAuth? The Garmin Connect Developer Program's OAuth is
restricted to approved business entities, not individuals — so for a personal
tool the garth token flow is the only way to read your own course list.

### Widget → Backend
Optional shared secret: set `API_KEY` on the backend and the matching `apiKey`
widget property. When `API_KEY` is unset the backend runs open (keep it on a
trusted network / VPN then).

### Configuration (backend env)
| Var | Purpose |
|---|---|
| `GARMIN_TOKEN_FILE` | Path to the garth token blob written by `login.py` (default `garmin_tokens.blob`) |
| `API_KEY` | Optional shared secret required as `X-Api-Key`; unset disables the check |

### Multi-user, later
If this ever needs to serve other people, the same `login.py`/token model
extends two ways: each user self-hosts their own backend instance (no shared
trust), or — only if a central service is really wanted — a backend-fronted
OAuth flow driving the widget's `Communications.makeOAuthRequest`. Out of scope
for the single-account setup.
