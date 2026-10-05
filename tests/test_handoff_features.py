import uuid
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_contractors_crud_and_supervisor_workflow():
    agency_headers = get_auth_header("agency@mundus.org")

    # 1. Create new contractor + supervisor
    unique_suffix = uuid.uuid4().hex[:6]
    contractor_payload = {
        "name": f"Delta Cleaners {unique_suffix}",
        "name": f"Kufre Jackson {unique_suffix}",
        "email": f"kufre_{unique_suffix}@deltaclean.ng",
        "password": "Password123!",
    }

    create_resp = client.post("/contractors", headers=agency_headers, json=contractor_payload)
    assert create_resp.status_code == 201
    contractor = create_resp.json()
    assert contractor["name"] == contractor_payload["name"]
    assert contractor["email"] == contractor_payload["email"]

    # 2. List contractors
    list_resp = client.get("/contractors", headers=agency_headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == contractor["id"] for c in list_resp.json())

    # 3. Login as new supervisor
    sup_login_resp = client.post(
        "/auth/login",
        json={"email": contractor_payload["email"], "password": "Password123!"},
    )
    assert sup_login_resp.status_code == 200
    sup_token = sup_login_resp.json()["access_token"]
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    # 4. Supervisor password change
    pw_resp = client.patch(
        f"/users/{sup_login_resp.json()['user']['id']}/password",
        headers=sup_headers,
        json={"current_password": "Password123!", "new_password": "NewPassword123!"},
    )
    assert pw_resp.status_code == 200

    # 5. Supervisor sites list
    sites_resp = client.get("/contractor/sites", headers=sup_headers)
    assert sites_resp.status_code == 200

    # 6. Supervisor submissions history
    subs_resp = client.get("/contractor/submissions", headers=sup_headers)
    assert subs_resp.status_code == 200


def test_reporter_nominate_approve_and_public_flag():
    sup_headers = get_auth_header("supervisor@mundus.org")
    agency_headers = get_auth_header("agency@mundus.org")

    # 1. Get an existing site
    sites_resp = client.get("/dump-points", headers=agency_headers)
    site = sites_resp.json()[0]
    site_id = site["id"]

    # 2. Nominate reporter
    phone = f"080{uuid.uuid4().int % 100000000:08d}"
    nominate_payload = {
        "site_id": site_id,
        "contractor_id": "CTR-AK-003",
        "name": "Jane Ukpong",
        "phone": phone,
    }
    nom_resp = client.post("/reporters/nominate", headers=sup_headers, json=nominate_payload)
    assert nom_resp.status_code == 201
    reporter_data = nom_resp.json()
    assert reporter_data["name"] == "Jane Ukpong"
    assert reporter_data["status"] == "pending"
    reporter_id = reporter_data["id"]

    # 3. Approve reporter (Agency)
    appr_resp = client.post(f"/reporters/{reporter_id}/approve", headers=agency_headers)
    assert appr_resp.status_code == 200
    approval_result = appr_resp.json()
    token = approval_result["token"]
    assert token is not None
    assert "whatsapp_link" in approval_result
    assert "wa.me" in approval_result["whatsapp_link"]

    # 4. Public token resolution GET /r/{token} (NO AUTH)
    public_resp = client.get(f"/r/{token}")
    assert public_resp.status_code == 200
    res_data = public_resp.json()
    assert res_data["reporter"]["name"] == "Jane Ukpong"
    assert res_data["site"]["id"] == site_id

    # 5. Public flag site POST /reporters/flag-site (NO AUTH, with reporter_token)
    # Use another unflagged site to avoid 12h rate limit if site[0] was flagged
    # Create a fresh site for clean flag test
    new_site_resp = client.post(
        "/dump-points",
        headers=agency_headers,
        json={
            "name": f"Fresh Flag Test Site {uuid.uuid4().hex[:4]}",
            "latitude": 5.035,
            "longitude": 7.915,
            "code": "AK-TEST-01",
            "sector": "Sector 9 · Test Sector",
        },
    )
    fresh_site_id = new_site_resp.json()["id"]

    # Nominate and approve for fresh site
    phone2 = f"081{uuid.uuid4().int % 100000000:08d}"
    nom2 = client.post(
        "/reporters/nominate",
        headers=agency_headers,
        json={"site_id": fresh_site_id, "name": "Mfon Obot", "phone": phone2},
    )
    appr2 = client.post(f"/reporters/{nom2.json()['id']}/approve", headers=agency_headers)
    token2 = appr2.json()["token"]

    public_flag_resp = client.post(
        "/reporters/flag-site",
        json={"site_id": fresh_site_id, "reporter_token": token2, "note": "Bin overflowing onto walk path"},
    )
    assert public_flag_resp.status_code == 201
    flag_result = public_flag_resp.json()
    assert flag_result["site_id"] == fresh_site_id
    assert flag_result["reporter_name"] == "Mfon Obot"

    # Second flag on same site returns 429
    second_public_flag = client.post(
        "/reporters/flag-site",
        json={"site_id": fresh_site_id, "reporter_token": token2, "note": "Repeat flag"},
    )
    assert second_public_flag.status_code == 429

    # Clean up test site
    del_resp = client.delete(f"/dump-points/{fresh_site_id}", headers=agency_headers)
    assert del_resp.status_code == 200


def test_agency_access_requests():
    agency_headers = get_auth_header("agency@mundus.org")

    # Public request access
    req_resp = client.post(
        "/agency/request-access",
        json={"full_name": "Commissioner of Environment", "email": "commissioner@akwaibom.gov.ng"},
    )
    assert req_resp.status_code == 201
    assert req_resp.json()["status"] == "pending"

    # Agency list requests
    list_resp = client.get("/agency/requests", headers=agency_headers)
    assert list_resp.status_code == 200
    assert any(r["email"] == "commissioner@akwaibom.gov.ng" for r in list_resp.json())


def test_device_registration_and_alerts():
    sup_headers = get_auth_header("supervisor@mundus.org")

    # Register FCM token
    reg_resp = client.post(
        "/devices/register",
        headers=sup_headers,
        json={"fcm_token": f"fcm_test_token_{uuid.uuid4().hex[:8]}", "role": "contractor"},
    )
    assert reg_resp.status_code == 200

    # Get contractor alerts
    alerts_resp = client.get("/contractor/alerts", headers=sup_headers)
    assert alerts_resp.status_code == 200

    # Dismiss alert
    seen_resp = client.post("/contractor/alerts/1/seen", headers=sup_headers)
    assert seen_resp.status_code == 200


def test_dumppoint_code_and_sector_persistence():
    agency_headers = get_auth_header("agency@mundus.org")

    create_resp = client.post(
        "/dump-points",
        headers=agency_headers,
        json={
            "name": "Ewet Housing Dump Point",
            "code": "AK-UYO-EWT-09",
            "sector": "Sector 8 · Ewet Housing Estate",
            "latitude": 5.0150,
            "longitude": 7.9420,
            "interval_days": 5,
        },
    )
    assert create_resp.status_code == 201
    site = create_resp.json()
    assert site["code"] == "AK-UYO-EWT-09"
    assert site["sector"] == "Sector 8 · Ewet Housing Estate"

    # Verify detail returns code & sector
    detail_resp = client.get(f"/dump-points/{site['id']}", headers=agency_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["code"] == "AK-UYO-EWT-09"
    assert detail_resp.json()["sector"] == "Sector 8 · Ewet Housing Estate"

    # Delete site
    del_resp = client.delete(f"/dump-points/{site['id']}", headers=agency_headers)
    assert del_resp.status_code == 200
