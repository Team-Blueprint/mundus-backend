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

    # Omitting photo_url returns 422
    missing_photo_resp = client.post(
        "/reporters/flag-site",
        json={"site_id": fresh_site_id, "reporter_token": token2, "note": "Missing photo"},
    )
    assert missing_photo_resp.status_code == 422

    public_flag_resp = client.post(
        "/reporters/flag-site",
        json={
            "site_id": fresh_site_id,
            "reporter_token": token2,
            "photo_url": "https://storage.mundus.org/evidence.jpg",
            "note": "Bin overflowing onto walk path",
        },
    )
    assert public_flag_resp.status_code == 201
    flag_result = public_flag_resp.json()
    assert flag_result["site_id"] == fresh_site_id
    assert flag_result["reporter_name"] == "Mfon Obot"

    # Second flag on same site returns 429
    second_public_flag = client.post(
        "/reporters/flag-site",
        json={
            "site_id": fresh_site_id,
            "reporter_token": token2,
            "photo_url": "https://storage.mundus.org/evidence2.jpg",
            "note": "Repeat flag",
        },
    )
    assert second_public_flag.status_code == 429
    err_body = second_public_flag.json()
    assert "detail" in err_body
    assert "retry_in_seconds" in err_body
    assert isinstance(err_body["retry_in_seconds"], int)

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


def test_password_change_authorization():
    agency_headers = get_auth_header("agency@mundus.org")
    contractor_headers = get_auth_header("contractor@mundus.org")

    agency_me = client.get("/auth/me", headers=agency_headers).json()
    contractor_me = client.get("/auth/me", headers=contractor_headers).json()

    # 1. Contractor attempting to change agency user password receives 403 Forbidden
    forbidden_resp = client.patch(
        f"/users/{agency_me['id']}/password",
        headers=contractor_headers,
        json={"new_password": "NewSecretPassword123!"},
    )
    assert forbidden_resp.status_code == 403

    # 2. Contractor can change their own password
    own_resp = client.patch(
        "/users/password",
        headers=contractor_headers,
        json={
            "current_password": "Password123!",
            "new_password": "UpdatedPassword123!",
        },
    )
    assert own_resp.status_code == 200

    # Verify login with updated password works
    re_login = client.post(
        "/auth/login",
        json={"email": "contractor@mundus.org", "password": "UpdatedPassword123!"},
    )
    assert re_login.status_code == 200
    new_token = re_login.json()["access_token"]
    updated_headers = {"Authorization": f"Bearer {new_token}"}

    # Reset password back to original Password123!
    reset_back = client.patch(
        "/users/password",
        headers=updated_headers,
        json={
            "current_password": "UpdatedPassword123!",
            "new_password": "Password123!",
        },
    )
    assert reset_back.status_code == 200

    # 3. Agency can change another user's password with administrative authority
    agency_change_resp = client.patch(
        f"/users/{contractor_me['id']}/password",
        headers=agency_headers,
        json={"new_password": "Password123!"},
    )
    assert agency_change_resp.status_code == 200


def test_agency_wallet_endpoint():
    agency_headers = get_auth_header("agency@mundus.org")
    contractor_headers = get_auth_header("contractor@mundus.org")

    # Contractor is rejected with 403 Forbidden
    contractor_resp = client.get("/agency/wallet", headers=contractor_headers)
    assert contractor_resp.status_code == 403

    # Agency receives 200 OK with wallet structure
    wallet_resp = client.get("/agency/wallet", headers=agency_headers)
    assert wallet_resp.status_code == 200
    wallet = wallet_resp.json()
    assert "balance" in wallet
    assert isinstance(wallet["balance"], (int, float))
    assert wallet["currency"] == "NGN"
    assert "last_updated" in wallet


