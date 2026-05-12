# Garmin Edge 530 — Reliable Route Sync Plan

## Problem Statement

The Garmin Edge 530's Bluetooth sync is unreliable for route/course transfers:

- Sync does not work while an activity is running (device reports "busy")
- Manual sync trigger frequently fails or stalls indefinitely
- Trailmap (Finnish route-planning app) can push routes to Garmin Connect, but delivery to the device depends on the same unreliable BLE sync pipeline

**Existing solution tried:** [GRouteLoaderIQ](https://apps.garmin.com/en-US/apps/6b770e92-2cc6-437e-8de2-0efae208a455) — a Connect IQ widget that can download a course by ID via `Communications.makeWebRequest()`. It works sometimes but has two problems:
1. UX is painful: user must enter a 9-digit Garmin Connect course ID digit by digit using physical buttons
2. Reliability is still inconsistent

Goal: a widget that is as reliable as GRouteLoaderIQ but with UX that doesn't require typing IDs — the device should show your recent courses and let you pick one.

---

## Root Cause Analysis

The Edge 530's BLE sync uses Garmin's standard device-sync protocol via the Garmin Connect Mobile (GCM) app. This pipeline has known failure modes:

| Failure mode | Why it happens |
|---|---|
| "Device busy" during activity | Garmin OS intentionally blocks file writes while an activity is recording |
| Sync stalls indefinitely | BLE transfer drops, GCM enters a hung state, or the device queue backs up |
| Manual "Sync now" fails | GCM simply retries the same stalled operation |

None of these are fixable from the phone side. The solution must bypass the standard BLE sync pipeline and initiate transfer from the device side — which is exactly what GRouteLoaderIQ does.

---

## Immediate Non-Code Fix

**Configure WiFi on the Edge 530** (`Settings → Wi-Fi → Add network`).

When idle on a known WiFi network the device syncs over WiFi rather than BLE, which is significantly more reliable. This does not help mid-activity or away from home, but it eliminates the most common pre-ride sync frustration with zero development effort.

---

## Solution: Improved Widget

Build on the GRouteLoaderIQ concept but fix the UX by showing a scrollable list of your recent Garmin Connect courses instead of requiring a typed ID.

### Target UX

```
┌─────────────────────────┐
│  Route Loader           │
│                         │
│ ▶ Morning Trail  12 km  │  ← most recent, highlighted
│   Lakeside Loop   8 km  │
│   Forest Path     5 km  │
│   Mountain Run   20 km  │
│   (5 more...)           │
│                         │
│  ↑↓ scroll              │
│  START: navigate        │
│  BACK: exit             │
└─────────────────────────┘
```

Opening the widget fetches your last ~10 courses from Garmin Connect and displays them by name. One button press starts navigation. No ID entry.

### How the course list gets to the widget

The widget cannot authenticate with Garmin Connect directly (OAuth2 consumer secret cannot be embedded in device code). Two viable paths:

**Option 1 — Backend proxy (recommended)**

A small server holds the Garmin Connect OAuth2 credentials. The widget calls the proxy, which returns a named course list and course points.

```
Trailmap ──(sync)──► Garmin Connect
                           │
                           │ HTTPS (device WiFi or BLE→phone proxy)
                           ▼
                     Backend Proxy
                     • GET /courses       → [{id, name, distance}, ...]
                     • GET /course/{id}   → [{lat, lon, alt}, ...]
                     (holds OAuth2 credentials)
                           │
                           │ Communications.makeWebRequest()
                           ▼
                     Connect IQ Widget
                     • Shows course list by name
                     • User picks one
                     • Calls Navigation.startNavigation()
                           │
                           ▼
                     Garmin OS navigation engine
```

- **Pros:** All interaction stays on the device; clean UX; no phone interaction needed
- **Cons:** Requires a publicly reachable HTTPS server; needs Garmin developer program enrollment for official OAuth credentials

**Option 2 — Companion phone app**

A simple phone app (Android/iOS) authenticates with Garmin Connect, fetches the course list, and pushes it to the widget over BLE via `Communications.registerForPhoneAppMessages()`.

- **Pros:** No server to run; OAuth handled on phone where it's natural
- **Cons:** Must build and maintain a phone app in addition to the widget; user must open the phone app first before opening the widget

Option 1 is recommended because it gives the cleaner device-side UX and avoids building a phone app. The backend is minimal (~100 lines of Python).

---

## Technical Constraints (Edge 530 / Connect IQ 3.3)

| Constraint | Detail |
|---|---|
| Cannot write course files to device storage | No Connect IQ API for `/Garmin/Courses/`; this is a hard OS restriction |
| `makeWebRequest()` does not carry Garmin auth cookies | Requests are direct HTTPS; Garmin session is not passed automatically |
| OAuth consumer secret cannot be in device code | Must live on the backend |
| `makeWebRequest()` works over BLE phone proxy | Confirmed; occasional `BLE_QUEUE_FULL` at high volume — keep JSON payloads small |
| `Navigation.startNavigation()` available in API 3.3 | Confirmed; whether navigation persists after widget exits needs physical device test |
| 5 physical buttons | Up, Down, Start/Enter, Lap, Back — sufficient for list navigation |

---

## Implementation Plan

### Step 1 — Development environment

- Install Connect IQ SDK (latest 3.x compatible build)
- Install Monkey C VS Code extension
- `manifest.xml` targeting `edge530`, app type `widget`
- Confirm hello-world widget runs in Edge 530 simulator

### Step 2 — Backend proxy

- Register for Garmin developer program (apply early; approval time unknown)
- Implement two endpoints in Python/FastAPI:
  - `GET /courses` → `[{"id": "123456789", "name": "Morning Trail", "distanceKm": 12.3}, ...]`
  - `GET /course/{id}` → `{"points": [{"lat": 60.1, "lon": 24.9, "alt": 50}, ...]}`
- OAuth2 against Garmin Connect; credentials in environment variables, never committed
- Deploy to any small VPS or serverless host; must be public HTTPS
- Backend URL stored as a configurable widget setting (editable via Garmin Connect Mobile settings page for the app)

### Step 3 — Widget: course list

- On widget open: call `GET /courses` via `makeWebRequest()`
- Show loading indicator during fetch
- On response: render scrollable list with course name + distance
- Up/Down buttons scroll the list; highlighted item tracks selection
- Handle errors: no phone, no network, empty list, server error

### Step 4 — Widget: load and navigate

- On Start press with a course highlighted: call `GET /course/{id}`
- Show loading indicator
- On response: build `[Position.Location]` array from points
- Call `Navigation.startNavigation(points, {})`
- Show "Navigating: [name]" confirmation
- User presses Back to exit widget and start their activity

### Step 5 — Key test: navigation persistence

Before investing further, verify on a physical Edge 530:
- Start widget → load course → press Back → start activity
- Does the loaded route appear on the map during the activity?

If yes: the widget is complete. If no: the course needs to be loaded in a different way (investigate how GRouteLoaderIQ achieves persistence — contact developer on Garmin forums or test their app carefully).

### Step 6 — Polish

- Cache the course list locally (`Application.Storage`) with a 5-minute TTL so reopening the widget is instant
- Show last-used course highlighted by default
- "Refresh" option (Lap button) to force re-fetch
- Handle the case where Trailmap's sync hasn't completed yet (course not yet on Garmin Connect) with a clear message

---

## Open Questions

| Question | Impact | How to resolve |
|---|---|---|
| Does `Navigation.startNavigation()` navigation persist after widget closes and activity starts? | **Critical** — determines if the whole approach works | Test on physical device (Step 5) |
| How long does Garmin developer program approval take? | High — blocks OAuth credentials | Apply at once; use Garmin's unofficial/scraper API for early development if needed |
| Does GRouteLoaderIQ persist courses (vs navigate-now only)? | Medium — informs Phase 2 design | Contact dpawlyk on Garmin forums |
| Can Trailmap routes be fetched directly by URL without auth? | Low — would simplify backend by skipping Garmin Connect | Check Trailmap GPX export URL format |

---

## File / Repo Structure (planned)

```
garmin-router-widget/
├── plan.md
├── widget/
│   ├── manifest.xml
│   ├── source/
│   │   ├── App.mc            ← entry point
│   │   ├── CourseListView.mc ← scrollable list UI
│   │   └── CourseLoader.mc   ← makeWebRequest + Navigation.startNavigation
│   └── resources/
│       └── layouts/
│           └── layout.xml
└── backend/
    ├── main.py               ← FastAPI proxy
    ├── requirements.txt
    └── Dockerfile
```
