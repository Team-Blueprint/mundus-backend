from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.auth.service import get_user_by_email

client = TestClient(app)


def test_login_success():
    response = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "Password123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "supervisor@mundus.org"
    assert data["user"]["role"] == "supervisor"


def test_login_invalid_password():
    response = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "WrongPassword!"}
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_get_me_success():
    # Login first
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

