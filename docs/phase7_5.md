# Phase 7.5: Smart Inputs (Meal Photo Analysis & Web Search Grounding)

## 1. Executive Summary

Phase 7.5 expands NutriCoach's capabilities with two high-impact smart input features while reinforcing existing authentication defenses:
1. **Auth Security Hardening**: Default enforcement preventing unauthenticated access across legacy `/api/v1/users/{user_id}/...` endpoints (`allow_unauthenticated_legacy=False`).
2. **Feature A — Meal Photo Analysis**: Mobile-friendly camera photo capture and upload, client/server file validation, in-memory Pillow processing, Gemini multimodal visual recognition, staging proposal review UI, and explicit user confirmation before database persistence (with zero image bytes stored in DB).
3. **Feature B — Web-aware Coach / Google Search Grounding**: Intelligent heuristic query routing activating Gemini's official `google_search` tool for branded food products, restaurant menus, and current events, paired with grounding source citations and chat idempotency preservation.

---

## 2. Auth Security Hardening

- **Default Setting**: `allow_unauthenticated_legacy: bool = False` added to `Settings` (`app/core/config.py`).
- **Enforcement**: Centralized in `assert_user_access(user_id, current_user, settings)` (`app/routes/dependencies.py`):
  - When unauthenticated (`current_user is None`), raises `HTTP 401 Unauthorized`.
  - When authenticated as User A but requesting User B's resources, raises `HTTP 403 Forbidden`.
  - In unit tests where `allow_unauthenticated_legacy=True` is explicitly configured, legacy unauthenticated access remains backward-compatible.
- **Scope**: Applied to all legacy routers (`users.py`, `nutrition.py`, `chat.py`, `memories.py`).

---

## 3. Feature A: Meal Photo Analysis

### 3.1 Architecture & Workflow
```
[Mobile Camera / Gallery]
           | (<input type="file" capture="environment">)
           v
[Client-Side Validation] (< 10MB, image MIME)
           |
           v (POST /api/v1/me/meals/analyze-photo + CSRF)
[Server Validation] (Content-Type, size guard, Pillow verify)
           |
           v (Downscale max 1536x1536, convert to JPEG/PNG in memory)
[Gemini Multimodal API] (client.models.generate_content)
           |
           v (Structured JSON: meal_type, items, confidence, warnings)
[Photo Review Dialog] (Editable items, macros, total kcal, disclaimer)
           |
           v (User explicitly reviews, edits, confirms)
[POST /api/v1/me/meals] (Persists standard meal record)
```

### 3.2 Key Specifications
- **Input Tag**: `<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment">`. On mobile devices, this prompts the camera directly while still permitting gallery selection.
- **Image Safety & Validation**:
  - Max file size: 10 MB (HTTP 413 if exceeded).
  - MIME types: `image/jpeg`, `image/png`, `image/webp` (HTTP 400 if unsupported).
  - Pillow verification: prevents decompression bombs and corrupted image streams.
  - Image downscaling: resized to max dimension 1536px if larger, preserving aspect ratio and reducing network payload.
- **Zero Image Storage**:
  - Image bytes exist only in volatile server memory during analysis and are immediately discarded.
  - No database schema migrations were added; no BLOB columns, file paths, or image storage buckets exist in the database.
- **Review & Staging UI**:
  - Analysis alone creates zero database records.
  - Opens `modalPhotoMealReview` displaying photo preview, editable items table (food name, portion, unit, calories, protein, carbs, fat), add/delete item buttons, calculated totals, and educational disclaimer.
  - Explicit confirmation triggers `api.createMeal(...)`.

---

## 4. Feature B: Web-aware Coach & Google Search Grounding

### 4.1 Routing Heuristic (`should_use_search`)
NutriCoach selectively enables Google Search only when real-time information or external knowledge is necessary, saving latency and token overhead for standard food queries:
- **Search Triggered (`enable_search=True`)**:
  - Branded foods and restaurants: Starbucks, McDonald's, Burger King, KFC, Domino's, Subway, Algida, Eti, Ülker, Danone, Nutella, Migros, Getir, Trendyol, etc.
  - Current events & live data: "bugünkü", "güncel", "son dakika", "skor", "maçı", "araştırmalar", "rehberi", etc.
  - Explicit user intent: "internetten bak", "web'den kontrol et", "google'da ara".
- **Standard Local/DB Routing (`enable_search=False`)**:
  - Generic nutrition questions ("100 gram tavuk kaç kalori?", "1 porsiyon mercimek çorbası").
  - Memory & logging intents ("Dün ne yedim?", "Bugün 75 kilo çıktım").

### 4.2 SDK Grounding Integration
- **SDK Tool**: `tools=[types.Tool(google_search=types.GoogleSearch())]` passed to `client.models.generate_content`.
- **Candidate Grounding Metadata Extraction**:
  - Parses `candidate.grounding_metadata.grounding_chunks`.
  - Extracts web title and URL: `{'title': chunk.web.title, 'url': chunk.web.uri}`.
- **Frontend Presentation**:
  - Displays `🌐 Web ile doğrulandı` badge beneath coach message bubble.
  - Renders external links with secure `target="_blank" rel="noopener noreferrer"` attributes.
  - When search is not invoked or no sources are returned, citations remain completely empty (no fake links).
- **Idempotency Preservation**:
  - Stored within `MessageRead.grounding_sources`.
  - Replaying a request with the same `client_request_id` returns the exact grounded response and citations without duplicate API calls or duplicate database effects.

---

## 5. Database Revision Status

- **Alembic Revision**: `0005 (head)` (Identical to Phase 7 baseline).
- **Schema Changes**: 0 new tables, 0 altered columns.
- **Verification**: `alembic check` reports "No new upgrade operations detected".

---

## 6. Verification & Test Suite Summary

- Total tests: **156 passed, 0 failed**.
- New test suite: `tests/test_smart_inputs.py` covering 14 dedicated test cases:
  1. `test_photo_analysis_requires_authentication` (401 response without session cookie)
  2. `test_photo_analysis_valid_jpeg_success` (structured item extraction)
  3. `test_photo_analysis_valid_png_success` (PNG support)
  4. `test_photo_analysis_invalid_mime_type_rejected` (400 on invalid MIME)
  5. `test_photo_analysis_oversized_rejected` (413 on >10MB)
  6. `test_photo_analysis_corrupted_image_rejected` (400 on corrupted payload)
  7. `test_photo_analysis_creates_no_database_records` (staging isolation)
  8. `test_photo_confirmation_creates_exact_meal` (single confirmed meal created)
  9. `test_zero_image_storage_in_db_schema` (database schema has no image columns)
  10. `test_cross_user_isolation` (User A and User B resource separation)
  11. `test_search_routing_heuristics` (selective search routing)
  12. `test_chat_search_grounding_invoked_for_branded_food` (Google Search tool activated)
  13. `test_chat_generic_query_has_empty_grounding_sources` (no search invoked, empty citations)
  14. `test_chat_idempotency_preserved_with_grounding` (retry returns identical grounded message)
