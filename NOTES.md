# Development Notes

## Authentication

The widget signs each user in with **their own** Garmin account using a real
OAuth authorization-code flow, delivered to the watch by the phone.

### Flow

```
Widget: Communications.makeOAuthRequest(<backend>/oauth/authorize, …)
   │  Garmin Connect Mobile opens the authorize page in a webview on the phone
   ▼
Backend /oauth/authorize → login form
   → user enters Garmin email + password
   → [MFA] Garmin sends a code to the phone; user enters it (/oauth/mfa)
   → garth mints that user's Garmin OAuth tokens, stored server-side
   → 302 redirect_uri?code=…
   │  Connect IQ intercepts the redirect and hands {code} to the widget
   ▼
Widget POST /api/token {code} → { access_token } → Application.Storage
Widget GET  /api/courses  (X-Api-Key: access_token)
```

The token lands on the watch through the OAuth callback, so **no Connect IQ
Store publication and no manual key entry are needed** — `makeOAuthRequest`
works for sideloaded apps.

### Backend → Garmin Connect
garth (via the `garminconnect` library) performs the genuine Garmin SSO
OAuth1→OAuth2 token exchange; `return_on_mfa` + `resume_login` surface the
phone-delivered MFA step. Per-user token blobs are persisted under
`TOKEN_STORE_DIR`, keyed by the opaque `api_key` the widget holds. No shared
account credentials live in the running service.

**Trust note:** because Garmin exposes no consent-screen OAuth for the Courses
API, the user's Garmin password is entered on a page the backend serves. It is
used only to mint tokens via garth and is never stored.

### Configuration (backend env)
| Var | Purpose |
|---|---|
| `TOKEN_STORE_DIR` | Directory for persisted per-user garth token blobs |
| `OAUTH_CLIENT_ID` | Expected client id (default `garmin-router-widget`) |
| `OAUTH_REDIRECT_URIS` | Comma-separated allowlist; must include `<backendUrl>/oauth/callback` |

### Widget settings
`backendUrl` points at the backend. `apiKey` is now an optional manual override
(handy for local testing): a non-placeholder value is treated as an
already-issued token and skips the sign-in prompt; otherwise the widget shows
"Sign in with Garmin".
