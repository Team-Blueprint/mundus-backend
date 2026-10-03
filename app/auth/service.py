import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import status
from app.auth.models import User, PasswordResetToken
from app.auth.schemas import UserCreate, LoginRequest, Token, UserResponse
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.core.exceptions import MundusException
from app.config import settings

# ---------------------------------------------------------------------------
# In-process rate-limit store for forgot-password (resets on restart)
# ---------------------------------------------------------------------------
_rate_limit_store: dict[str, list[datetime]] = defaultdict(list)
_RATE_LIMIT_WINDOW = timedelta(minutes=15)
_RATE_LIMIT_MAX_EMAIL = 3
_RATE_LIMIT_MAX_IP = 5


def _check_rate_limit(key: str, max_requests: int) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - _RATE_LIMIT_WINDOW
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if t > window_start]
    if len(_rate_limit_store[key]) >= max_requests:
        return False
    _rate_limit_store[key].append(now)
    return True


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def generate_tokens_for_user(user: User) -> Token:
    access_token = create_access_token(subject=user.id, role=user.role.value)
    refresh_token = create_refresh_token(subject=user.id, role=user.role.value)
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


def create_user(db: Session, user_in: UserCreate) -> User:
    existing = get_user_by_email(db, user_in.email)
    if existing:
        raise MundusException(
            message=f"User with email '{user_in.email}' already exists.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    db_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def register_service(db: Session, user_in: UserCreate) -> Token:
    from app.auth.models import UserRole as _UserRole
    # Security: self-service register only creates SUPERVISOR accounts
    if user_in.role and user_in.role != _UserRole.SUPERVISOR:
        raise MundusException(
            message="Self-registration is only available for supervisor accounts.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    user_in_copy = user_in.model_copy(update={"role": _UserRole.SUPERVISOR})
    user = create_user(db, user_in_copy)
    return generate_tokens_for_user(user)


def authenticate_user(db: Session, login_data: LoginRequest) -> User:
    user = get_user_by_email(db, login_data.email)
    if not user:
        raise MundusException(
            message="Incorrect email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not verify_password(login_data.password, user.hashed_password):
        raise MundusException(
            message="Incorrect email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        raise MundusException(
            message="Inactive user account.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return user


def login_service(db: Session, login_data: LoginRequest) -> Token:
    user = authenticate_user(db, login_data)
    return generate_tokens_for_user(user)


def refresh_token_service(db: Session, refresh_token: str) -> Token:
    payload = decode_access_token(refresh_token)
    if not payload or payload.get("type") != "refresh_token":
        raise MundusException(
            message="Invalid refresh token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise MundusException(
            message="Invalid token subject.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise MundusException(
            message="User not found or inactive.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return generate_tokens_for_user(user)


# ---------------------------------------------------------------------------
# Password reset -- public, no JWT required
# ---------------------------------------------------------------------------

async def forgot_password_service(
    db: Session,
    email: str,
    client_ip: str,
    background_tasks=None,
) -> dict:
    """Always 200/{}. Sends an OTP to the user's email if active. Rate-limited per email + IP."""
    from app.notifications.brevo import send_brevo_email, format_password_reset_otp_email

    email = email.strip().lower()

    email_ok = _check_rate_limit(f"forgot:email:{email}", _RATE_LIMIT_MAX_EMAIL)
    ip_ok = _check_rate_limit(f"forgot:ip:{client_ip}", _RATE_LIMIT_MAX_IP)
    if not email_ok or not ip_ok:
        return {"message": "If an account with that email exists, an OTP has been sent to your email."}

    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return {"message": "If an account with that email exists, an OTP has been sent to your email."}

    # Invalidate outstanding unused tokens for this email
    db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({"used": True})
    db.commit()

    # Generate 6-digit OTP
    otp = f"{secrets.randbelow(900000) + 100000}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    prt = PasswordResetToken(email=email, token=otp, expires_at=expires, used=False)
    db.add(prt)
    db.commit()

    subject, html_content, text_content = format_password_reset_otp_email(otp, user.full_name)

    if background_tasks:
        background_tasks.add_task(
            send_brevo_email, user.email, user.full_name, subject, html_content, text_content
        )
    else:
        await send_brevo_email(user.email, user.full_name, subject, html_content, text_content)

    return {"message": "Password reset OTP has been sent to your email."}


def reset_password_service(db: Session, email: str, otp: str, new_password: str) -> dict:
    """Consume a single-use OTP and update the user password."""
    email = email.strip().lower()
    otp = otp.strip()
    now = datetime.now(timezone.utc)

    prt = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.token == otp,
            PasswordResetToken.used == False,  # noqa: E712
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )

    if not prt:
        raise MundusException(
            message="Invalid or expired OTP.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    expires = prt.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        prt.used = True
        db.commit()
        raise MundusException(
            message="Invalid or expired OTP.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if len(new_password) < 6:
        raise MundusException(
            message="Password must be at least 6 characters.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        raise MundusException(
            message="Invalid or expired OTP.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    user.hashed_password = get_password_hash(new_password)
    prt.used = True
    db.commit()
    return {"message": "Password has been reset successfully."}

