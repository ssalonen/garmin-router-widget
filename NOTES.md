# Development Notes

## Authentication

Single-account setup: the backend talks to Garmin as **one** account (yours),
using Garmin OAuth2 tokens minted once via the `/setup` web page. No Garmin
password lives in the running service, and MFA is supported.

### Backend → Garmin Connect (one-time web bootstrap)

```
Browse to  <backend>/setup
   → enter setup token + Garmin email + password
   → [MFA] Garmin sends a code to your phone; enter it   ← phone-assisted
   → garminconnect mints real Garmin OAuth2 tokens via SSO
   → token blob written to $GARMIN_TOKEN_FILE (0600, atomic)
   → "✅ Connected"
```

The `garminconnect` library performs the genuine Garmin SSO OAuth2 token
exchange; `return_on_mfa` + `resume_login` surface the phone-delivered MFA
step (`/setup/login` → `/setup/mfa`, logic in `bootstrap.py`). The backend loads
the saved blob at first request (`session_from_tokens`) and reuses it. The blob
holds a bearer token plus a refresh token; the bearer is refreshed silently
(the library re-mints it once the JWT `exp` is within 15 minutes), so day-to-day
expiry is invisible. When the refresh token itself stops working, revisit
`/setup`. The password is used only to mint tokens and is never stored.

When tokens are expired/invalid the backend returns **503** on the course
endpoints (auth failures are surfaced as `GarminAuthError`, kept distinct from a
transient 502), and the widget renders it as **"Garmin not connected"** — the
cue to revisit `/setup`.

Why not official Garmin OAuth? The Garmin Connect Developer Program's OAuth is
restricted to approved business entities, not individuals — so for a personal
tool the SSO token flow is the only way to read your own course list.

### Widget → Backend
Optional shared secret: set `API_KEY` on the backend and the matching `apiKey`
widget property. When `API_KEY` is unset the backend runs open (keep it on a
trusted network / VPN then). Note the widget's `apiKey` is compiled into the
sideloaded `.prg`, so treat it as a coarse gate, not real auth.

### Configuration (backend env)
| Var | Purpose |
|---|---|
| `GARMIN_TOKEN_FILE` | Path to the Garmin token blob written by `/setup`. In Docker this defaults to `/data/garmin_tokens.blob` (mount a volume); otherwise `garmin_tokens.blob` in CWD. |
| `API_KEY` | Optional shared secret required as `X-Api-Key`; unset disables the check |
| `SETUP_TOKEN` | **Required to enable `/setup`.** Setup is default-closed; unset → `/setup` returns 403. |

### Operational endpoints
- `GET /health` — liveness (process up, no Garmin dependency).
- `GET /ready` — readiness: 200 when a token blob is present and loads, 503 when
  the account needs connecting via `/setup`. Reflects "is the backend set up",
  not "are the tokens still valid" — it doesn't call Garmin, and expiry only
  surfaces on a real course request (503).

## Deployment requirements

These are real constraints, not asides:

- **Run a single worker.** The MFA continuation (`PendingLogins`) and the cached
  Garmin session are in-memory, per-process. With `uvicorn --workers > 1` the MFA
  code POST can land on a different worker than the login POST and fail
  intermittently. The Dockerfile pins `--workers 1`.
- **Serve over TLS.** The `/setup` password POST and the widget's `X-Api-Key`
  travel in cleartext over plain HTTP — terminate TLS at a reverse proxy and
  point the widget's `backendUrl` at `https://`.
- **`/setup` is default-closed and privileged.** It accepts a Garmin password and
  overwrites the account tokens; keep `SETUP_TOKEN` set and the backend off the
  public internet. The setup token is entered as a form field (POST), so it does
  not appear in URLs, access logs, or browser history.
- **Persist the token file.** Point `GARMIN_TOKEN_FILE` at a mounted volume (the
  Docker image uses `/data`), else the tokens vanish on container recreation and
  you must re-run `/setup`.
- **Blast radius.** The stored blob authenticates as the *full* Garmin account
  (activities, settings, health data), not a course-read scope — the SSO flow
  can't narrow it. Protecting the token file is the whole mitigation; it is gitignored
  (`*.blob`).

### Multi-user, later
If this ever needs to serve other people, the same `/setup`/token model extends
two ways: each user self-hosts their own backend instance (no shared trust), or
— only if a central service is really wanted — a backend-fronted OAuth flow
driving the widget's `Communications.makeOAuthRequest`. Out of scope for the
single-account setup.
