# Phase 8 — Production / Cloud Deployment Guide

NutriCoach has evolved from a local development environment into an enterprise-ready, containerized cloud application architected for **Google Cloud Run** and **Google Cloud SQL (PostgreSQL)**, integrated with Gemini AI and GitHub Actions CI/CD.

This document serves as the complete technical specification and operational deployment manual. It is structured into two main sections:
- **Section A**: Automated Repository Architecture & Configuration (Codebase components, Docker, CI/CD, migration tooling).
- **Section B**: Cloud Setup Manual for User + ChatGPT (Step-by-step GCP provisioning with commands).
- **Section C**: 20-Point Production Smoke Test Plan.

---

## Target Cloud Architecture

```
[ Browser / iPhone / Mac Client ]
               │
           HTTPS (TLS)
               ▼
[ Google Cloud Load Balancer / CDN ]
               │
               ▼ (X-Forwarded-Proto: https, Port 8080)
   ┌────────────────────────────────────────────────────────┐
   │ Google Cloud Run (Fully Managed Container)             │
   │  - Docker Container: python:3.11-slim (non-root)       │
   │  - Uvicorn ASGI Server (--proxy-headers)               │
   │  - FastAPI Application (version 0.8.0)                 │
   │  - TrustedHostMiddleware & Sliding-window Rate Limiter │
   │  - Fail-fast Production Settings Validation            │
   └───────────────┬────────────────────────┬───────────────┘
                   │                        │
       Cloud SQL Unix Socket           REST / HTTPS
       (/cloudsql/PROJECT:REGION:INSTANCE)  │
                   ▼                        ▼
     ┌────────────────────────┐  ┌─────────────────────┐
     │ Cloud SQL (PostgreSQL) │  │ Google Gemini API   │
     │  - Pooled connections  │  │  - google-genai SDK │
     │  - Zero data loss      │  │  - Search Grounding │
     │  - Alembic Head (0005) │  │  - Photo Analysis   │
     └────────────────────────┘  └─────────────────────┘
```

---

## SECTION A: Automated Repository Architecture

### 1. Containerization (`Dockerfile` & `.dockerignore`)
- **Base Image**: `python:3.11-slim` ensures minimal attack surface and lightweight image footprint (~200MB).
- **User Privileges**: Runs strictly under a non-root system user (`appuser`, UID 10001) to satisfy CIS benchmarks and container security standards.
- **Port Binding**: Dynamically evaluates `$PORT` (injected automatically by Google Cloud Run, defaulting to `8080`).
- **Proxy Headers**: Uvicorn is invoked with `--proxy-headers --forwarded-allow-ips='*'`, correctly parsing client IPs and `https` scheme through Google Cloud Frontends.
- **Exclusions**: `.dockerignore` strictly prevents shipping `.git`, virtual environments (`.venv`), SQLite database files (`*.db`), test suites, and unencrypted local `.env` files into build images.

### 2. Database Layer: Dual-Engine Support (SQLite & PostgreSQL)
NutriCoach dynamically accommodates both local SQLite development and production PostgreSQL:
- **PostgreSQL Driver**: Standardized on `psycopg2-binary>=2.9.9,<3`.
- **URL Normalization**: Automatically converts legacy `postgres://` or bare `postgresql://` connection strings into SQLAlchemy-compliant `postgresql+psycopg2://`.
- **Production Connection Pooling**:
  - `pool_pre_ping=True`: Detects and transparently discards stale/dropped database connections before executing queries.
  - `pool_recycle=1800`: Automatically recycles TCP connections every 30 minutes to stay ahead of firewall timeouts.
  - `pool_size=5`, `max_overflow=10`: Bounds concurrency per instance to avoid exhausting Cloud SQL connection limits.
- **Alembic Schema Head**: Current head is `0005` (incorporating user auth, profile, meal photos, conversation memory, and selective web search logs).

### 3. Production Hardening & Fail-Fast Validation (`app/core/config.py`)
When `APP_ENV=production`, NutriCoach executes strict fail-fast startup assertions:
1. **Secret Entropy**: Rejects default development keys (`nutricoach-insecure-dev-secret-change-in-prod` and `nutricoach-csrf-dev-secret`). `SECRET_KEY` and `CSRF_SECRET` must be set and contain >= 32 characters.
2. **Database Engine**: Strictly disallows `sqlite:///` URLs in production.
3. **Insecure Flags**: Forcibly blocks startup if `enable_dev_bootstrap=True` or `allow_unauthenticated_legacy=True`.
4. **Enforced Cookie Security**: `is_cookie_secure` property guarantees that session cookies carry the `Secure` flag in production regardless of overrides.
5. **Dynamic Host Protection**: `TrustedHostMiddleware` filters traffic using `ALLOWED_HOSTS`.
6. **Authentication Rate Limiting**: In-memory sliding window rate limiter throttles brute-force attempts on `POST /api/v1/auth/login` and `/api/v1/auth/register` (10 attempts per minute per IP, responding with HTTP 429 and `Retry-After`).

