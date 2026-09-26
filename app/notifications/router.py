from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user_optional
from app.auth.models import User
from app.notifications.schemas import DeviceRegisterRequest, DeviceRegisterResponse, NotifyTestRequest
import app.notifications.service as notif_service

router = APIRouter(tags=["Notifications & Devices"])


@router.post("/devices/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_200_OK)
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Register client FCM device token for web-push notifications."""
    user_id = current_user.id if current_user else None
    notif_service.register_device_token(
        db=db,
        user_id=user_id,
        fcm_token=payload.fcm_token,
        role=payload.role or (current_user.role.value if current_user else None),
    )
    return DeviceRegisterResponse(
        message="Device registered successfully",
        fcm_token=payload.fcm_token,
    )


@router.post("/notify/test", status_code=status.HTTP_200_OK)
async def test_notification(
    payload: NotifyTestRequest,
    background_tasks: BackgroundTasks,
):
    """Debug endpoint to test sending push notifications."""
    tokens = [payload.fcm_token] if payload.fcm_token else []
    background_tasks.add_task(
        notif_service.send_push_notification,
        tokens,
        {"type": "test_ping"},
        payload.title,
        payload.body,
    )
    return {"message": "Test notification queued", "recipient_count": len(tokens)}
