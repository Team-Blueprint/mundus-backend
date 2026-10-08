from datetime import datetime, timezone
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_reporter_flag_site_success_and_rate_limit():
    reporter_headers = get_auth_header("reporter@mundus.org")
    agency_headers = get_auth_header("agency@mundus.org")

    # Create a fresh isolated site for this test
    create_resp = client.post(
        "/dump-points",
        headers=agency_headers,
        json={"name": "Isolated Flag Test Site", "latitude": 5.040, "longitude": 7.920}
    )
    site_id = create_resp.json()["id"]

    # Omitting photo_url returns 422
    missing_photo_resp = client.post(
        "/reporters/flag-site",
        headers=reporter_headers,
        json={"site_id": site_id, "note": "No photo provided"}
    )
    assert missing_photo_resp.status_code == 422

    # 1. First flag succeeds
    flag_resp = client.post(
        "/reporters/flag-site",
        headers=reporter_headers,
        json={
            "site_id": site_id,
            "photo_url": "https://storage.mundus.org/flag1.jpg",
            "note": "Overflowing waste at market entrance"
        }
    )
    assert flag_resp.status_code == 201
    data = flag_resp.json()
    assert data["site_id"] == site_id
    assert "Overflowing" in data["note"]

    # 2. Second flag on same site within 12h is rate-limited with HTTP 429
    second_flag_resp = client.post(
        "/reporters/flag-site",
        headers=reporter_headers,
        json={
            "site_id": site_id,
            "photo_url": "https://storage.mundus.org/flag2.jpg",
            "note": "Duplicate flag test"
        }
    )
    assert second_flag_resp.status_code == 429
    res_data = second_flag_resp.json()
    assert "detail" in res_data
    assert "retry_in_seconds" in res_data
    assert isinstance(res_data["retry_in_seconds"], int)
    assert "Already reported" in res_data["detail"]

    # Clean up
    client.delete(f"/dump-points/{site_id}", headers=agency_headers)



def test_photo_pairings_endpoint():
    sup_headers = get_auth_header("supervisor@mundus.org")

    sites_resp = client.get("/dump-points", headers=sup_headers)
    site_id = sites_resp.json()[0]["id"]

    pairings_resp = client.get(f"/check-ins/pairings/{site_id}", headers=sup_headers)
    assert pairings_resp.status_code == 200
    data = pairings_resp.json()
    assert "before_check_in" in data
    assert "after_check_in" in data
    assert "is_cleared" in data


def test_site_history_timeline_endpoint():
    agency_headers = get_auth_header("agency@mundus.org")

    sites_resp = client.get("/dump-points", headers=agency_headers)
    site_id = sites_resp.json()[0]["id"]

    history_resp = client.get(f"/dump-points/{site_id}/history", headers=agency_headers)
    assert history_resp.status_code == 200
    timeline = history_resp.json()
    assert isinstance(timeline, list)
    if len(timeline) > 0:
        event = timeline[0]
        assert "kind" in event
        assert "at" in event
        assert "actor" in event
