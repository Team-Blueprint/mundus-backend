#!/usr/bin/env bash
# Creates one GitHub issue per backend phase for Mundus, with the tasks
# as a checklist inside the issue body.
#
# Prereqs:
#   1. Install GitHub CLI: https://cli.github.com
#   2. Auth once:  gh auth login
#   3. Run this from inside your cloned Mundus repo (or add: gh issue create -R owner/repo ...)

set -e

gh issue create \
  --title "Phase 0: Foundation" \
  --label "backend,mvp" \
  --body "- [ ] Project scaffold (FastAPI app, routers, pydantic-settings config, .env)
- [ ] PostgreSQL setup + SQLAlchemy (or SQLModel) + Alembic migrations
- [ ] Object storage bucket (S3-compatible) for photos
- [ ] /health endpoint returning 200
- [ ] Global exception handler + structured logging (site ID, user ID, timestamp)"

gh issue create \
  --title "Phase 1: Auth & Roles" \
  --label "backend,mvp,auth" \
  --body "- [ ] User model with role enum: supervisor, agency, reporter
- [ ] JWT auth (fastapi-users or python-jose + passlib)
- [ ] /auth/login, /auth/me endpoints
- [ ] Role-based dependency guards (Depends(require_role(...)))
- [ ] Seed script for mock contractor/supervisor/agency accounts"

gh issue create \
  --title "Phase 2: Dump Point Registry" \
  --label "backend,mvp" \
  --body "- [ ] DumpPoint model: name, lat, lng, assigned_contractor_id, assigned_supervisor_id, interval_days, last_clearance_timestamp
- [ ] CRUD endpoints: create, list, assign
- [ ] Supervisor scoping — supervisors only see their assigned sites"

gh issue create \
  --title "Phase 3: Check-In Flow" \
  --label "backend,mvp,anti-fraud" \
  --body "- [ ] CheckIn model: site_id, supervisor_id, type (before/after), photo_url, lat, lng, device_timestamp, server_timestamp, status
- [ ] Photo upload endpoint (multipart) -> object storage -> store URL
- [ ] Reject payloads missing GPS coords
- [ ] Haversine geofence check (server-side, configurable radius default 100m)
- [ ] Timestamp sanity check (flag, don't block)
- [ ] Photo hash (SHA-256) + DB lookup for exact-duplicate reuse detection"

gh issue create \
  --title "Phase 4: Scheduling / Overdue Logic" \
  --label "backend,mvp" \
  --body "- [ ] Read-time computation: days_since_last_clearance = now() - last_clearance_timestamp
- [ ] No cron — compute on dashboard GET request
- [ ] Configurable overdue threshold (default 10 days)"

gh issue create \
  --title "Phase 5: Agency Dashboard API" \
  --label "backend,mvp" \
  --body "- [ ] GET /dashboard/sites — all sites, sorted by days-since-clearance descending
- [ ] Response includes red-flag boolean per site
- [ ] Agency-only access (read-only, can't submit check-ins)"

gh issue create \
  --title "Phase 6: Nice-to-have (post-MVP)" \
  --label "backend,nice-to-have" \
  --body "- [ ] Reporter 'site full' endpoint
- [ ] Rate limit: one report per site per 12h window
- [ ] Before/after pairing endpoint for dashboard
- [ ] Site history/timeline endpoint (GET /sites/{id}/history)
- [ ] Push notifications on reporter flag (FCM or Supabase realtime)"

gh issue create \
  --title "Cross-cutting" \
  --label "backend,mvp" \
  --body "- [ ] Request logging middleware — every check-in submission (success/fail) logged
- [ ] Deploy as its own Pxxl service, independent from frontend
- [ ] Seed 5–6 real dump point coordinates + 2 sites pre-flagged overdue for demo"

echo "Done. Check the Issues tab on your repo."