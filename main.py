from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.exceptions import MundusException, mundus_exception_handler, global_exception_handler
from app.auth.router import router as auth_router
from app.media.router import router as media_router
from app.dump_points.router import router as dump_points_router
from app.check_ins.router import router as check_ins_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(MundusException, mundus_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(auth_router)
app.include_router(media_router)
app.include_router(dump_points_router)
app.include_router(check_ins_router)


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