### 4. Data Migration Tool (`app/scripts/migrate_sqlite_to_pg.py`)
Facilitates one-time or scheduled transfer of existing local SQLite data into Cloud SQL PostgreSQL:
- **Safe Pre-Flight**: Verifies that the target database schema matches Alembic `head` revision before writing.
- **Topological Integrity**: Inserts records according to explicit foreign-key dependency order:
  `users` ➔ `user_profiles` ➔ `auth_sessions` ➔ `meals` ➔ `meal_items` ➔ `conversations` ➔ `messages` ➔ `ai_requests` ➔ `memories`.
- **Dry-Run Mode**: Supports `--dry-run` flag to inspect table row counts without committing data.

```bash
# Example invocation
python -m app.scripts.migrate_sqlite_to_pg \
  --sqlite sqlite:///./nutricoach.db \
  --pg postgresql+psycopg2://user:pass@host:5432/nutricoach \
  --dry-run
```

### 5. CI/CD Pipelines (GitHub Actions)
- **CI (`.github/workflows/ci.yml`)**:
  - Triggers on pull requests and pushes to `main`.
  - Runs full automated test suite with Python 3.11.
  - Executes `alembic check` to prevent uncommitted schema drifts.
- **CD (`.github/workflows/cd.yml`)**:
  - Triggers on push to `main`.
  - Keyless authentication via **Workload Identity Federation** (no static JSON keys).
  - Builds and tags Docker image with commit SHA to Artifact Registry.
  - Executes isolated Cloud Run Job (`nutricoach-migrator`) to run `alembic upgrade head` before updating the web service.
  - Deploys container to Cloud Run with attached Cloud SQL instance and mounted Secret Manager secrets.

---

## SECTION B: Step-by-Step GCP Provisioning Manual

> [!IMPORTANT]
> The following steps should be executed by the developer using the `gcloud` CLI or Google Cloud Console in collaboration with ChatGPT. No billing or cloud account operations are performed automatically by the agent.

### Step 1: Configure Project & Core Settings
```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="europe-west3" # Frankfurt or preferred region
export AR_REPO="nutricoach-repo"
export CLOUDSQL_INSTANCE="nutricoach-db"
export DB_NAME="nutricoach"
export DB_USER="nutricoach_app"

gcloud config set project $GCP_PROJECT_ID
```

### Step 2: Enable Required Google APIs
```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com
```

### Step 3: Create Artifact Registry Repository
```bash
gcloud artifacts repositories create $AR_REPO \
  --repository-format=docker \
  --location=$GCP_REGION \
  --description="NutriCoach Docker Repository"
```

### Step 4: Create Cloud SQL PostgreSQL Instance
For cost-effective production deployment:
```bash
gcloud sql instances create $CLOUDSQL_INSTANCE \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$GCP_REGION \
  --storage-size=10GB \
  --storage-auto-increase \
  --backup-start-time=02:00

# Create application database
gcloud sql databases create $DB_NAME --instance=$CLOUDSQL_INSTANCE

# Generate strong database password and create user
DB_PASSWORD=$(openssl rand -base64 24)
gcloud sql users create $DB_USER \
  --instance=$CLOUDSQL_INSTANCE \
  --password="$DB_PASSWORD"

echo "Database user password: $DB_PASSWORD"
```

### Step 5: Store Application Secrets in Secret Manager
Generate cryptographic secrets:
```bash
SECRET_KEY_VAL=$(openssl rand -hex 32)
CSRF_SECRET_VAL=$(openssl rand -hex 32)
GEMINI_KEY_VAL="your-actual-gemini-api-key"

# Cloud SQL Unix Socket Connection String:
DB_URL_VAL="postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${GCP_PROJECT_ID}:${GCP_REGION}:${CLOUDSQL_INSTANCE}"

echo -n "$DB_URL_VAL" | gcloud secrets create nutricoach-db-url --data-file=-
echo -n "$SECRET_KEY_VAL" | gcloud secrets create nutricoach-secret-key --data-file=-
echo -n "$CSRF_SECRET_VAL" | gcloud secrets create nutricoach-csrf-secret --data-file=-
echo -n "$GEMINI_KEY_VAL" | gcloud secrets create nutricoach-gemini-key --data-file=-
```

### Step 6: Create Application Service Account & Grant Permissions
```bash
export SA_NAME="nutricoach-runner"
export SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME \
  --display-name="NutriCoach Cloud Run Runner"

# Grant Cloud SQL Client permission
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"

# Grant Secret Manager Accessor permission
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 7: Configure Workload Identity Federation for GitHub Actions
```bash
# Create Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Bind Service Account to GitHub Repo
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-pool/attribute.repository/BurakEfeYildiz/NutriCoach"

