from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.logging import logger
from datetime import datetime, timezone


class MundusException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, detail: str = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)


class EntityNotFoundException(MundusException):
    def __init__(self, entity_name: str, entity_id: str | int):
        super().__init__(
            message=f"{entity_name} with id '{entity_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class PermissionDeniedException(MundusException):
    def __init__(self, detail: str = "Permission denied for this action."):
        super().__init__(
            message=detail,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class GeofenceMismatchException(MundusException):
    def __init__(self, distance_meters: float, allowed_radius_meters: float):
        super().__init__(
            message=f"Location mismatch: Check-in distance ({distance_meters:.1f}m) exceeds allowed radius ({allowed_radius_meters:.1f}m).",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="location_mismatch"
        )


class RateLimitException(MundusException):
    def __init__(self, detail: str = "Already reported. Site is locked for 12 hours.", retry_in_seconds: int = 43200):
        self.retry_in_seconds = int(retry_in_seconds)
        super().__init__(
            message=detail,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


async def rate_limit_exception_handler(request: Request, exc: RateLimitException):
    user_id = getattr(request.state, "user_id", None)
    site_id = getattr(request.state, "site_id", None)

    logger.warning(
        f"Rate limit triggered: {exc.message} on {request.method} {request.url.path}",
        extra={"user_id": user_id, "site_id": site_id}
    )

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": exc.message,
            "retry_in_seconds": exc.retry_in_seconds,
        },
        headers={"Retry-After": str(exc.retry_in_seconds)},
    )


async def mundus_exception_handler(request: Request, exc: MundusException):
    user_id = getattr(request.state, "user_id", None)
    site_id = getattr(request.state, "site_id", None)

    logger.warning(
        f"Handled exception: {exc.message} on {request.method} {request.url.path}",
        extra={"user_id": user_id, "site_id": site_id}
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "detail": exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        }
    )


async def global_exception_handler(request: Request, exc: Exception):
    user_id = getattr(request.state, "user_id", None)
    site_id = getattr(request.state, "site_id", None)

    logger.error(
        f"Unhandled server error on {request.method} {request.url.path}",
        exc_info=exc,
        extra={"user_id": user_id, "site_id": site_id}
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected internal server error occurred.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        }
    )

