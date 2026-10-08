import secrets
from sqlalchemy.orm import Session
from fastapi import status
from app.agency.models import AgencyAccessRequest
from app.agency.schemas import AgencyAccessRequestCreate, AgencyAccessRequestResponse, StaffInviteRequest, StaffResponse
from app.auth.models import User, UserRole
from app.core.security import get_password_hash
from app.core.exceptions import MundusException, EntityNotFoundException
from app.config import settings


def create_access_request_service(db: Session, data: AgencyAccessRequestCreate) -> AgencyAccessRequestResponse:
    req = AgencyAccessRequest(
        full_name=data.full_name.strip(),
        email=data.email.strip().lower(),
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return AgencyAccessRequestResponse.model_validate(req)


def list_access_requests_service(db: Session) -> list[AgencyAccessRequestResponse]:
    requests = db.query(AgencyAccessRequest).order_by(AgencyAccessRequest.created_at.desc()).all()
    return [AgencyAccessRequestResponse.model_validate(r) for r in requests]


def list_staff_service(db: Session) -> list[StaffResponse]:
    """Return all agency staff users ordered newest first."""
    staff = (
        db.query(User)
        .filter(User.is_agency_staff == True)  # noqa: E712
        .order_by(User.created_at.desc())
        .all()
    )
    return [_user_to_staff_response(u) for u in staff]


async def invite_staff_service(
    db: Session,
    data: StaffInviteRequest,
    invited_by: User,
    background_tasks=None,
) -> StaffResponse:
    """
    Create an agency staff account and email login credentials.
    The temporary password is ONLY in the email — never returned in the response.
    """
    from app.notifications.brevo import send_brevo_email, format_staff_invite_email

    email = data.email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise MundusException(
            message=f"An account with email '{email}' already exists.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    temp_password = secrets.token_urlsafe(9)  # ~12 printable chars
    new_staff = User(
        email=email,
        hashed_password=get_password_hash(temp_password),
        full_name=data.full_name.strip(),
        role=UserRole.AGENCY,
        is_active=True,
        is_agency_staff=True,
        invited_by_id=invited_by.id,
    )
    db.add(new_staff)
    db.commit()
    db.refresh(new_staff)

    login_url = f"{settings.FRONTEND_ORIGIN}/contractor/sign-in"
    subject, html_content, text_content = format_staff_invite_email(
        full_name=data.full_name.strip(),
        email=email,
        temp_password=temp_password,
        login_url=login_url,
    )

    if background_tasks:
        background_tasks.add_task(
            send_brevo_email, email, data.full_name, subject, html_content, text_content
        )
    else:
        await send_brevo_email(email, data.full_name, subject, html_content, text_content)

    return _user_to_staff_response(new_staff)


def deactivate_staff_service(db: Session, staff_id: int) -> dict:
    """Deactivate a staff member — prevents login but preserves audit history."""
    staff = db.query(User).filter(User.id == staff_id, User.is_agency_staff == True).first()  # noqa: E712
    if not staff:
        raise EntityNotFoundException("AgencyStaff", staff_id)
    staff.is_active = False
    db.commit()
    return {"message": f"Staff member '{staff.full_name or staff.email}' has been deactivated."}


def reactivate_staff_service(db: Session, staff_id: int) -> dict:
    """Reactivate a previously deactivated staff member."""
    staff = db.query(User).filter(User.id == staff_id, User.is_agency_staff == True).first()  # noqa: E712
    if not staff:
        raise EntityNotFoundException("AgencyStaff", staff_id)
    staff.is_active = True
    db.commit()
    return {"message": f"Staff member '{staff.full_name or staff.email}' has been reactivated."}


def _user_to_staff_response(user: User) -> StaffResponse:
    return StaffResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=user.is_active,
        is_agency_staff=user.is_agency_staff,
        created_at=user.created_at,
    )
