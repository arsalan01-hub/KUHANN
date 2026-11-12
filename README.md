# KUHANN — Truck Search & Website Discovery Platform

KUHHAN finds truck-selling websites across Europe, inspects them for permission
(robots.txt, terms, official APIs), collects their advertisements into one
searchable database, and monitors price and listing changes over time.

KUHHAN is **not** a marketplace: every listing stays the property of the original
external website and every record links back to it. No public registration, no
transactions.

- Backend: FastAPI + SQLAlchemy 2 + Alembic (Python 3.12)
- Database: PostgreSQL 16
- Frontend: React 18 + TypeScript + Vite (no UI framework, own design system)
- Background work: a separate worker process reading `job_schedules` from the database

---

## 1. Feature overview

### Discovery
- Pluggable discovery providers: a bundled curated catalogue (28 European truck
  websites) and an optional search-API provider (Brave-style endpoint + key,
  both configured in System Settings).
- Every discovered domain is recorded as `newly_discovered`. Discovery never
  grants collection rights — a human approves the access method.
- Site inspector records robots.txt rules, terms hints, sitemap/API signals and a
  compatibility report before any collection is configured.

### Collection
- Three connector kinds, all declarative (no user code is executed):
  - `json_feed` — an external JSON feed with field mapping
  - `html_listing` — CSS selectors for listing pages
  - `api_integration` — an official API described in API Management
- Normalisation: manufacturer/model cleanup, year, mileage, power, euro class,
  axle configuration, currency conversion to EUR, completeness percentage and
  missing-field tracking.
- Duplicate detection and price history per listing.

### Search & analysis
- Unified search across approved sources only, with filters for manufacturer,
  model, country, price range, year, mileage, power, euro class, new-in-window,
  price-changed-only, with-image and risk review.
- Facets, saved searches with background evaluation, saved trucks and favourites.
- Price analysis (averages by manufacturer/country), price history charts.
- Risk scoring: under-priced listings, data anomalies, duplicates.

### Administration
- RBAC: 24 permissions across four system roles (`super_admin`, `admin`,
  `manager`, `employee`), plus custom roles.
- Users, roles, API integrations (credentials encrypted at rest, masked in every
  response), sources, jobs and schedules, notifications, audit trail, system
  settings, backups, health monitoring.

> Notifications are in-app only. `notifications.email_enabled` exists in settings,
> but no mail transport is wired up yet.

---

## 2. Repository layout

```
backend/
  app/
    main.py            FastAPI app, security middleware, routers
    worker.py          background job loop (independent process)
    api/routes/        auth, users, sources, apis, listings, search, system
    api/               shared dependencies, filters, serializers
    connectors/        json feed, html listing, api integration
    services/          discovery, inspector, collector, normalise, search,
                       prices, risk, notifications, jobs, backups, bootstrap
    core/              config, security (JWT/bcrypt/TOTP), crypto (Fernet),
                       rate limiting, audit
    db/                engine/session, declarative base
    models/            SQLAlchemy models
  alembic/             migrations (single initial schema revision)
  tests/               112 pytest tests against a real PostgreSQL database
frontend/
  src/
    pages/             one file per screen
    components/        layout, UI kit, charts, listing table, filters
    api/               typed API client and response types
    context/           auth context
  vite.config.ts       dev proxy: /api -> http://localhost:8000
docs/deployment.md     production deployment on a Linux VPS (no Docker)
```

---

## 3. Local development

The Base44 sandbox runs everything with Compose (Postgres, migrations, API,
worker, Vite). The same pieces can be started by hand:

```sh
# 1. database
createdb kuhhan

# 2. backend
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://kuhhan:password@localhost:5432/kuhhan"
export SECRET_KEY="change-me"
alembic upgrade head
uvicorn app.main:app --reload --port 8000     # http://localhost:8000/api/docs

# 3. worker (second terminal, same environment)
python -m app.worker

# 4. frontend (third terminal)
cd frontend
npm ci
npm run dev                                    # http://localhost:5173, proxies /api
```

