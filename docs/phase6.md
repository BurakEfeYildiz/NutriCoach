# Phase 6: Web UI Architecture & Implementation

## 1. Executive Summary

Phase 6 transforms NutriCoach from a Swagger/API-only backend into a mobile-first, consumer-facing health and nutrition web application accessible at `http://127.0.0.1:8000/`.

The user interface delivers a modern, minimal, premium wellness aesthetic with zero build steps, zero npm pipelines, and zero heavy client-side frameworks. It adheres strictly to the single source-of-truth principle: all nutrition math, timezone-aware day bounds, and AI decisions remain exclusively on the FastAPI backend.

---

## 2. Architecture & Technology Stack

- **Server-side Rendering**: FastAPI `Jinja2Templates` for initial HTML document delivery.
- **Client-side Interaction**: Native vanilla ES6+ JavaScript (`fetch`, `async/await`, custom events, standard DOM APIs).
- **Styling**: Single pure CSS3 design system (`app.css`) using CSS Custom Properties (variables), Flexbox, CSS Grid, and responsive media queries.
- **Dependencies Added**: `jinja2` added to `pyproject.toml`.
- **Database Migrations**: Zero migrations required (`0004 (head)` remains unchanged).
- **Backend Integrity**: All Phase 1–5 domain endpoints, services, schemas, and 106 existing tests remain 100% untouched and passing.

---

## 3. Directory Structure

```
NutriCoach/
├── app/
│   ├── routes/
│   │   ├── web.py                 # HTML page routes + /api/v1/dev/bootstrap
│   │   └── users.py               # Added GET /api/v1/users list endpoint
│   ├── templates/
│   │   ├── base.html              # Core app shell, navbars, toast & dialog containers
│   │   ├── dashboard.html         # Today's calories, macros, meals, quick log
│   │   ├── coach.html             # Conversational UI with action cards & composer
│   │   ├── meals.html             # Date navigation, daily items, meal modals
│   │   ├── progress.html          # Weight logs, adherence stats, native SVG chart
│   │   └── profile.html           # Canonical profile goals & Memory manager
│   └── static/
│       ├── css/
│       │   └── app.css            # Complete design system & responsive layout
│       └── js/
│           ├── api.js             # Centralized fetch wrapper & user bootstrap
│           ├── ui.js              # Toast system, confirm modal, formatting helpers
│           ├── dashboard.js       # Dashboard logic & summary rendering
│           ├── coach.js           # Chat flow, retry idempotency & action badges
│           ├── meals.js           # Meal log CRUD & date switcher
│           ├── progress.js        # Weight logging & zero-dependency SVG line chart
│           └── profile.js         # Profile form handling & memory deactivation
├── docs/
│   └── phase6.md                  # This document
└── tests/
    └── test_web_ui.py             # 5 automated tests verifying SSR, assets & security
```

---

## 4. Core Pages & Features

### 4.1 Today / Dashboard (`/` or `/today`)
- **Nutrition Hero Card**: Displays remaining calories vs. target with progress bar, color-coded for over/under budget.
- **Macro Progress Grid**: Visual progress bars for Protein, Carbohydrates, and Fat with current grams vs. target grams.
- **Today's Meals**: Chronological breakdown of meals logged today with calorie & macro badges and item counts.
- **Quick Action Modals**: Fast modal dialogs to log a meal or record current weight without leaving the dashboard.
- **Empty State**: Welcoming guidance prompt when no meals have been logged yet today.

### 4.2 Coach (`/coach`)
- **Conversational Stream**: Message bubbles distinguishing user and coach messages with timestamps.
- **Action Badges**: Visual confirmation tags rendered directly under coach messages when backend tools trigger meal or weight logs (e.g. `✓ Öğün günlüğüne eklendi: 650 kcal`).
- **Typing Indicator**: Smooth animated dots while waiting for AI generation.
- **Auto-Scrolling**: Keeps latest message in view without jarring jumps.
- **Smart Composer**: Auto-expanding textarea with `Enter` to send and `Shift + Enter` for new lines.
- **Idempotent Retry**: Failed requests display an in-line retry button that preserves `client_request_id`, guaranteeing no duplicate backend execution.

