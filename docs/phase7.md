# Phase 7: Authentication & Multi-User Architecture

## 1. Executive Summary

Phase 7 elevates NutriCoach from a single-user / development-user prototype into a secure, production-grade multi-user nutrition platform.

All legacy bootstrap mechanisms (`nutricoach_dev_user`, `GET /api/v1/dev/bootstrap`) have been disabled by default. Identity and session state are managed via cryptographically secure server-side sessions, stored only as SHA-256 digests, and transported strictly via `HttpOnly`, `SameSite=Lax` session cookies. Passwords are protected using `Argon2id` with defense against timing attacks.

Frontend interactions have migrated to a first-class `/api/v1/me` domain with HMAC-SHA256 CSRF protection, while legacy `/api/v1/users/{user_id}/...` endpoints enforce strict object-level authorization (`assert_user_access`), preventing unauthorized cross-user access.

---

## 2. Security Architecture & Threat Model

### 2.1 Password Hashing (Argon2id)
- **Algorithm**: Argon2id via `argon2-cffi` (`Type.ID`).
- **Parameters**: RFC 9106 recommended parameters:
  - Memory cost: 64 MiB (`time_cost=3`, `memory_cost=65536`)
  - Parallelism: 4 threads (`parallelism=4`)
  - Hash length: 32 bytes (`hash_len=32`)
- **Zero Leakage**: Passwords and password hashes are excluded from all Pydantic response schemas (`UserRead`, `UserProfileRead`, etc.), never logged, and never sent to AI providers.

### 2.2 Server-Side Sessions & Token Model
- **Token Generation**: 256 bits (32 bytes) of cryptographic randomness via `secrets.token_urlsafe(32)`.
- **Digest Storage**: Plaintext tokens are NEVER stored in the database. The database stores only `token_hash = sha256(raw_token).hexdigest()`. A compromised database dump yields zero active session credentials.
- **Transport**: Stored exclusively in an `HttpOnly`, `SameSite=Lax`, `Path=/` cookie named `nutricoach_session`.
  - In production (`APP_ENV=production`), the `Secure` flag is enforced.
  - In local development (`APP_ENV=local`), plain HTTP is supported seamlessly.
- **Session Lifecycle**:
  - Expiration: Configurable TTL (`session_ttl_days`, default 30 days).
  - Throttled Activity: `last_seen_at` timestamps are updated at most once every 5 minutes to prevent unnecessary DB write contention.
  - Revocation: Immediate on logout (`revoked_at = utc_now()`).
  - Strict Validation: Requests with expired, revoked, or non-existent tokens return `401 Unauthorized`.

### 2.3 CSRF Protection
- **Mechanism**: Session-bound HMAC-SHA256 CSRF token:
  $$\text{CSRF Token} = \text{HMAC-SHA256}(\text{key}=\text{csrf\_secret}, \text{data}=\text{token\_hash})$$
- **Delivery**: Embedded into HTML templates via `<meta name="csrf-token" content="{{ csrf_token }}">`.
- **Validation**: All state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) submitted by browser clients must provide the `X-CSRF-Token` header. Safe methods (`GET`, `HEAD`, `OPTIONS`) are exempt.
- **Constant-Time Verification**: Validated using `hmac.compare_digest` to prevent timing attacks.

### 2.4 Object-Level Authorization & Defense in Depth
- **Dedicated `/api/v1/me` Endpoints**:
  - Browser UI and mobile clients bind directly to the authenticated session context.
  - Endpoints include `/api/v1/me`, `/api/v1/me/profile`, `/api/v1/me/meals`, `/api/v1/me/nutrition/daily`, `/api/v1/me/nutrition/weekly`, `/api/v1/me/weight-logs`, `/api/v1/me/conversations`, `/api/v1/me/memories`, `/api/v1/me/change-password`.
- **Legacy Endpoint Enforcement (`/api/v1/users/{user_id}/...`)**:
  - Retained for backwards compatibility with tests.
  - Protected by `assert_user_access(user_id, current_user)`: if an authenticated session attempts to access resources under a different `user_id`, a `403 Forbidden` error is raised immediately.
- **Database-Level Isolation**:
  - All queries filter explicitly on `user_id == current_user.id`.

### 2.5 Security Headers Middleware
All HTTP responses include defense-in-depth security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## 3. Database Migration (`0005_auth.py`)

Alembic revision `0005_auth.py` transitions the schema from `0004` to `0005 (head)`:

```
0001 (foundation) -> 0002 (nutrition) -> 0003 (chat) -> 0004 (memory) -> 0005 (auth) [head]
```

### Table Changes
1. **`users` Table**:
   - Added `password_hash VARCHAR(255) NULL`
   - Added `updated_at TIMESTAMP NULL`
2. **`auth_sessions` Table (New)**:
   - `id VARCHAR(36) PRIMARY KEY`
   - `user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE`
   - `token_hash VARCHAR(64) NOT NULL UNIQUE` (indexed)
   - `created_at TIMESTAMP NOT NULL`
   - `expires_at TIMESTAMP NOT NULL` (indexed)
   - `last_seen_at TIMESTAMP NOT NULL`
   - `revoked_at TIMESTAMP NULL`

Both forward migration (`upgrade`) and backward migration (`downgrade`) are fully tested and clean.

---

## 4. Web UI & Frontend Integration

### 4.1 Authentication Pages
- **`/login`**: Clean, accessible login form with email/password validation, error alerts, and "Hesabın yok mu? Kayıt Ol" link. Authenticated users are automatically redirected to `/today`.
- **`/register`**: Registration form with name, email, password (min 8 characters), timezone selector, and terms confirmation.
- **`/logout`**: Seamless one-click logout invalidating the server session and clearing the cookie.

### 4.2 Application Shell & Navbar
- In unauthenticated state, displays "Giriş Yap" and "Kayıt Ol" links.
- In authenticated state, displays user avatar/initials, user name, "Çıkış Yap" action, and active navigation tabs (Bugün, Koç, Öğünler, İlerleme, Profil).
- Development user switcher removed from production UI.

### 4.3 Profile Page Updates (`/profile`)
- **Hesap Bilgileri**: View registered name, email, and timezone.
- **Şifre Değiştir**: Secure password change form verifying existing password before hashing and persisting the new password.

### 4.4 API Client (`app/static/js/api.js`)
- Automatic extraction and injection of `X-CSRF-Token` header for all mutating fetch requests.
- Cookie credentials transported via `credentials: 'same-origin'`.
- Automatic 401 interception: redirects user to `/login` if a session expires during active use.

---

## 5. Verification & Test Suite

NutriCoach has 141 automated tests covering:
- Argon2id password hashing and verification
- Session creation, lookup, expiration, and revocation
- SHA-256 token hashing and secure cookie headers
- CSRF validation on mutating endpoints and bypass on safe endpoints
- Complete user isolation (User A vs User B for profiles, meals, weights, conversations, and memories)
- 403 Forbidden enforcement on cross-user path manipulations
- Full Alembic 0004 -> 0005 upgrade and downgrade verification
- Web UI SSR templates and authentication redirects

```bash
# Run complete test suite
pytest
# Result: 141 passed in 7.88s
```