The API's startup bootstrap is idempotent: it creates the permissions, the four
system roles, the administrator, the default job schedules and the curated
website catalogue.

Development administrator defaults (change these outside development):

- `admin@kuhhan.local` / `KuhhanDev!2026`

---

## 4. Configuration

All settings come from environment variables (`backend/app/core/config.py`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://…/kuhhan` | PostgreSQL DSN |
| `SECRET_KEY` | dev value | JWT signing key — **required in production** |
| `ENCRYPTION_KEY` | derived from `SECRET_KEY` | Fernet key for stored API credentials |
| `ENVIRONMENT` | `development` | Free-form environment label |
| `ACCESS_TOKEN_TTL_MINUTES` | `720` | Session lifetime (12 hours) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | dev defaults | Bootstrap administrator |
| `SEED_SOURCE_CATALOGUE` | `true` | Seed the curated website catalogue |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins (empty = same-origin only) |
| `WORKER_POLL_SECONDS` | `15` | Worker tick interval |
| `BACKUP_DIR` | `<repo>/backend/var/backups` | Where backups are written |
| `BACKUP_RETENTION_DAYS` | `14` | Retention window |
| `OUTBOUND_TIMEOUT_SECONDS`, `OUTBOUND_MAX_BYTES`, `OUTBOUND_MAX_REDIRECTS` | 15 / 2 MB / 3 | Outbound HTTP limits |
| `ALLOW_PRIVATE_OUTBOUND` | `false` | Must stay `false` in production (SSRF guard) |
| `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS` | 10 / 60 | Login throttling |

Runtime behaviour that operators tune often lives in **System Settings** (stored
in the database, audited) rather than in the environment.

---

## 5. Security model

- Passwords hashed with bcrypt; login throttling (in-process sliding window) plus
  a durable per-user lockout after repeated failures.
- JWT bearer tokens; optional TOTP two-factor per user.
- Every endpoint is permission-guarded (`require_permission("…")`), not just
  role-checked.
- Outbound HTTP (discovery, inspector, connectors) passes through an SSRF guard:
  http/https only, no embedded credentials, no loopback/private/link-local
  addresses, each redirect re-validated, body size and redirect caps.
- Third-party API credentials are encrypted with Fernet at rest and never
  returned by the API (only a masked hint).
- Security headers and request IDs on every response; audit log for
  administrative actions.

---

## 6. Background jobs

The worker executes due schedules from `job_schedules`. Seeded schedules:

| Job | Interval |
| --- | --- |
| `discover_websites` | daily |
| `collect_all` | hourly |
| `run_saved_searches` | hourly |
| `refresh_risk` | daily |
| `database_backup` | daily |
| `retention_cleanup` | weekly |

All jobs can be triggered manually from the Jobs screen or the API; changes to
schedules are audited. The worker writes a heartbeat (`runtime.worker_heartbeat`)
that the health screen and the compose healthcheck read.

---

## 7. API

- OpenAPI docs: `/api/docs` (ReDoc at `/api/redoc`, schema at `/api/openapi.json`)
- Health: `GET /api/health` → database reachability, version, preview flag
- 81 endpoints across `auth`, `users`, `sources`, `apis`, `listings`, `search`
  and `system` (dashboard, settings, audit, jobs, notifications, backups, health)

---

## 8. Tests

```sh
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite creates the `kuhhan_test` database next to the configured one and runs
against real PostgreSQL (never SQLite). It covers authentication, RBAC, source
approval flow, connectors and jobs, normalisation, search/listings, API
integrations, security (SSRF, encryption, rate limiting) and operations
(settings, audit, backups). Frontend type checking: `cd frontend && npm run typecheck`.

---

## 9. Deployment

Production runs on a Linux VPS without Docker — systemd services for the API and
worker, nginx serving the built frontend and proxying `/api`, PostgreSQL from the
distribution. Full steps: [docs/deployment.md](docs/deployment.md).
