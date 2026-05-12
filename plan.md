# Garmin Edge 530 — Reliable Route Sync Plan

## Problem Statement

The Garmin Edge 530's Bluetooth sync is unreliable for route/course transfers:

- Sync does not work while an activity is running (device reports "busy")
- Manual sync trigger frequently fails or stalls indefinitely
- Trailmap (Finnish route-planning app) can push routes to Garmin Connect, but delivery to the device depends on the same unreliable BLE sync pipeline

Goal: a method to get a route onto the Edge 530 reliably, with minimal friction, even mid-activity or just before starting one.

---

## Root Cause Analysis

The Edge 530's BLE sync uses Garmin's standard "LiveTrack / device sync" protocol via the Garmin Connect Mobile (GCM) app. This pipeline has several known failure modes:

| Failure mode | Why it happens |
|---|---|
| "Device busy" during activity | Garmin OS intentionally blocks file writes while an activity is recording |
| Sync stalls indefinitely | BLE transfer drops, GCM enters a hung state, or the device queue backs up |
| Manual "Sync now" fails | GCM simply retries the same stalled operation |

None of these are fixable from the phone side. The solution must either bypass the BLE sync pipeline entirely or initiate transfer from the device side.

---

## Solution Options

### A. USB File Transfer (most reliable; manual)

Copy a `.fit` course file directly to `/Garmin/Courses/` on the device via USB.

- **Pros:** 100 % reliable, no BLE, no auth issues, works on any OS
- **Cons:** Requires USB cable, not suitable just before a ride, still need to convert GPX → FIT

A helper script (Python + `fitdecode`/`fit-tool`) could automate: fetch GPX from Trailmap share URL → convert to FIT → write to device. This is a good offline fallback.

### B. WiFi Sync via Garmin Express

Edge 530 has WiFi. When the device is on a known WiFi network and idle (not recording), it syncs with Garmin Connect over WiFi, which is far more reliable than BLE.

- **Pros:** No cable, no phone, no code changes — just configure WiFi on the device
- **Cons:** Only works when idle (same "device busy" restriction), requires home WiFi, not on-demand

**Action:** Ensure the device has home WiFi configured (`Settings → Wi-Fi → Add network`). This alone may solve most day-to-day sync problems without any custom code.

### C. Connect IQ Widget — "Navigate Now" (recommended for on-device reliability)

A Connect IQ widget that fetches course waypoints on demand and immediately starts Garmin's built-in navigation engine via `Navigation.startNavigation()`.

The widget bypasses the sync pipeline entirely: it pulls data at the moment the user needs it and hands it to the OS navigation layer.

