# Development Notes

## Authentication

### Widget → Backend
Currently: no auth. Backend should be kept on a local network or VPN.

**Future option — publish to Connect IQ Store:**
The store unlocks `type="alphaNumeric"` settings, which show a text input in the
Garmin Connect mobile app. This would let each user type their own backend URL and
an API key (or even Garmin credentials) which sync to the watch via the app.
Not available for sideloaded apps — the settings editor simply doesn't appear.

### Backend → Garmin Connect
Currently: `GARMIN_EMAIL` + `GARMIN_PASSWORD` env vars, hardcoded to one account.
The `garminconnect` library mimics the Garmin mobile app; no developer portal registration needed.
