# Phase 5: Long-Term Memory (LTM) Architecture & Implementation

## 1. Executive Summary

Phase 5 introduces safe, durable, and bounded Long-Term Memory (LTM) for NutriCoach. The coach now reliably remembers qualitative facts about the user—such as food preferences, dislikes, dietary habits, schedules, and everyday constraints—across chat sessions without relying on volatile chat history windows.

Critically, Long-Term Memory is strictly separated from:
- **Canonical User Profile**: Quantitative goals (calorie target, macros, height, date of birth) live in `user_profiles` and can never be altered autonomously by memory extraction.
- **Domain Records**: Concrete logged entities (meals, items, weight logs) remain source-of-truth logs with Decimal-precision math and timezone awareness.
- **Volatile Chat History**: Session messages are bounded; memories persist durably in PostgreSQL/SQLite.

---

## 2. Database Schema & Migration (`0004_memory.py`)

### 2.1 Table: `memories`
| Column | Type | Constraints / Details |
|---|---|---|
| `id` | Integer | Primary key, autoincrement |
| `user_id` | Integer | NOT NULL, Indexed, FK -> `users.id` (CASCADE) |
| `source_message_id` | Integer | Nullable, compound FK -> `messages.id` (SET NULL) |
| `category` | String(32) | NOT NULL, Check constraint (`food_preference`, `food_dislike`, `dietary_habit`, `routine`, `constraint`) |
| `key` | String(64) | NOT NULL, Normalized lowercase keyword (e.g. `yumurta`, `kahve`, `aksam_yemegi`) |
| `value` | Text | NOT NULL, Concise qualitative fact (e.g. "Kahvaltıda yumurta sevmiyor") |
| `confidence` | Numeric(3, 2) | NOT NULL, Check constraint (`0.00 <= confidence <= 1.00`) |
| `status` | String(16) | NOT NULL, Check constraint (`active`, `superseded`, `deleted`), default `'active'` |
| `created_at` | DateTime(timezone=True) | NOT NULL, server_default=now() |
| `updated_at` | DateTime(timezone=True) | NOT NULL, server_default=now() |
| `last_confirmed_at` | DateTime(timezone=True) | NOT NULL, server_default=now() |

### 2.2 Integrity & Isolation
- **Compound Foreign Key**:
  `ForeignKeyConstraint(['user_id', 'source_message_id'], ['messages.user_id', 'messages.id'], ondelete='SET NULL')`
  This guarantees database-level tenant isolation: a memory can never reference a message belonging to another user.
- **Indexes**:
  - `ix_memories_user_id_status` on `(user_id, status)`
  - `ix_memories_user_id_category` on `(user_id, category)`
  - `ix_memories_user_id_key` on `(user_id, key)`

---

## 3. Extraction Pipeline & Pre-Filter Heuristics

To protect latency and API budget, memory extraction does not run on every user interaction.

### 3.1 Deterministic Pre-Filter (`should_extract_memories`)
- Evaluates raw message text before calling the LLM.
- **Bypassed / Skipped**:
  - Greetings (`"merhaba"`, `"günaydın"`, `"selam"`).
  - Routine meal logs (`"200g tavuk ve pilav yedim"`).
  - Weight logs (`"kilom 75.5"`).
  - Fleeting emotions or temporary states (`"bugün yorgunum"`, `"canım istemiyor"`).
- **Triggered**:
  - Strong preference markers: `"sevmiyorum"`, `"bayılırım"`, `"asla yemem"`, `"tercih ederim"`.
  - Dietary habits & constraints: `"vejetaryen"`, `"alerji"`, `"intolerans"`, `"oruç"`.
  - Routines: `"genelde"`, `"her sabah"`, `"hafta sonu"`, `"rutinim"`.

### 3.2 Structured Extraction via Gemini (`extract_memories`)
- Uses official `google-genai` SDK with `response_mime_type="application/json"`.
- **Wire Schema Sanitization**: To prevent `GoogleGenAIError (400 INVALID_ARGUMENT)` from unsupported OpenAPI keywords, `wire_schema_memory()` strips `maxItems`, `discriminator`, and `default`. Length constraints (`max_length=3`) are enforced by Pydantic on validation.
- Instructed to capture only durable facts and omit temporary or one-off statements.

---

## 4. Conflict Resolution & Safety Guards

### 4.1 Sensitive Data Filtering (`is_sensitive_candidate`)
Medical diagnoses, prescription drugs, mental health statements, and severe health conditions are rejected prior to persistence. NutriCoach is a nutritional assistant, not a clinical diagnostic system.

### 4.2 Deduplication
When a user repeats an already remembered preference (matching `user_id`, `category`, and normalized `key`):
- No duplicate row is inserted.
- The existing record's `value`, `confidence`, and `last_confirmed_at` are updated.

### 4.3 Contradiction & Supersession
When a user expresses a contradictory preference:
- Example: User previously had `food_dislike` for `"yogurt"`, now states `"Artık yoğurt yiyorum"` (`food_preference`).
- The existing contradictory memory is marked `status = 'superseded'`.
- The new memory is inserted with `status = 'active'`.

### 4.4 Explicit Forgetting
When the user says `"Yumurta sevmediğimi unut"` or `"unut bunu"`:
- The system parses the target key and marks active matching memories as `status = 'deleted'`.

---

## 5. Context Engine Integration

### 5.1 Relevance Filtering
In `build_coach_context`, active memories are retrieved and filtered based on the current interaction:
- Queries regarding meal planning / food suggestions match `food_preference`, `food_dislike`, and `dietary_habit`.
- Workout / schedule questions match `routine`.
- General greetings receive 0 irrelevant memory dumps, keeping prompt tokens minimal and focused.

### 5.2 Bounded Injection
- Hard limit of `context_max_memories` (default 10).
- If memories exceed the limit, the most confident and recently confirmed are chosen, and `memory_detail_truncated = True` is set on `CoachContext`.

### 5.3 Strict Precedence
In `COACH_INSTRUCTIONS`:
- User Profile numerical targets (e.g. 2000 kcal) always override qualitative memories.
- Explicit instructions from the current message take precedence over long-term memories.

---

## 6. Failure Isolation

Memory extraction and persistence run in a completely isolated sub-pipeline after meal/weight transactions have successfully committed:
- Any network error, timeout, or schema failure during memory extraction is safely caught and logged.
- The user's chat response and logged meals/weights are **never** rolled back or interrupted by a memory failure.

---

## 7. REST API Endpoints

- `GET /api/v1/users/{user_id}/memories?include_inactive=false`
  Lists memories for the specified user (user-isolated, 404 if user not found).
- `DELETE /api/v1/users/{user_id}/memories/{memory_id}`
  Deactivates (`status = 'deleted'`) the memory. Returns 204 No Content, or 404 if memory doesn't exist or belongs to another user.

---

## 8. Deferred Architecture (Explicit Out of Scope)
- Vector DB / Vector Embeddings (standard SQL indexes provide sub-millisecond retrieval at this scale).
- Autonomous modification of UserProfile targets.
- Third-party RAG pipelines.
- User Authentication / JWT (deferred to upcoming security phases).