### 4.3 Meals (`/meals`)
- **Date Navigation**: Previous/Next day buttons, "Bugün" shortcut, and a native HTML5 date picker.
- **Daily Totals**: Aggregated daily calorie, protein, carbohydrate, and fat totals.
- **Meal Cards**: Detailed list of meals with items, grams, calories, and macros.
- **Meal CRUD**: Modal dialogs to add new meals with dynamic ingredient rows and delete meals with native confirmation.

### 4.4 Progress (`/progress`)
- **Weight Metrics**: Displays current weight, target weight, and weight delta.
- **Trend Badge**: Categorizes progress as "Kilo Veriyor", "Kilo Alıyor", or "Kilosunu Koruyor".
- **Zero-Dependency SVG Line Chart**:
  - Dynamically calculates min/max bounds and scales data points across responsive SVG viewBox.
  - Interactive SVG circles with tooltips showing exact date and weight.
  - Dashed target weight reference line when a target is defined in user profile.
- **7-Day Adherence Card**: Days on track vs. total days logged in the last week.
- **Weight Log CRUD**: Quick modal to record new weights or delete past entries.

### 4.5 Profile & Long-Term Memory (`/profile`)
- **Canonical Profile Form**: Update calorie target, protein target, carb target, fat target, height, and date of birth.
- **Koçun Hakkında Bildikleri (LTM)**:
  - Lists all active long-term memories extracted by the Phase 5 engine.
  - Category badges (`food_preference`, `food_dislike`, `dietary_habit`, `routine`, `constraint`).
  - Confidence indicators.
  - "Unut" (Delete/Forget) button with confirmation modal calling `DELETE /api/v1/users/{user_id}/memories/{memory_id}`.

---

## 5. Design System & Responsiveness

- **Color Palette**:
  - Primary Accent: Sage/Forest Green (`#2d6a4f`, `#1b4332`, `#52b788`).
  - Backgrounds: Warm off-white/cream (`#f8f9fa`, `#f1f3f5`).
  - Cards: Crisp white (`#ffffff`) with subtle elevations and 1px border.
  - Accents: Protein (Indigo `#4361ee`), Carbs (Amber `#d97706`), Fat (Rose `#e11d48`).
- **Typography**: Native modern system font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
- **Mobile Navigation**: Sticky bottom navigation bar for screen widths `< 768px` with Apple safe-area padding (`env(safe-area-inset-bottom)`).
- **Desktop Navigation**: Fixed left sidebar for screen widths `>= 768px` with expansive multi-column dashboard layouts.

---

## 6. User Resolution & Development Bootstrap

NutriCoach implements a development user resolution mechanism in `api.js`:
1. Checks `localStorage.getItem("nutricoach_user_id")`.
2. If absent or invalid, calls `GET /api/v1/dev/bootstrap`.
3. `/api/v1/dev/bootstrap` queries existing users; if none exist, it creates a default user (`"Burak"`, `Europe/Istanbul`) with a healthy sample profile (`2200 kcal`, `150g protein`).
4. Caches the resolved user ID in `localStorage` and provides a quick user-switch dropdown in the UI to facilitate multi-user testing.

---

## 7. Security & API Key Protection

- The `GEMINI_API_KEY` is strictly server-side and is never passed to Jinja2 template contexts, static JavaScript files, or client-side storage.
- All client communication passes through NutriCoach's local REST endpoints (`/api/v1/*`).
- Automated tests (`test_no_secrets_in_rendered_html`) guarantee that environment variables and secret tokens are not leaked in DOM attributes or scripts.

---

## 8. Transition to Phase 7 (Authentication)

Phase 6 intentionally abstracts user identity retrieval behind `NutriAPI.getCurrentUserId()`. When Phase 7 introduces JWT authentication, sessions, and secure cookies:
1. `GET /api/v1/dev/bootstrap` and client-side `localStorage` ID caching will be superseded by standard `Authorization: Bearer <token>` or `HttpOnly` session cookies.
2. `api.js` will attach the authorization header in `request()`.
3. No template markup or UI component structure will need to be rewritten.
