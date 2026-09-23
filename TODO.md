# Mundus Backend — FastAPI Technical Todo

## Phase 0: Foundation
- [x] Project scaffold (FastAPI app, routers, `pydantic-settings` config, `.env`)
- [x] PostgreSQL setup + SQLAlchemy + Alembic migrations
- [x] Media storage (Cloudinary) for photos — never store binaries in Postgres
- [x] `/health` endpoint returning 200 (WatchUp integration)
- [x] Global exception handler + structured logging (site ID, user ID, timestamp)

## Phase 1: Auth & Roles
- [x] User model with `role` enum: `supervisor`, `agency`, `reporter`
- [x] JWT auth (hand-rolled with `pyjwt` + `bcrypt` with refresh tokens)
- [x] `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/me` endpoints
- [x] Role-based dependency guards (`Depends(require_role("supervisor"))` etc.)
- [x] Seed script for mock contractor/supervisor/agency accounts (demo data)

## Phase 2: Dump Point Registry (admin)
- [x] `DumpPoint` model: name, lat, lng, assigned_contractor_id, assigned_supervisor_id, interval_days, last_clearance_timestamp
- [x] CRUD endpoints: create, list, assign
- [x] Supervisor scoping — supervisors only see their assigned sites

## Phase 3: Check-In Flow & Anti-Fraud
- [x] `CheckIn` model: site_id, supervisor_id, type (`before`/`after`), photo_url, lat, lng, device_timestamp, server_timestamp, status
- [x] Photo upload endpoint (multipart) → push to object storage → store URL
- [x] Reject payloads missing GPS coords (client must send native GPS data)
- [x] **Haversine geofence check** — server-side distance calculation, flag `location_mismatch` if outside 100m radius
- [x] Timestamp sanity check (flag if device_timestamp vs server_timestamp diverges)
- [x] Photo hash on upload (SHA-256) + DB lookup for exact-duplicate reuse detection

## Phase 4: Scheduling / Overdue Logic
- [ ] Read-time computation: `days_since_last_clearance = now() - last_clearance_timestamp`
- [ ] No cron — compute on dashboard GET request
- [ ] Configurable overdue threshold (default 10 days) for red-flagging

## Phase 5: Agency Dashboard API
- [ ] `GET /dashboard/sites` — all sites, sorted by days-since-clearance descending
- [ ] Response includes red-flag boolean per site
- [ ] Agency-only access (read-only, can't submit check-ins)

## Phase 6: Reporter & Enhancements (Nice-to-have, post-MVP)
- [ ] Reporter "site full" endpoint (single-tap, tied to one site)
- [ ] Rate limit: one report per site per 12h window (timestamp check)
- [ ] Before/after pairing endpoint for dashboard side-by-side view
- [ ] Site history/timeline endpoint (`GET /sites/{id}/history`)

## Cross-cutting & Demo Setup
- [ ] Request logging middleware — every check-in submission logged for audit trail
- [ ] Seed 5–6 real dump point coordinates + 2 sites pre-flagged overdue for demo