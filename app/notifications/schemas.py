from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    fcm_token: str
    role: str | None = None


class DeviceRegisterResponse(BaseModel):
    message: str
    fcm_token: str


class NotifyTestRequest(BaseModel):
    fcm_token: str | None = None
    title: str = "Mundus Test Notification"
    body: str = "This is a test notification from Mundus backend."
