# Mundus Backend — Implementation Roadmap & Technical Todo

## Completed Core Foundation & Baseline (Phase 0 - 5)
- [x] Project scaffold (FastAPI, routers, `pydantic-settings`, `.env`)
- [x] Database setup (SQLAlchemy ORM + SQLite / PostgreSQL)
- [x] Media upload endpoint (`/media/upload`) with Cloudinary & fallback
- [x] Health check endpoint (`/health`)
- [x] Global exception handlers and audit logging middleware
- [x] JWT Auth: `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/me`
- [x] Baseline Dump Point CRUD: `/dump-points/create`, `/dump-points/all`, `/dump-points/detail/{id}`, `/dump-points/update/{id}`
- [x] Baseline Check-Ins: `/check-ins/new`, `/check-ins/all`, `/check-ins/site/{site_id}`, `/check-ins/pairings/{site_id}`
- [x] Haversine geofence calculation & photo SHA-256 duplicate detection
- [x] Read-time overdue computation (7 days overdue, 10 days critical)
- [x] Agency Dashboard stats & sites: `/dashboard/stats`, `/dashboard/sites`, `/dashboard/contractors`

---

## Frontend-Handoff Implementations (Completed)

### 1. Dump-Point Fixes & Enhancements (§4.1 & §6, §7)
- [x] **Media Upload Schema**: Defined `MediaUploadResponse` schema returning `{"photo_url": str, "photo_hash": str, "filename": str, "content_type": str, "size_bytes": int}`.
- [x] **DumpPoint Schema & Model Updates**: Added `code` (e.g. `AK-UYO-NWN-04`) and `sector` (e.g. `Sector 4 · Uyo Urban Core`) to `DumpPoint` model, create, update, and response schemas.
- [x] **DumpPoint Deletion**: Added `DELETE /dump-points/{id}` and `DELETE /dump-points/delete/{id}` (Agency only) with cascade handling.
- [x] **Flexible Assignment**: Updated `PUT /dump-points/assign/{id}` and `PUT /dump-points/{id}/assign` to allow contractor-only assignment (`assigned_supervisor_id` optional).
- [x] **Chronological History Timeline Endpoint**: Formalized `GET /dump-points/history/{id}` and `GET /dump-points/{id}/history` returning structured events list `[ { "kind": "check_in" | "flag" | "clearance", "at": "...", "actor": "...", "note": "...", "before": {...}, "after": {...} } ]`.
- [x] **Fix Route Matching**: Ensured static/sub-routes (`/history/{id}`, `/{id}/history`, `/detail/{id}`, `/all`, `/assign/{id}`, `/update/{id}`, `/delete/{id}`) do not collide with wildcard `/{id}`.

### 2. Contractor Directory & Supervisor Workflow (§4.2)
- [x] **Contractor Model & Persistence**: Created `Contractor` model (`id`, `name`, `supervisor_name`, `supervisor_email`, `supervisor_user_id`, `created_at`).
- [x] **List Contractors**: Implemented `GET /contractors?q&status` for Agency table and assignment dropdowns with computed `site_count`, `overdue`, and `critical` metrics.
- [x] **Create Contractor**: Implemented `POST /contractors` `{name, supervisor_name, supervisor_email, password (min 6)}` creating contractor entity + supervisor user account.
- [x] **Supervisor Password Change**: Implemented `PATCH /users/{id}/password` and `PATCH /users/password` `{current?, new}` for supervisor settings screen.
- [x] **Supervisor Assigned Sites List**: Implemented `GET /contractor/sites` (supervisor JWT) returning only assigned sites sorted most overdue first.
- [x] **Supervisor Submissions History**: Implemented `GET /contractor/submissions?site_id&status` grouping check-ins by site & day into before/after pairs.

### 3. Community Reporter Management & Public Link (§4.3)
- [x] **Reporter Model & Database Table**: Created `Reporter` model (`id`, `name`, `phone`, `site_id`, `contractor_id`, `status: pending|approved|rejected|revoked`, `token`, `rejection_reason`, timestamps).
- [x] **Nominate Reporter**: Implemented `POST /reporters/nominate` `{site_id, contractor_id, name (min 2), phone (11 digits NG)}` with unique active phone validation.
- [x] **Reporter Roster**: Implemented `GET /reporters?site_id&status&q` for Agency queue (includes token) and Contractor view (masks/omits token).
- [x] **Approve Reporter**: Implemented `POST /reporters/{id}/approve` generating unique token + WhatsApp deep link (`https://wa.me/234...?text=...`).
- [x] **Reject & Revoke Reporter**: Implemented `POST /reporters/{id}/reject` `{reason?}` and `POST /reporters/{id}/revoke`.
- [x] **Public Reporter Page Endpoint**: Implemented `GET /r/{token}` (public, no JWT) resolving reporter name/status + site details.
- [x] **Public Flag-Site Endpoint**: Made `POST /reporters/flag-site` public using `reporter_token` (no JWT required), validating site match, rate-limiting 12h (returning 429 with `retry_in`), and triggering Brevo email + alerts.
- [x] **Contractor Alerts**: Implemented `GET /contractor/alerts` and `POST /contractor/alerts/{site_id}/seen` for field app banner alerts.

