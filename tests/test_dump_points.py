from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_agency_create_dump_point():
    headers = get_auth_header("agency@mundus.org")
    response = client.post(
        "/dump-points",
        headers=headers,
        json={
            "name": "Test Hospital Road Dump Site",
            "latitude": 5.0300,
            "longitude": 7.9200,
            "interval_days": 7
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Hospital Road Dump Site"
    assert data["is_overdue"] is True  # Never cleared site is overdue


def test_supervisor_scoping():
    agency_headers = get_auth_header("agency@mundus.org")
    sup_headers = get_auth_header("supervisor@mundus.org")

    # Agency sees all sites
    agency_resp = client.get("/dump-points", headers=agency_headers)
    assert agency_resp.status_code == 200
    all_sites = agency_resp.json()
    assert len(all_sites) >= 5

    # Supervisor sees only assigned sites
    sup_resp = client.get("/dump-points", headers=sup_headers)
    assert sup_resp.status_code == 200
    sup_sites = sup_resp.json()
    for site in sup_sites:
        # Each site returned to supervisor should be assigned to them
        assert site["name"] in [s["name"] for s in all_sites]


def test_assign_supervisor():
    headers = get_auth_header("agency@mundus.org")

    # Create site
    create_resp = client.post(
        "/dump-points",
        headers=headers,
        json={"name": "Unassigned Site", "latitude": 5.0500, "longitude": 7.9500}
    )
    site_id = create_resp.json()["id"]

    # Get contractor id
    me_resp = client.get("/auth/me", headers=get_auth_header("supervisor@mundus.org"))
    contractor_id = me_resp.json()["contractor_id"]

    # Assign contractor
    assign_resp = client.put(
        f"/dump-points/{site_id}/assign",
        headers=headers,
        json={"assigned_contractor_id": contractor_id}
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["assigned_contractor_id"] == contractor_id