# Grant deployer permissions to Service Account
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"
```

### Step 8: Create Alembic Migration Cloud Run Job
Running migrations in a dedicated job guarantees **zero-concurrency** migration collisions:
```bash
gcloud run jobs create nutricoach-migrator \
  --image="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/nutricoach:latest" \
  --region=$GCP_REGION \
  --command="alembic" \
  --args="upgrade,head" \
  --service-account="${SA_EMAIL}" \
  --set-cloudsql-instances="${GCP_PROJECT_ID}:${GCP_REGION}:${CLOUDSQL_INSTANCE}" \
  --set-env-vars="APP_ENV=production" \
  --set-secrets="DATABASE_URL=nutricoach-db-url:latest"
```

### Step 9: Configure GitHub Secrets and Variables
In your GitHub repository settings (**Settings > Secrets and variables > Actions**):

**Variables**:
- `GCP_PROJECT_ID`: Your GCP project ID.
- `GCP_REGION`: e.g. `europe-west3`.
- `GCP_AR_REPO`: `nutricoach-repo`.
- `GCP_CLOUDSQL_INSTANCE`: `${GCP_PROJECT_ID}:${GCP_REGION}:${CLOUDSQL_INSTANCE}`.

**Secrets**:
- `GCP_WIF_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- `GCP_WIF_SERVICE_ACCOUNT`: `${SA_EMAIL}`

---

## SECTION C: 20-Point Production Smoke Test Plan

After deployment, perform this end-to-end verification checklist against your live Cloud Run domain (e.g., `https://nutricoach-xyz.a.run.app`):

| # | Check Area | Step & Verification Action | Expected Outcome |
|---|---|---|---|
| 1 | **SSL/TLS Security** | Open `https://<domain>/health` in browser. | HTTPS green padlock, HTTP 200 `{"status": "ok"}`. |
| 2 | **HTTP to HTTPS Redirect** | Attempt HTTP access: `curl -I http://<domain>/`. | HTTP 301/302 redirecting to `https://`. |
| 3 | **Security Headers** | Inspect headers on `/login`. | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`. |
| 4 | **Landing Page** | Navigate to `https://<domain>/`. | Clean UI, NutriCoach branding, Login/Register buttons. |
| 5 | **User Registration** | Register new user: `prod_user@example.com` + password. | Successful registration, redirected to onboarding or dashboard. |
| 6 | **Cookie Flags** | Inspect application cookies in Chrome DevTools. | `nutricoach_session` has `HttpOnly`, `SameSite=Lax`, and **`Secure`** flags. |
| 7 | **Profile Onboarding** | Fill profile: age (30), height (178), weight (75), goal (weight_loss). | Saved without error, profile metrics displayed. |
| 8 | **CSRF Defense** | Attempt POST to `/api/v1/auth/register` without CSRF token. | HTTP 403 Forbidden: Invalid CSRF token. |
| 9 | **Auth Rate Limiting** | Run 12 failed login attempts within 30 seconds. | 11th and 12th attempts return HTTP 429 Too Many Requests. |
| 10 | **Text Meal Logging** | Log meal: "150g grilled chicken breast and 1 cup brown rice". | Macro breakdown computed and meal logged in dashboard. |
| 11 | **Daily Nutrition Totals** | Check Dashboard daily card. | Calories, Protein, Carbs, Fat values accurately summed. |
| 12 | **Meal Photo Analysis** | Upload food picture via smart meal log interface. | Gemini Vision recognizes items and estimates portions. |
| 13 | **Weight Logging** | Log morning weight: `74.8` kg. | Weight log recorded; trend graph updates. |
| 14 | **Chat Interactive Session** | Send chat message: "Bugün ne kadar protein aldım?". | Coach replies context-aware with exact daily protein sum. |
| 15 | **Search Grounding** | Ask: "2026 Akdeniz diyeti rehberinde ceviz önerisi nedir?". | Gemini answers with Google Search grounding citations. |
| 16 | **Long-term Memory** | State in chat: "Ben fıstığa alerjiyim". | Long-term memory extraction detects allergy preference. |
| 17 | **Multi-User Isolation** | In Incognito window, register User B. Check User B's meals. | User B sees 0 meals; User A's data is strictly inaccessible. |
| 18 | **User Logout** | Click "Çıkış Yap" in user menu. | Session cookie cleared; redirected to `/login`. |
| 19 | **Protected Route Guard** | After logout, attempt navigating to `/dashboard`. | Redirected back to `/login?next=/dashboard`. |
| 20 | **Container Restart Persistence** | In GCP Console, execute `gcloud run services update nutricoach --min-instances 0` to trigger fresh instance recycle, then log in again. | All users, meals, weight logs, and chat histories persist intact from Cloud SQL. |
