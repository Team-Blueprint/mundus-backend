from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_agency_dashboard_success():
    headers = get_auth_header("agency@mundus.org")
    response = client.get("/dashboard/sites", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "total_sites" in data
    assert "overdue_sites_count" in data
    assert "cleared_sites_count" in data
    assert "sites" in data

    sites = data["sites"]
    assert len(sites) >= 5

    # Verify descending sort order (sites with None / max days come first)
    days_list = [s["days_since_last_clearance"] for s in sites if s["days_since_last_clearance"] is not None]
    assert days_list == sorted(days_list, reverse=True)

    # Verify overdue flags for pre-seeded overdue sites (> 10 days)
    overdue_sites = [s for s in sites if s["is_overdue"]]
    assert len(overdue_sites) >= 2


def test_supervisor_cannot_access_agency_dashboard():
    sup_headers = get_auth_header("supervisor@mundus.org")
    response = client.get("/dashboard/sites", headers=sup_headers)
    assert response.status_code == 403
    assert "does not have permission" in response.json()["error"]

