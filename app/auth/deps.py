from typing import Callable, Sequence
from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.models import User, UserRole
from app.auth.service import get_user_by_id
from app.core.security import decode_access_token
from app.core.exceptions import MundusException, PermissionDeniedException

http_bearer = HTTPBearer(scheme_name="HttpJwtAuth", auto_error=True)
http_bearer_optional = HTTPBearer(scheme_name="HttpJwtAuthOptional", auto_error=False)


def get_current_user(auth: HTTPAuthorizationCredentials = Depends(http_bearer), db: Session = Depends(get_db),) -> User:
    token = auth.credentials
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise MundusException(
            message="Could not validate credentials.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise MundusException(
            message="Invalid token subject.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user = get_user_by_id(db, user_id=user_id)
    if not user or not user.is_active:
        raise MundusException(
            message="User not found or inactive.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return user


def get_current_user_optional(
    auth: HTTPAuthorizationCredentials | None = Depends(http_bearer_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not auth or not auth.credentials:
        return None
    try:
        payload = decode_access_token(auth.credentials)
        if not payload or not payload.get("sub"):
            return None
        user_id = int(payload["sub"])
        user = get_user_by_id(db, user_id=user_id)
        return user if user and user.is_active else None
    except Exception:
        return None



def require_role(allowed_roles: Sequence[UserRole | str]) -> Callable:
    allowed_role_strings = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role_str = current_user.role.value if isinstance(current_user.role, UserRole) else str(current_user.role)
        if user_role_str not in allowed_role_strings:
            raise PermissionDeniedException(
                detail=f"Role '{user_role_str}' does not have permission for this resource. Required: {allowed_role_strings}"
            )
        return current_user

    return role_checker
