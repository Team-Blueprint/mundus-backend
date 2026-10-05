import uuid
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_login_success():
    response = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "Password123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "supervisor@mundus.org"
    assert data["user"]["role"] == "contractor"


def test_login_invalid_password():
    response = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "WrongPassword!"}
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_register_returns_tokens():
    unique_email = f"user_{uuid.uuid4().hex[:8]}@mundus.org"
    response = client.post(
        "/auth/register",
        json={
            "email": unique_email,
            "password": "Password123!",
            "full_name": "New User",
            "role": "contractor"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == unique_email


def test_refresh_token_success():
    login_resp = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "Password123!"}
    )
    refresh_token = login_resp.json()["refresh_token"]

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_get_me_success():
    login_resp = client.post(
        "/auth/login",
        json={"email": "agency@mundus.org", "password": "Password123!"}
    )
    token = login_resp.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == "agency@mundus.org"
    assert user_data["role"] == "agency"


def test_get_me_unauthorized():
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_forgot_and_reset_password_otp_flow():
    from app.database import get_db
    from app.auth.models import PasswordResetToken

    test_email = "bassey@mundus.org"

    # 1. Request forgot password - must return message
    forgot_resp = client.post(
        "/auth/forgot-password",
        json={"email": test_email}
    )
    assert forgot_resp.status_code == 200
    assert "message" in forgot_resp.json()

    # 2. Verify OTP was saved in DB and is 6 digits
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    token_record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.email == test_email, PasswordResetToken.used == False)
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    assert token_record is not None
    otp = token_record.token
    assert len(otp) == 6
    assert otp.isdigit()

    # 3. Attempt reset with wrong OTP -> 422
    invalid_resp = client.post(
        "/auth/reset-password",
        json={"email": test_email, "otp": "000000", "new_password": "NewSecretPassword123!"}
    )
    assert invalid_resp.status_code == 422

    # 4. Attempt reset with correct OTP -> 200
    valid_resp = client.post(
        "/auth/reset-password",
        json={"email": test_email, "otp": otp, "new_password": "NewSecretPassword123!"}
    )
    assert valid_resp.status_code == 200
    assert "message" in valid_resp.json()


    # 5. Verify login succeeds with new password
    new_login = client.post(
        "/auth/login",
        json={"email": test_email, "password": "NewSecretPassword123!"}
    )
    assert new_login.status_code == 200

    # 6. Verify reuse of same OTP fails -> 422
    reuse_resp = client.post(
        "/auth/reset-password",
        json={"email": test_email, "otp": otp, "new_password": "AnotherPassword123!"}
    )
    assert reuse_resp.status_code == 422

    # 7. Restore original password for test consistency
    restore_resp = client.post(
        "/auth/forgot-password",
        json={"email": test_email}
    )
    assert restore_resp.status_code == 200
    db.expire_all()
    new_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.email == test_email, PasswordResetToken.used == False)
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    client.post(
        "/auth/reset-password",
        json={"email": test_email, "otp": new_token.token, "new_password": "Password123!"}
    )
    try:
        next(db_gen)
    except StopIteration:
        pass