### 4. Agency Access Requests (§4.4)
- [x] **Agency Access Request Model**: Created `AgencyAccessRequest` (`id`, `full_name`, `email`, `status: pending|approved|rejected`, `created_at`).
- [x] **Submit Access Request**: Implemented `POST /agency/request-access` `{full_name (min 2), email}` returning 201.
- [x] **List Access Requests**: Implemented `GET /agency/requests` (Agency/admin only).

### 5. Notifications & Brevo Integration (§5)
- [x] **Brevo Email Client**: Implemented Brevo API client (`BREVO_API_KEY`, `BREVO_SENDER_EMAIL`) with HTML template and console fallback.
- [x] **Email Notification on Flag**: Async send Brevo email to supervisor when reporter flags site full.
- [x] **FCM Web-Push Device Tokens**: Implemented `POST /devices/register` `{fcm_token, role}`, `DeviceToken` model, and `POST /notify/test`.

### 6. Validation, Server Rules & Verification (§7 & §8)
- [x] **Model Validations**: String length, 11-digit NG phone validation, and coordinate bounds across all endpoints.
- [x] **Database Seed & Migrations**: Updated seed data with contractors, code/sector dump points, nominated reporters, alerts, and automatic SQLite migrations.
- [x] **Automated Test Suite**: 36/36 pytest integration tests passing cleanly.

---

## Phase 7: Monthly Contractor Payouts via Bachs Integration (Completed)

> **Core Scope Definition:**
> **Mundus does not create a new compensation stream. It calculates the portion of an existing monthly contractor stipend earned through verified service and provides the agency with a controlled mechanism to release that amount.**
> The demo payment integration operates in **test/sandbox mode** with **Bachs** (`https://sandbox-api.bachs.io`) and **does not move real money**.

- [x] **Contractor Model Extension**: Added `monthly_stipend`, `bank_name`, `bank_account_number`, `bank_account_name`, `bank_code`, `payment_provider_recipient_id`, and `payment_provider_metadata` to `Contractor` model and schemas.
- [x] **Payout Statement & Audit Log Models**: Created `PayoutStatement` with full snapshot calculation fields (`expected_clearances`, `verified_clearances`, `held_clearances`, `calculated_payout_amount`), immutable references (`MND-PO-YYYYMM-...`), `PayoutStatus` enum (`DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `PROCESSING`, `SUCCESS`, `FAILED`, `CANCELLED`), and `PayoutAuditLog`.
- [x] **Mathematical Clearance & Payout Formula Service**:
  - `expected_clearances = sum(floor(days_in_month / site.interval_days))` across all assigned dump points.
  - `verified_clearances`: Verified check-in pairs (before + after photo, geofence distance <= 100m, photo hash deduplicated, unflagged).
  - `held_clearances`: Flagged visits placed on hold for review.
  - `payout = min(monthly_stipend * (verified_clearances / expected_clearances), monthly_stipend)`.
- [x] **Progressive In-Month Earnings**: Implemented `GET /contractor/earnings` allowing contractors to view progressive earnings during the month without triggering transfers.
- [x] **Bachs Client & Recipient Management**: Created Bachs sandbox API client (`bachs_client.py`) with destination recipient creation (`POST /v1/payouts/destinations`), account resolution (`/payouts/resolve-account`), bank directory lookup (`/payouts/banks`), and transfer initiation (`POST /v1/payouts`).
- [x] **Idempotent Agency Approval**: Implemented `POST /agency/payouts/{id}/approve` with idempotency token verification, preventing duplicate transfers on retries or double clicks.
- [x] **Secure Webhook Handling**: Implemented `POST /payouts/webhooks/bachs` with HMAC-SHA256 signature verification (`X-Bachs-Signature-V2`), idempotently processing `payout.paid` -> `SUCCESS` and `payout.failed` -> `FAILED`.
- [x] **Held Clearances Review Queue**: Implemented `GET /agency/clearances/held` and `POST /agency/clearances/{site_id}/{date_str}/approve` allowing agencies to inspect flagged visits and clear them into verified count.
- [x] **CSV Export & Printable Voucher**: Implemented `GET /agency/payouts/export` and `GET /agency/payouts/{id}/receipt`.
- [x] **Agency Payments Dashboard UI**: Implemented rich responsive UI served at `/agency/payments/ui` and `/payments` with real-time KPI metrics, statement review modal, held clearance drawer, and sandbox webhook simulator.
- [x] **Test Suite**: 36 comprehensive pytest tests passing with 100% success rate.