def test_contractor_update_payout_details():
    contractor_headers = get_auth_header("contractor@mundus.org")
    agency_headers = get_auth_header("agency@mundus.org")

    # Agency calling contractor endpoint gets 403
    agency_forbidden = client.put(
        "/contractor/payout-details",
        headers=agency_headers,
        json={"bank_code": "058", "bank_account_number": "0123456789", "monthly_stipend": 50000.0},
    )
    assert agency_forbidden.status_code == 403

    # Contractor updates own payout details
    payload = {
        "bank_code": "058",
        "bank_account_number": "0123456789",
        "bank_account_name": "Emmanuel Udo",
        "bank_name": "Guaranty Trust Bank",
        "monthly_stipend": 50000.0,
    }
    update_resp = client.put(
        "/contractor/payout-details",
        headers=contractor_headers,
        json=payload,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["bank_code"] == "058"
    assert data["bank_account_number"] == "0123456789"
    assert data["bank_account_name"] == "Emmanuel Udo"
    assert data["monthly_stipend"] == 50000.0

    # Contractor updates payout details omitting monthly_stipend (optional field)
    payload_no_stipend = {
        "bank_code": "057",
        "bank_account_number": "1023456789",
        "bank_account_name": "Emmanuel Udo",
        "bank_name": "Zenith Bank",
    }
    update_no_stipend_resp = client.put(
        "/contractor/payout-details",
        headers=contractor_headers,
        json=payload_no_stipend,
    )
    assert update_no_stipend_resp.status_code == 200
    data_no_stipend = update_no_stipend_resp.json()
    assert data_no_stipend["bank_code"] == "057"
    assert data_no_stipend["bank_account_number"] == "1023456789"
    assert data_no_stipend["monthly_stipend"] == 50000.0


def test_pagination_x_total_count_headers():
    agency_headers = get_auth_header("agency@mundus.org")

    # /contractors
    c_resp = client.get("/contractors?page=1&limit=5", headers=agency_headers)
    assert c_resp.status_code == 200
    assert isinstance(c_resp.json(), list)
    assert "x-total-count" in c_resp.headers

    # /dump-points
    dp_resp = client.get("/dump-points?page=1&limit=5", headers=agency_headers)
    assert dp_resp.status_code == 200
    assert isinstance(dp_resp.json(), list)
    assert "x-total-count" in dp_resp.headers

    # /reporters
    rep_resp = client.get("/reporters?page=1&limit=5", headers=agency_headers)
    assert rep_resp.status_code == 200
    assert isinstance(rep_resp.json(), list)
    assert "x-total-count" in rep_resp.headers


def test_insufficient_platform_balance_rejection(db, monkeypatch):
    from app.payouts.bachs_client import BachsClient
    from app.payouts.models import PayoutStatement, PayoutStatus
    agency_headers = get_auth_header("agency@mundus.org")

    stmt = PayoutStatement(
        id=uuid.uuid4().hex,
        contractor_id="CTR-AK-001",
        period="2026-04",
        monthly_stipend=50000.0,
        expected_clearances=4,
        verified_clearances=4,
        held_clearances=0,
        calculated_payout_amount=50000.0,
        status=PayoutStatus.PENDING_APPROVAL,
        unique_payout_reference=f"MND-{uuid.uuid4().hex[:12].upper()}",
    )
    db.add(stmt)
    db.commit()

    # Monkeypatch BachsClient.get_balance to return balance lower than amount_to_pay
    monkeypatch.setattr(BachsClient, "get_balance", lambda self: {
        "balance": 100.0,
        "currency": "NGN",
        "last_updated": "2026-10-08T00:00:00Z"
    })

    approve_resp = client.post(f"/agency/payouts/{stmt.id}/approve", headers=agency_headers)
    assert approve_resp.status_code == 400
    assert "insufficient_platform_balance" in str(approve_resp.json())


def test_agency_wallet_topup_flow():
    import hmac
    import hashlib
    import time
    import json
    from app.config import settings

    contractor_headers = get_auth_header("contractor@mundus.org")
    agency_headers = get_auth_header("agency@mundus.org")

    # 1. Contractor cannot initiate wallet top-up
    forbidden_resp = client.post(
        "/agency/wallet/topup",
        headers=contractor_headers,
        json={"amount": 500000.0},
    )
    assert forbidden_resp.status_code == 403

    # 2. Invalid amount (<= 0) rejected with 422
    invalid_resp = client.post(
        "/agency/wallet/topup",
        headers=agency_headers,
        json={"amount": 0},
    )
    assert invalid_resp.status_code == 422

    # 3. Agency initiates wallet top-up session
    topup_resp = client.post(
        "/agency/wallet/topup",
        headers=agency_headers,
        json={"amount": 750000.0, "redirect_url": "https://usemundus.pxxl.click/agency/wallet"},
    )
    assert topup_resp.status_code == 201
    topup_data = topup_resp.json()
    assert topup_data["amount"] == 750000.0
    assert topup_data["currency"] == "NGN"
    assert topup_data["status"] == "pending"
    assert "checkout_url" in topup_data
    assert "reference" in topup_data
    topup_ref = topup_data["reference"]
    assert topup_ref.startswith("TOPUP-AK-")

    # 4. List topups shows the created record
    list_resp = client.get("/agency/wallet/topups", headers=agency_headers)
    assert list_resp.status_code == 200
    topups = list_resp.json()
    assert any(t["reference"] == topup_ref for t in topups)

    # 5. Bachs collection.succeeded webhook marks topup as completed
    webhook_secret = settings.BACHS_WEBHOOK_SECRET or "whsec_test"
    now_ts = int(time.time())
    payload = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "type": "collection.succeeded",
        "data": {
            "reference": topup_ref,
            "amount": "750000.00",
            "currency": "NGN",
            "status": "completed",
        },
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    valid_digest = hmac.new(
        webhook_secret.encode(),
        f"{now_ts}.".encode() + body_bytes,
        hashlib.sha256,
    ).hexdigest()
    v2_header = f"t={now_ts},v1={valid_digest}"

    wh_resp = client.post(
        "/payouts/webhooks/bachs",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Bachs-Signature-V2": v2_header,
        },
    )
    assert wh_resp.status_code == 200
    assert wh_resp.json()["action"] == "wallet_topup_completed"

    # Verify topup list now reflects completed status
    updated_list_resp = client.get("/agency/wallet/topups", headers=agency_headers)
    assert updated_list_resp.status_code == 200
    matched = next((t for t in updated_list_resp.json() if t["reference"] == topup_ref), None)
    assert matched is not None
    assert matched["status"] == "completed"

