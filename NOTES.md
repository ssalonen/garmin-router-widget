# Development Notes

## Authentication

Single-account setup: the backend talks to Garmin as **one** account (yours),
using garth OAuth tokens minted once by `login.py`. No Garmin password lives in
the running service, and MFA is supported.

### Backend → Garmin Connect (one-time web bootstrap)

```
Browse to  <backend>/setup
   → enter Garmin email + password
   → [MFA] Garmin sends a code to your phone; enter it   ← phone-assisted
   → garth mints real Garmin OAuth1→OAuth2 tokens
   → token blob written to $GARMIN_TOKEN_FILE (0600)
   → "✅ Connected"
```

garth (via the `garminconnect` library) performs the genuine Garmin SSO OAuth
token exchange; `return_on_mfa` + `resume_login` surface the phone-delivered MFA
step (`/setup/login` → `/setup/mfa`). The backend loads the saved blob at first
request (`session_from_tokens`) and reuses it; the OAuth1 token lasts ~1 year and
the OAuth2 bearer auto-refreshes. When it finally expires, revisit `/setup`. The
password is used only to mint tokens and is never stored.

When tokens are expired/invalid the backend returns **503** on the course
endpoints (auth failures are surfaced as `GarminAuthError`, kept distinct from a
transient 502), and the widget renders it as **"Garmin login expired"** — the
cue to revisit `/setup`.

**Protect the setup page:** it writes the account tokens, so gate it with
`SETUP_TOKEN` (then browse to `/setup?token=…`) and/or keep the backend off the
public internet. With `SETUP_TOKEN` unset the page is open.

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
| `GARMIN_TOKEN_FILE` | Path to the garth token blob written by `/setup` (default `garmin_tokens.blob`) |
| `API_KEY` | Optional shared secret required as `X-Api-Key`; unset disables the check |
| `SETUP_TOKEN` | Optional gate for the `/setup` pages (`/setup?token=…`); unset leaves setup open |

### Multi-user, later
If this ever needs to serve other people, the same `login.py`/token model
extends two ways: each user self-hosts their own backend instance (no shared
trust), or — only if a central service is really wanted — a backend-fronted
OAuth flow driving the widget's `Communications.makeOAuthRequest`. Out of scope
for the single-account setup.
