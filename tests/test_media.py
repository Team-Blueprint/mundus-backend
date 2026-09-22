import io
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_media_upload_requires_auth():
    response = client.post("/media/upload")
    assert response.status_code == 401


@patch("cloudinary.uploader.upload")
def test_media_upload_success(mock_cloudinary_upload):
    mock_cloudinary_upload.return_value = {
        "secure_url": "https://res.cloudinary.com/mundus-test/image/upload/v1/test_dump.jpg",
        "url": "http://res.cloudinary.com/mundus-test/image/upload/v1/test_dump.jpg",
    }

    # Login as supervisor
    login_resp = client.post(
        "/auth/login",
        json={"email": "supervisor@mundus.org", "password": "Password123!"}
    )
    token = login_resp.json()["access_token"]

    # Upload mock image
    file_bytes = b"FAKE_IMAGE_BYTES_MUNDUS_TEST"
    files = {"file": ("test_dump.jpg", io.BytesIO(file_bytes), "image/jpeg")}

    response = client.post(
        "/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )

    assert response.status_code == 201
    data = response.json()
    assert "photo_url" in data
    assert "photo_hash" in data
    assert data["filename"] == "test_dump.jpg"

