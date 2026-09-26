from sqlalchemy.orm import Session
from app.notifications.models import DeviceToken
from app.core.logging import logger
from app.config import settings
import httpx


async def send_push_notification(fcm_tokens: list[str], data_payload: dict, title: str = "Mundus Alert", body: str = "") -> None:
    """Send FCM web-push notification."""
    if not fcm_tokens:
        return

    if settings.FCM_SERVER_KEY and settings.FCM_SERVER_KEY.strip():
        url = "https://fcm.googleapis.com/fcm/send"
        headers = {
            "Authorization": f"key={settings.FCM_SERVER_KEY.strip()}",
            "Content-Type": "application/json",
        }
        for token in fcm_tokens:
            payload = {
                "to": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "data": data_payload,
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    logger.info(f"FCM push response: {resp.status_code}")
            except Exception as e:
                logger.error(f"Failed to send FCM push to {token[:10]}...: {e}")
    else:
        logger.info(f"[FCM PUSH (DEV)] Tokens: {len(fcm_tokens)} | Title: {title} | Data: {data_payload}")


def register_device_token(db: Session, user_id: int | None, fcm_token: str, role: str | None = None) -> DeviceToken:
    existing = db.query(DeviceToken).filter(DeviceToken.fcm_token == fcm_token).first()
    if existing:
        existing.user_id = user_id or existing.user_id
        existing.role = role or existing.role
        db.commit()
        db.refresh(existing)
        return existing

    device = DeviceToken(
        user_id=user_id,
        fcm_token=fcm_token,
        role=role,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def get_user_device_tokens(db: Session, user_id: int) -> list[str]:
    devices = db.query(DeviceToken).filter(DeviceToken.user_id == user_id).all()
    return [d.fcm_token for d in devices]
