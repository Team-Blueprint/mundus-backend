import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.logging import logger
import uuid
from app.core.exceptions import (
    MundusException,
    mundus_exception_handler,
    global_exception_handler,
    RateLimitException,
    rate_limit_exception_handler,
)
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.auth.router import router as auth_router
from app.media.router import router as media_router
from app.dump_points.router import router as dump_points_router
from app.check_ins.router import router as check_ins_router
from app.dashboard.router import router as dashboard_router
from app.reporters.router import router as reporters_router
from app.contractors.router import router as contractors_router
from app.agency.router import router as agency_router
from app.notifications.router import router as notifications_router
from app.payouts.router import router as payouts_router

from contextlib import asynccontextmanager
from app.database import engine, Base
from sqlalchemy import text


def patch_sqlite_carried_over_db(conn):
    cursor = conn.connection.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF;")

    # 1. Migrate users: convert supervisor -> contractor
    cursor.execute("PRAGMA table_info(users);")
    u_cols = [c[1] for c in cursor.fetchall()]
    if "is_agency_staff" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_agency_staff BOOLEAN NOT NULL DEFAULT 0;")
    if "invited_by_id" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN invited_by_id INTEGER;")
    cursor.execute("UPDATE users SET role = 'contractor' WHERE LOWER(role) = 'supervisor';")

    # 2. Check contractors table
    cursor.execute("PRAGMA table_info(contractors);")
    c_cols_info = cursor.fetchall()
    c_cols = {c[1]: c[2] for c in c_cols_info}

    # 3. Check dump_points table
    cursor.execute("PRAGMA table_info(dump_points);")
    dp_cols_info = cursor.fetchall()
    dp_cols = {c[1]: c[2] for c in dp_cols_info}

    contractor_map = {}
    site_id_map = {}

    needs_contractors_rebuild = c_cols.get("id", "").upper() == "INTEGER" or "supervisor_email" in c_cols
    needs_dp_rebuild = dp_cols.get("id", "").upper() == "INTEGER"

    if needs_contractors_rebuild:
        cursor.execute("SELECT * FROM contractors;")
        old_contractors = cursor.fetchall()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contractors_new (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                user_id INTEGER,
                monthly_stipend FLOAT NOT NULL DEFAULT 0.0,
                bank_name VARCHAR(100),
                bank_account_number VARCHAR(20),
                bank_account_name VARCHAR(255),
                bank_code VARCHAR(10),
                payment_provider_recipient_id VARCHAR(100),
                payment_provider_metadata JSON DEFAULT '{}',
                created_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id)
            );
        """)

        default_contractor_ids = {
            "CleanCity Services": "CTR-AK-001",
            "GreenPath Ltd": "CTR-AK-002",
            "EcoWaste Management": "CTR-AK-003",
            "Emmanuel Udo": "CTR-AK-004",
        }

        col_keys = [c[1] for c in c_cols_info]
        for row_tuple in old_contractors:
            row = dict(zip(col_keys, row_tuple))
            old_id = row.get("id")
            name = row.get("name")
            email = row.get("email") or row.get("supervisor_email") or f"contractor_{old_id}@mundus.org"
            user_id = row.get("user_id") if row.get("user_id") is not None else row.get("supervisor_user_id")

            new_id = default_contractor_ids.get(name, str(old_id) if not str(old_id).isdigit() else f"CTR-AK-{str(old_id).zfill(3)}")
            contractor_map[str(old_id)] = new_id
            if name:
                contractor_map[name] = new_id

            monthly_stipend = row.get("monthly_stipend") if row.get("monthly_stipend") is not None else 0.0
            bank_name = row.get("bank_name")
            bank_acc = row.get("bank_account_number")
            bank_name_holder = row.get("bank_account_name")
            bank_code = row.get("bank_code")
            recipient_id = row.get("payment_provider_recipient_id")
            metadata = row.get("payment_provider_metadata") or "{}"
            created_at = row.get("created_at")

            cursor.execute("""
                INSERT OR REPLACE INTO contractors_new (
                    id, name, email, user_id, monthly_stipend, bank_name,
                    bank_account_number, bank_account_name, bank_code,
                    payment_provider_recipient_id, payment_provider_metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, name, email, user_id, monthly_stipend, bank_name, bank_acc, bank_name_holder, bank_code, recipient_id, metadata, created_at))

        cursor.execute("DROP TABLE contractors;")
        cursor.execute("ALTER TABLE contractors_new RENAME TO contractors;")

    if needs_dp_rebuild:
        cursor.execute("SELECT * FROM dump_points;")
        old_dps = cursor.fetchall()
        dp_col_keys = [c[1] for c in dp_cols_info]

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dump_points_new (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                code VARCHAR(50),
                sector VARCHAR(100),
                assigned_contractor_id VARCHAR(36),
                interval_days INTEGER NOT NULL DEFAULT 7,
                last_clearance_timestamp DATETIME,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(assigned_contractor_id) REFERENCES contractors (id)
            );
        """)

        for row_tuple in old_dps:
            row = dict(zip(dp_col_keys, row_tuple))
            old_id = row.get("id")
            new_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"mundus_dp_{old_id}").hex
            site_id_map[str(old_id)] = new_id

            raw_cid = row.get("assigned_contractor_id")
            new_cid = None
            if raw_cid:
                if raw_cid in contractor_map:
                    new_cid = contractor_map[raw_cid]
                elif str(raw_cid) in contractor_map:
                    new_cid = contractor_map[str(raw_cid)]
                elif "CleanCity" in str(raw_cid) or "Emmanuel" in str(raw_cid):
                    new_cid = contractor_map.get("CleanCity Services", "CTR-AK-001")
                elif "GreenPath" in str(raw_cid):
                    new_cid = contractor_map.get("GreenPath Ltd", "CTR-AK-002")
                elif "EcoWaste" in str(raw_cid) or "CTR-AK-003" in str(raw_cid):
                    new_cid = contractor_map.get("EcoWaste Management", "CTR-AK-003")
                else:
                    new_cid = str(raw_cid)

            cursor.execute("""
                INSERT OR REPLACE INTO dump_points_new (
                    id, name, latitude, longitude, code, sector,
                    assigned_contractor_id, interval_days, last_clearance_timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_id, row.get("name"), row.get("latitude"), row.get("longitude"),
                row.get("code"), row.get("sector"),
                new_cid,
                row.get("interval_days", 7),
                row.get("last_clearance_timestamp"),
                row.get("created_at"),
            ))

        cursor.execute("DROP TABLE dump_points;")
        cursor.execute("ALTER TABLE dump_points_new RENAME TO dump_points;")

    # Fallback first valid site id for dangling FKs
    cursor.execute("SELECT id FROM dump_points LIMIT 1;")
    first_site_row = cursor.fetchone()
    first_site_id = first_site_row[0] if first_site_row else str(uuid.uuid4().hex)

    # 4. Migrate check_ins
    cursor.execute("PRAGMA table_info(check_ins);")
    ci_cols_info = cursor.fetchall()
    ci_cols = {c[1]: c[2] for c in ci_cols_info}
    needs_ci_rebuild = ci_cols.get("site_id", "").upper() == "INTEGER" or "supervisor_id" in ci_cols or "user_id" not in ci_cols

    if needs_ci_rebuild:
        cursor.execute("SELECT * FROM check_ins;")
        old_cis = cursor.fetchall()
        ci_col_keys = [c[1] for c in ci_cols_info]

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS check_ins_new (
                id INTEGER PRIMARY KEY,
                site_id VARCHAR(36) NOT NULL,
                user_id INTEGER NOT NULL,
                type VARCHAR(6) NOT NULL,
                photo_url VARCHAR(500) NOT NULL,
                photo_hash VARCHAR(64) NOT NULL,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                distance_from_site_meters FLOAT NOT NULL,
                device_timestamp DATETIME NOT NULL,
                server_timestamp DATETIME NOT NULL,
                status VARCHAR(17) NOT NULL,
                flags JSON NOT NULL,
                FOREIGN KEY(site_id) REFERENCES dump_points (id),
                FOREIGN KEY(user_id) REFERENCES users (id)
            );
        """)

        for row_tuple in old_cis:
            row = dict(zip(ci_col_keys, row_tuple))
            old_site = str(row.get("site_id"))
            new_site = site_id_map.get(old_site, old_site)
            cursor.execute("SELECT 1 FROM dump_points WHERE id = ?;", (new_site,))
            if not cursor.fetchone():
                new_site = first_site_id

            user_id = row.get("user_id") if row.get("user_id") is not None else row.get("supervisor_id")

            cursor.execute("""
                INSERT OR REPLACE INTO check_ins_new (
                    id, site_id, user_id, type, photo_url, photo_hash,
                    latitude, longitude, distance_from_site_meters,
                    device_timestamp, server_timestamp, status, flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("id"), new_site, user_id, row.get("type"), row.get("photo_url"), row.get("photo_hash"),
                row.get("latitude"), row.get("longitude"), row.get("distance_from_site_meters"),
                row.get("device_timestamp"), row.get("server_timestamp"), row.get("status"), row.get("flags"),
            ))

        cursor.execute("DROP TABLE check_ins;")
        cursor.execute("ALTER TABLE check_ins_new RENAME TO check_ins;")

    # 5. Migrate reporters
    cursor.execute("PRAGMA table_info(reporters);")
    rep_cols_info = cursor.fetchall()
    rep_cols = {c[1]: c[2] for c in rep_cols_info}
    needs_rep_rebuild = rep_cols.get("site_id", "").upper() == "INTEGER" or rep_cols.get("contractor_id", "").upper() == "INTEGER"

    if needs_rep_rebuild:
        cursor.execute("SELECT * FROM reporters;")
        old_reps = cursor.fetchall()
        rep_col_keys = [c[1] for c in rep_cols_info]

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reporters_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                site_id VARCHAR(36) NOT NULL,
                contractor_id VARCHAR(36),
                status VARCHAR(8) NOT NULL,
                token VARCHAR(64),
                rejection_reason VARCHAR(500),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(site_id) REFERENCES dump_points (id)
            );
        """)

        for row_tuple in old_reps:
            row = dict(zip(rep_col_keys, row_tuple))
            old_site = str(row.get("site_id"))
            new_site = site_id_map.get(old_site, old_site)
            cursor.execute("SELECT 1 FROM dump_points WHERE id = ?;", (new_site,))
            if not cursor.fetchone():
                new_site = first_site_id

            old_cid = str(row.get("contractor_id")) if row.get("contractor_id") is not None else None
            new_cid = contractor_map.get(old_cid, old_cid)

            cursor.execute("""
                INSERT OR REPLACE INTO reporters_new (
                    id, name, phone, site_id, contractor_id, status, token, rejection_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("id"), row.get("name"), row.get("phone"), new_site, new_cid, row.get("status"),
                row.get("token"), row.get("rejection_reason"), row.get("created_at"), row.get("updated_at"),
            ))

        cursor.execute("DROP TABLE reporters;")
        cursor.execute("ALTER TABLE reporters_new RENAME TO reporters;")

    # 6. Migrate reporter_flags
    cursor.execute("PRAGMA table_info(reporter_flags);")
    rf_cols_info = cursor.fetchall()
    rf_cols = {c[1]: c[2] for c in rf_cols_info}
    needs_rf_rebuild = rf_cols.get("site_id", "").upper() == "INTEGER"

    if needs_rf_rebuild:
        cursor.execute("SELECT * FROM reporter_flags;")
        old_rfs = cursor.fetchall()
        rf_col_keys = [c[1] for c in rf_cols_info]

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reporter_flags_new (
                id INTEGER PRIMARY KEY,
                site_id VARCHAR(36) NOT NULL,
                reporter_id INTEGER NOT NULL,
                reporter_community_id INTEGER,
                reporter_name VARCHAR(255),
                timestamp DATETIME NOT NULL,
                note VARCHAR(500),
                photo_url VARCHAR(500),
                FOREIGN KEY(site_id) REFERENCES dump_points (id),
                FOREIGN KEY(reporter_id) REFERENCES users (id)
            );
        """)

        for row_tuple in old_rfs:
            row = dict(zip(rf_col_keys, row_tuple))
            old_site = str(row.get("site_id"))
            new_site = site_id_map.get(old_site, old_site)
            cursor.execute("SELECT 1 FROM dump_points WHERE id = ?;", (new_site,))
            if not cursor.fetchone():
                new_site = first_site_id

            cursor.execute("""
                INSERT OR REPLACE INTO reporter_flags_new (
                    id, site_id, reporter_id, reporter_community_id, reporter_name, timestamp, note, photo_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("id"), new_site, row.get("reporter_id"),
                row.get("reporter_community_id"), row.get("reporter_name"),
                row.get("timestamp"), row.get("note"), row.get("photo_url"),
            ))

        cursor.execute("DROP TABLE reporter_flags;")
        cursor.execute("ALTER TABLE reporter_flags_new RENAME TO reporter_flags;")

    # 7. Migrate contractor_alerts
    cursor.execute("PRAGMA table_info(contractor_alerts);")
    ca_cols_info = cursor.fetchall()
    ca_cols = {c[1]: c[2] for c in ca_cols_info}
    needs_ca_rebuild = ca_cols.get("site_id", "").upper() == "INTEGER" or "supervisor_id" in ca_cols

    if needs_ca_rebuild:
        cursor.execute("SELECT * FROM contractor_alerts;")
        old_cas = cursor.fetchall()
        ca_col_keys = [c[1] for c in ca_cols_info]

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contractor_alerts_new (
                id INTEGER PRIMARY KEY,
                site_id VARCHAR(36) NOT NULL,
                contractor_id VARCHAR(36),
                message VARCHAR(500) NOT NULL,
                is_seen BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(site_id) REFERENCES dump_points (id),
                FOREIGN KEY(contractor_id) REFERENCES contractors (id)
            );
        """)

        for row_tuple in old_cas:
            row = dict(zip(ca_col_keys, row_tuple))
            old_site = str(row.get("site_id"))
            new_site = site_id_map.get(old_site, old_site)
            cursor.execute("SELECT 1 FROM dump_points WHERE id = ?;", (new_site,))
            if not cursor.fetchone():
                new_site = first_site_id

            old_cid = str(row.get("contractor_id")) if row.get("contractor_id") is not None else str(row.get("supervisor_id")) if row.get("supervisor_id") is not None else None
            new_cid = contractor_map.get(old_cid, old_cid)

            cursor.execute("""
                INSERT OR REPLACE INTO contractor_alerts_new (
                    id, site_id, contractor_id, message, is_seen, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row.get("id"), new_site, new_cid, row.get("message"), row.get("is_seen", 0), row.get("created_at"),
            ))

        cursor.execute("DROP TABLE contractor_alerts;")
        cursor.execute("ALTER TABLE contractor_alerts_new RENAME TO contractor_alerts;")

    # Ensure individual columns exist if not rebuilt
    cursor.execute("PRAGMA table_info(dump_points);")
    dp_cols_final = [r[1] for r in cursor.fetchall()]
    if "code" not in dp_cols_final:
        cursor.execute("ALTER TABLE dump_points ADD COLUMN code VARCHAR(50);")
    if "sector" not in dp_cols_final:
        cursor.execute("ALTER TABLE dump_points ADD COLUMN sector VARCHAR(100);")

    cursor.execute("PRAGMA table_info(reporter_flags);")
    rf_cols_final = [r[1] for r in cursor.fetchall()]
    if "reporter_community_id" not in rf_cols_final:
        cursor.execute("ALTER TABLE reporter_flags ADD COLUMN reporter_community_id INTEGER;")
    if "reporter_name" not in rf_cols_final:
        cursor.execute("ALTER TABLE reporter_flags ADD COLUMN reporter_name VARCHAR(255);")
    if "photo_url" not in rf_cols_final:
        cursor.execute("ALTER TABLE reporter_flags ADD COLUMN photo_url VARCHAR(500);")

    cursor.execute("PRAGMA table_info(contractors);")
    c_cols_final = [r[1] for r in cursor.fetchall()]
    if "monthly_stipend" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN monthly_stipend FLOAT NOT NULL DEFAULT 0.0;")
    if "bank_name" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN bank_name VARCHAR(100);")
    if "bank_account_number" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN bank_account_number VARCHAR(20);")
    if "bank_account_name" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN bank_account_name VARCHAR(255);")
    if "bank_code" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN bank_code VARCHAR(10);")
    if "payment_provider_recipient_id" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN payment_provider_recipient_id VARCHAR(100);")
    if "payment_provider_metadata" not in c_cols_final:
        cursor.execute("ALTER TABLE contractors ADD COLUMN payment_provider_metadata JSON DEFAULT '{}';")

    cursor.execute("PRAGMA foreign_keys=ON;")
    conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist on startup
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        try:
            with engine.connect() as conn:
                patch_sqlite_carried_over_db(conn)
        except Exception as e:
            logger.warning(f"SQLite lifespan migration check notice: {e}")
    elif engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text("UPDATE users SET role = 'CONTRACTOR' WHERE role::text ILIKE 'supervisor';"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS monthly_stipend DOUBLE PRECISION DEFAULT 0.0;"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS bank_name VARCHAR(100);"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(20);"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS bank_account_name VARCHAR(255);"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS bank_code VARCHAR(10);"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS payment_provider_recipient_id VARCHAR(100);"))
                conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS payment_provider_metadata JSONB DEFAULT '{}'::jsonb;"))
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN IF NOT EXISTS code VARCHAR(50);"))
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN IF NOT EXISTS sector VARCHAR(100);"))
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN IF NOT EXISTS interval_days INTEGER DEFAULT 7;"))
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN IF NOT EXISTS last_clearance_timestamp TIMESTAMP WITH TIME ZONE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_agency_staff BOOLEAN DEFAULT FALSE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by_id INTEGER;"))
                conn.execute(text("ALTER TABLE reporter_flags ADD COLUMN IF NOT EXISTS reporter_community_id INTEGER;"))
                conn.execute(text("ALTER TABLE reporter_flags ADD COLUMN IF NOT EXISTS reporter_name VARCHAR(255);"))
                conn.execute(text("ALTER TABLE reporter_flags ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500);"))
                conn.execute(text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='contractors' AND column_name='supervisor_email') THEN UPDATE contractors SET email = supervisor_email WHERE email IS NULL OR email = ''; END IF; END $$;"))
                conn.execute(text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='contractors' AND column_name='supervisor_user_id') THEN UPDATE contractors SET user_id = supervisor_user_id WHERE user_id IS NULL; END IF; END $$;"))
                conn.execute(text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='check_ins' AND column_name='supervisor_id') THEN UPDATE check_ins SET user_id = supervisor_id WHERE user_id IS NULL; END IF; END $$;"))
                conn.commit()
        except Exception as e:
            logger.warning(f"PostgreSQL lifespan migration check notice: {e}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    servers=[{"url": "/"}],  # Ensures Swagger UI uses current host and port dynamically
    lifespan=lifespan,
)


