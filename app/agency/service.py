from sqlalchemy.orm import Session
from app.agency.models import AgencyAccessRequest
from app.agency.schemas import AgencyAccessRequestCreate, AgencyAccessRequestResponse


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