- **Pros:** Works regardless of BLE sync state, user-initiated, fast
- **Cons:** Navigation started from widget may or may not persist if the widget is closed before an activity starts (needs testing); requires phone + internet to fetch; needs a small backend service for auth
- **Precedent:** [GRouteLoaderIQ](https://forums.garmin.com/developer/connect-iq/f/showcase/7983/grouteloaderiq-download-course-location-files-to-your-device) demonstrates that a Connect IQ widget can download and load a course wirelessly on Edge hardware

### D. Connect IQ Widget — Course Download via Backend (full solution)

Extension of Option C where the backend also pushes the course to the device through Garmin Connect's "Send to Device" API, making the course available persistently (not just for the current navigation session).

- **Pros:** Course is saved on device for offline use, no navigation session required
- **Cons:** More complex backend; "Send to Device" API may require Garmin developer program enrollment

---

## Recommended Approach

**Phase 1 (immediate fix, no code):** Configure WiFi on the Edge 530. This resolves the reliability issue for pre-ride syncs without any custom development.

**Phase 2 (widget, reliable on-demand):** Build the Connect IQ widget (Option C). This covers the cases WiFi doesn't handle — mid-activity route fetch, or when the user is away from home WiFi.

**Phase 3 (optional enhancement):** Add persistent course saving if the Phase 2 widget meets all practical needs (Phase 3 may turn out unnecessary).

---

## Architecture (Phase 2 Widget)

```
Trailmap ──(sync)──► Garmin Connect (course stored, has course ID)
                              │
                              │  HTTP (via device WiFi or phone proxy)
                              ▼
                       Backend Proxy API
                       (handles Garmin Connect OAuth,
                        returns course points as JSON)
                              │
                              │  Communications.makeWebRequest()
                              ▼
                     Connect IQ Widget (Edge 530)
                       - User enters course ID (digits via buttons)
                       - Widget fetches waypoints
                       - Calls Navigation.startNavigation()
                              │
                              ▼
                     Garmin OS navigation engine
                     (map route shown, turn-by-turn active)
```

### Why a backend proxy is required

`Communications.makeWebRequest()` on the Edge 530 makes direct HTTPS requests but does not handle session cookies or pass Garmin Connect authentication automatically. The Garmin Connect Courses API requires OAuth 2.0 with a consumer secret that must never be embedded in a device app. A small backend service holds the credentials and acts as an authenticated proxy.

### Backend proxy (minimal)

- Language: anything (Python/FastAPI suggested for simplicity)
- Endpoint: `GET /course/{courseId}/points` → returns `[{lat, lon, alt}, ...]`
- Auth: server-side OAuth2 against Garmin Connect using registered developer credentials
- Hosting: any small VPS or serverless function (low traffic)

### Widget UI

Edge 530 has a 240×200 screen and five physical buttons: Up, Down, Start/Enter, Back, Lap.

```
┌─────────────────────────┐
│  Route Loader           │
│                         │
│  Course ID:             │
│  [ 1 2 3 4 5 _ _ _ ]    │  ← cursor digit highlighted
│                         │
│  UP/DOWN: change digit  │
│  START: next digit      │
│  LAP: fetch & navigate  │
│  BACK: cancel           │
│                         │
│  Status: Ready          │
└─────────────────────────┘
```

After Lap/fetch, the widget calls `Navigation.startNavigation()` with the fetched waypoints and shows a brief confirmation before the user exits the widget to start their activity.

---

## Implementation Plan

### Step 1 — Development environment setup

- Install Connect IQ SDK (latest compatible with API 3.3)
- Install Monkey C VS Code extension
- Configure Edge 530 as target device in `manifest.xml`
- Verify simulator runs a hello-world widget on Edge 530 profile

### Step 2 — Backend proxy

- Register as a Garmin developer and obtain OAuth2 consumer credentials for the Courses API
- Implement `GET /course/{courseId}/points` endpoint
- Return simplified JSON: `{"points": [{"lat": 60.1, "lon": 24.9, "alt": 50}, ...]}`
- Deploy to a public HTTPS endpoint (the widget needs a stable URL)
- Store the backend URL as a configurable app setting in the widget

### Step 3 — Widget skeleton

- Widget app type in `manifest.xml`, target `edge530`
- `WatchUi.WatchFace` → `WatchUi.View` with custom `onUpdate()` draw loop
- Implement button handler (`onKey()`) for digit-entry state machine
- Display current digit array and cursor position

### Step 4 — Network fetch

- On "fetch" button press: call `Communications.makeWebRequest()` to backend proxy with the entered course ID
- Handle `COMMUNICATIONS_ERROR` cases: no phone, no network, bad ID
- Show loading indicator while waiting (Edge 530 can take several seconds for a round trip)

### Step 5 — Start navigation

- On successful response, build `[Position.Location]` array from returned points
- Call `Navigation.startNavigation(points, opts)`
- Show success message ("Route loaded — start activity")
- Let user press Back to exit widget; navigation remains active

### Step 6 — Trailmap course ID flow

Trailmap syncs routes to Garmin Connect. The course ID appears in the Garmin Connect URL:
`https://connect.garmin.com/modern/course/123456789`

The user notes the 9-digit ID from Garmin Connect (or Trailmap's Garmin sync confirmation) and enters it in the widget. Consider adding a "recent courses" list in a future iteration to avoid re-typing.

### Step 7 — Testing

- Test on Edge 530 simulator: digit entry, error states, loading state
- Sideload to physical Edge 530 via Garmin Express developer mode
- Test end-to-end: Trailmap route → Garmin Connect → widget fetch → navigation on device
- Test the "start activity after widget navigation" flow to confirm navigation persists

---

## Open Questions

| Question | Impact | How to resolve |
|---|---|---|
| Does `Navigation.startNavigation()` navigation persist after the widget is closed and an activity starts? | High — if not, the whole approach needs rethinking | Test on physical Edge 530; check GRouteLoaderIQ behavior |
| How does GRouteLoaderIQ actually write courses to device storage (if it does)? | Medium — would enable persistent course saving (Phase 3) | Read GRouteLoaderIQ source if available; contact developer; test behavior |
| Does `makeWebRequest()` work over BLE (phone proxy) when WiFi is unavailable? | Medium — affects field usability | Test on device with WiFi disabled |
| Does Garmin's developer program approval take long? | Medium — blocks backend auth | Apply early; consider using a test/personal OAuth token for initial development |
| Can Trailmap export a direct GPX download URL for a shared route? | Low — could simplify the backend (skip Garmin Connect entirely) | Check Trailmap API / share URL format |

---

## File / Repo Structure (planned)

```
garmin-router-widget/
├── plan.md                  ← this file
├── widget/                  ← Connect IQ project
│   ├── manifest.xml
│   ├── source/
│   │   ├── App.mc           ← app entry point
│   │   ├── MainView.mc      ← digit-entry UI
│   │   └── CourseLoader.mc  ← web request + Navigation.startNavigation
│   └── resources/
│       └── layouts/
│           └── layout.xml
└── backend/                 ← proxy service
    ├── main.py              ← FastAPI app
    ├── requirements.txt
    └── Dockerfile
```