# CORS middleware configuration - allow all origins, methods, and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def audit_request_logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time_ms = (time.time() - start_time) * 1000.0

    user_id = getattr(request.state, "user_id", None)
    logger.info(
        f"AUDIT {request.method} {request.url.path} - Status: {response.status_code} - Latency: {process_time_ms:.1f}ms",
        extra={"user_id": user_id}
    )
    return response


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 429:
        detail_msg = exc.detail
        retry_secs = 43200
        if isinstance(exc.detail, dict):
            detail_msg = exc.detail.get("detail", "Already reported")
            retry_val = exc.detail.get("retry_in_seconds", exc.detail.get("retry_in", 43200))
            try:
                retry_secs = int(retry_val)
            except Exception:
                retry_secs = 43200
        return JSONResponse(
            status_code=429,
            content={"detail": str(detail_msg), "retry_in_seconds": retry_secs},
            headers={"Retry-After": str(retry_secs)},
        )
    return await default_http_exception_handler(request, exc)


app.add_exception_handler(RateLimitException, rate_limit_exception_handler)
app.add_exception_handler(MundusException, mundus_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Include module routers directly without v1 prefix
app.include_router(auth_router)
app.include_router(media_router)
app.include_router(dump_points_router)
app.include_router(check_ins_router)
app.include_router(dashboard_router)
app.include_router(reporters_router)
app.include_router(contractors_router)
app.include_router(agency_router)
app.include_router(notifications_router)
app.include_router(payouts_router)



@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Health check endpoint for WatchUp / Pxxl monitoring",
)
def health_check():
    """Health check route returning HTTP 200 OK for WatchUp and Pxxl deployment uptime monitoring."""
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
