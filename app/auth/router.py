from fastapi import APIRouter, Depends, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    Token,
    UserCreate,
    UserResponse,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse,
)
from app.auth.deps import get_current_user
import app.auth.service as auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with email and password and return access & refresh JWT tokens."""
    return auth_service.login_service(db, login_data)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user and return access & refresh JWT tokens."""
    return auth_service.register_service(db, user_in)


@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK)
def refresh_token(refresh_data: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh expired access token using a valid refresh token."""
    return auth_service.refresh_token_service(db, refresh_data.refresh_token)


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user details."""
    return current_user


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):

    client_ip = request.client.host if request.client else "unknown"
    return await auth_service.forgot_password_service(
        db, payload.email, client_ip, background_tasks=background_tasks
    )


@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):

    return auth_service.reset_password_service(
        db=db,
        email=payload.email,
        otp=payload.otp,
        new_password=payload.new_password,
    )


