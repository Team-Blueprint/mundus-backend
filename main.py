import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.logging import logger
from app.core.exceptions import MundusException, mundus_exception_handler, global_exception_handler
from app.auth.router import router as auth_router
from app.media.router import router as media_router
from app.dump_points.router import router as dump_points_router
from app.check_ins.router import router as check_ins_router
from app.dashboard.router import router as dashboard_router
from app.reporters.router import router as reporters_router
from app.contractors.router import router as contractors_router
from app.agency.router import router as agency_router
from app.notifications.router import router as notifications_router

from contextlib import asynccontextmanager
from app.database import engine, Base
from sqlalchemy import text


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist on startup
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            cursor = conn.connection.cursor()
            cursor.execute("PRAGMA table_info(dump_points);")
            dp_cols = [row[1] for row in cursor.fetchall()]
            if "code" not in dp_cols:
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN code VARCHAR(50);"))
                conn.commit()
            if "sector" not in dp_cols:
                conn.execute(text("ALTER TABLE dump_points ADD COLUMN sector VARCHAR(100);"))
                conn.commit()

            cursor.execute("PRAGMA table_info(reporter_flags);")
            rf_cols = [row[1] for row in cursor.fetchall()]
            if "reporter_community_id" not in rf_cols:
                conn.execute(text("ALTER TABLE reporter_flags ADD COLUMN reporter_community_id INTEGER;"))
                conn.commit()
            if "reporter_name" not in rf_cols:
                conn.execute(text("ALTER TABLE reporter_flags ADD COLUMN reporter_name VARCHAR(255);"))
                conn.commit()
    except Exception as e:
        logger.warning(f"Lifespan migration check notice: {e}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    servers=[{"url": "/"}],  # Ensures Swagger UI uses current host and port dynamically
    lifespan=lifespan,
)


# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
