from sqlalchemy.orm import Session
from fastapi import status
from app.auth.models import User
from app.auth.schemas import UserCreate, LoginRequest, Token, UserResponse
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.core.exceptions import MundusException


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
    user = create_user(db, user_in)
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
