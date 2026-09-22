from typing import Callable, Sequence
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.models import User, UserRole
from app.auth.service import get_user_by_id
from app.core.security import decode_access_token
from app.core.exceptions import MundusException, PermissionDeniedException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
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

