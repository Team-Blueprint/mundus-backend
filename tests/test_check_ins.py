import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_submit_valid_check_in():
    sup_headers = get_auth_header("supervisor@mundus.org")

    # Get a site assigned to supervisor
    sites_resp = client.get("/dump-points", headers=sup_headers)
    assert len(sites_resp.json()) > 0
    site = sites_resp.json()[0]

    # Submit check-in at exact site coordinates (0m distance)
    now = datetime.now(timezone.utc).isoformat()
    unique_hash = f"valid_{uuid.uuid4().hex}"
    payload = {
        "site_id": site["id"],
        "type": "before",
        "photo_url": "https://res.cloudinary.com/demo/image/upload/v1/dump1.jpg",
        "photo_hash": unique_hash,
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "device_timestamp": now,
    }

    response = client.post("/check-ins", headers=sup_headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "valid"
    assert data["distance_from_site_meters"] < 1.0
    assert len(data["flags"]) == 0


def test_geofence_mismatch_flag():
    sup_headers = get_auth_header("supervisor@mundus.org")

    sites_resp = client.get("/dump-points", headers=sup_headers)
    site = sites_resp.json()[0]

    # Submit check-in ~500m away (lat + 0.005 deg)
    now = datetime.now(timezone.utc).isoformat()
    unique_hash = f"far_{uuid.uuid4().hex}"
    payload = {
        "site_id": site["id"],
        "type": "before",
        "photo_url": "https://res.cloudinary.com/demo/image/upload/v1/dump_far.jpg",
        "photo_hash": unique_hash,
        "latitude": site["latitude"] + 0.005,
        "longitude": site["longitude"],
        "device_timestamp": now,
    }

    response = client.post("/check-ins", headers=sup_headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "location_mismatch"
    assert data["distance_from_site_meters"] > 100.0
    assert any("location_mismatch" in f for f in data["flags"])


def test_after_clearance_updates_site_timestamp():
    sup_headers = get_auth_header("supervisor@mundus.org")

    sites_resp = client.get("/dump-points", headers=sup_headers)
    site = sites_resp.json()[0]

    now = datetime.now(timezone.utc).isoformat()
    unique_hash = f"after_{uuid.uuid4().hex}"
    payload = {
        "site_id": site["id"],
        "type": "after",
        "photo_url": "https://res.cloudinary.com/demo/image/upload/v1/dump_after.jpg",
        "photo_hash": unique_hash,
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "device_timestamp": now,
    }

    response = client.post("/check-ins", headers=sup_headers, json=payload)
    assert response.status_code == 201

    # Verify site last_clearance_timestamp was updated
    updated_site_resp = client.get(f"/dump-points/{site['id']}", headers=sup_headers)
    assert updated_site_resp.json()["last_clearance_timestamp"] is not None

