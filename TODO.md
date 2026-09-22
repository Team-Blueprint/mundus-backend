# Mundus Backend — FastAPI Technical Todo

## Phase 0: Foundation
- [ ] Project scaffold (FastAPI app, routers, `pydantic-settings` config, `.env`)
- [x] Project scaffold (FastAPI app, routers, `pydantic-settings` config, `.env`)
- [ ] PostgreSQL setup + SQLAlchemy (or SQLModel) + Alembic migrations
- [ ] Object storage bucket (S3-compatible) for photos — never store binaries in Postgres
- [ ] `/health` endpoint returning 200 (do this first — unblocks WatchUp integration)
- [ ] Media storage (Cloudinary) for photos — never store binaries in Postgres
- [x] `/health` endpoint returning 200 (do this first — unblocks WatchUp integration)
- [ ] Global exception handler + structured logging (site ID, user ID, timestamp on every error)

## Phase 1: Auth & Roles
- [ ] User model with `role` enum: `supervisor`, `agency`, `reporter`
- [ ] JWT auth (`fastapi-users` or hand-rolled with `python-jose` + `passlib`)
- [ ] `/auth/login`, `/auth/me` endpoints
- [ ] Role-based dependency guards (`Depends(require_role("supervisor"))` etc.)
- [ ] Seed script for mock contractor/supervisor/agency accounts (demo data)

## Phase 2: Dump Point Registry (admin)
- [ ] `DumpPoint` model: name, lat, lng, assigned_contractor_id, assigned_supervisor_id, interval_days, last_clearance_timestamp
- [ ] CRUD endpoints: create, list, assign
- [ ] Supervisor scoping — supervisors only see their assigned sites

## Phase 3: Check-In Flow
- [ ] `CheckIn` model: site_id, supervisor_id, type (`before`/`after`), photo_url, lat, lng, device_timestamp, server_timestamp, status
- [ ] Photo upload endpoint (multipart) → push to object storage → store URL
- [ ] Reject payloads missing GPS coords (client must send `navigator.geolocation` / native GPS data — no manual entry)
- [ ] **Haversine geofence check** — server-side, compare submitted lat/lng to registered dump point coords; flag `location_mismatch` if outside configurable radius (default 100m)
- [ ] Timestamp sanity check (flag, don't block, if device_timestamp vs server_timestamp diverges significantly)
- [ ] Photo hash on upload (SHA-256) + DB lookup for exact-duplicate reuse detection

## Phase 4: Scheduling / Overdue Logic
- [ ] Read-time computation: `days_since_last_clearance = now() - last_clearance_timestamp`
- [ ] No cron — compute on dashboard GET request
- [ ] Configurable overdue threshold (default 10 days) for red-flagging

## Phase 5: Agency Dashboard API
- [ ] `GET /dashboard/sites` — all sites, sorted by days-since-clearance descending
- [ ] Response includes red-flag boolean per site
- [ ] Agency-only access (read-only, can't submit check-ins)

## Phase 6 (Nice-to-have, post-MVP)
- [ ] Reporter "site full" endpoint (single-tap, tied to one site)
- [ ] Rate limit: one report per site per 12h window (timestamp check)
- [ ] Before/after pairing endpoint for dashboard side-by-side view
- [ ] Site history/timeline endpoint (`GET /sites/{id}/history`)
- [ ] Push notifications on reporter flag (FCM or Supabase realtime — budget 1–2 days max)

## Cross-cutting
- [ ] Request logging middleware — every check-in submission (success/fail) logged for audit trail
- [ ] Deploy as its own Pxxl service, independent from frontend
- [ ] Seed 5–6 real dump point coordinates + 2 sites pre-flagged overdue for demo

Want this broken into a sprint-day schedule for your 18 days, or turned into GitHub issues?