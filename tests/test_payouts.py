import hashlib
import hmac
import time
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app
from app.contractors.models import Contractor
from app.dump_points.models import DumpPoint
from app.check_ins.models import CheckIn, CheckInType, CheckInStatus
from app.payouts.models import PayoutStatement, PayoutStatus
from app.payouts.service import calculate_monthly_clearances
from app.config import settings

client = TestClient(app)


def get_auth_header(email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_clearance_calculation_service_logic(db):
    """Unit test for the exact monthly payout formula & clearance logic:

    expected = floor(days_in_month / interval)
    payout = min(stipend * (verified / expected), stipend)
    """
    try:
        # Create an isolated contractor
        test_c = Contractor(
            id=uuid.uuid4().hex,
            name=f"Formula Test Contractor {uuid.uuid4().hex[:6]}",
            email=f"formula_{uuid.uuid4().hex[:6]}@test.com",
            monthly_stipend=50000.0,
        )
        db.add(test_c)
        db.commit()

        # Add 2 assigned dump points
        # Site 1: interval 7 days (in a 28-day month -> 4 expected)
        # Site 2: interval 7 days (in a 28-day month -> 4 expected)
        # Total expected = 8
        site1 = DumpPoint(
            id=uuid.uuid4().hex,
            name="Formula Site 1",
            latitude=5.030,
            longitude=7.920,
            interval_days=7,
            assigned_contractor_id=test_c.id,
        )
        site2 = DumpPoint(
            id=uuid.uuid4().hex,
            name="Formula Site 2",
            latitude=5.040,
            longitude=7.930,
            interval_days=7,
            assigned_contractor_id=test_c.id,
        )
        db.add_all([site1, site2])
        db.commit()

        # Use Feb 2026 (28 days) -> days_in_month = 28
        period = "2026-02"

        # 1. Zero clearances: earned = 0
        calc_0 = calculate_monthly_clearances(db, test_c.id, period=period)
        assert calc_0["expected_clearances"] == 8
        assert calc_0["verified_clearances"] == 0
        assert calc_0["earned_so_far"] == 0.0

        # 2. Add 6 verified clearances (pairs of before & after) and 1 held clearance
        feb_dates = [
            datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 9, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 12, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 16, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc),
        ]

        for d in feb_dates:
            db.add_all([
                CheckIn(
                    site_id=site1.id,
                    user_id=1,
                    type=CheckInType.BEFORE,
                    photo_url="https://res.cloudinary.com/demo/image/upload/b.jpg",
                    photo_hash=uuid.uuid4().hex,
                    latitude=5.030,
                    longitude=7.920,
                    distance_from_site_meters=10.0,
                    device_timestamp=d,
                    server_timestamp=d,
                    status=CheckInStatus.VALID,
                    flags=[],
                ),
                CheckIn(
                    site_id=site1.id,
                    user_id=1,
                    type=CheckInType.AFTER,
                    photo_url="https://res.cloudinary.com/demo/image/upload/a.jpg",
                    photo_hash=uuid.uuid4().hex,
                    latitude=5.030,
                    longitude=7.920,
                    distance_from_site_meters=10.0,
                    device_timestamp=d + timedelta(hours=1),
                    server_timestamp=d + timedelta(hours=1),
                    status=CheckInStatus.VALID,
                    flags=[],
                ),
            ])

        # Add 1 held clearance (visit with location mismatch flag)
        held_d = datetime(2026, 2, 23, 10, 0, tzinfo=timezone.utc)
        db.add_all([
            CheckIn(
                site_id=site1.id,
                user_id=1,
                type=CheckInType.BEFORE,
                photo_url="https://res.cloudinary.com/demo/image/upload/b_flag.jpg",
                photo_hash=uuid.uuid4().hex,
                latitude=5.030,
                longitude=7.920,
                distance_from_site_meters=300.0,  # Geofence violation
                device_timestamp=held_d,
                server_timestamp=held_d,
                status=CheckInStatus.LOCATION_MISMATCH,
                flags=["location_mismatch"],
            ),
            CheckIn(
                site_id=site1.id,
                user_id=1,
                type=CheckInType.AFTER,
                photo_url="https://res.cloudinary.com/demo/image/upload/a_flag.jpg",
                photo_hash=uuid.uuid4().hex,
                latitude=5.030,
                longitude=7.920,
                distance_from_site_meters=300.0,
                device_timestamp=held_d + timedelta(hours=1),
                server_timestamp=held_d + timedelta(hours=1),
                status=CheckInStatus.LOCATION_MISMATCH,
                flags=["location_mismatch"],
            ),
        ])
        db.commit()

        calc_6 = calculate_monthly_clearances(db, test_c.id, period=period)
        assert calc_6["expected_clearances"] == 8
        assert calc_6["verified_clearances"] == 6
        assert calc_6["held_clearances"] == 1
        # Formula: 50,000 * (6 / 8) = 37,500.00
        assert calc_6["earned_so_far"] == 37500.00
        assert calc_6["progress_percent"] == 75.0

        # 3. Add 4 more verified clearances -> total 10 verified out of 8 expected
        # Should cap at monthly stipend: min(50000 * (10/8), 50000) = 50,000
        extra_dates = [
            datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 25, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 26, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 27, 10, 0, tzinfo=timezone.utc),
        ]
        for d in extra_dates:
            db.add_all([
                CheckIn(
                    site_id=site2.id,
                    user_id=1,
                    type=CheckInType.BEFORE,
                    photo_url="https://res.cloudinary.com/demo/image/upload/b_extra.jpg",
                    photo_hash=uuid.uuid4().hex,
                    latitude=5.040,
                    longitude=7.930,
                    distance_from_site_meters=10.0,
                    device_timestamp=d,
                    server_timestamp=d,
                    status=CheckInStatus.VALID,
                    flags=[],
                ),
                CheckIn(
                    site_id=site2.id,
                    user_id=1,
                    type=CheckInType.AFTER,
                    photo_url="https://res.cloudinary.com/demo/image/upload/a_extra.jpg",
                    photo_hash=uuid.uuid4().hex,
                    latitude=5.040,
                    longitude=7.930,
                    distance_from_site_meters=10.0,
                    device_timestamp=d + timedelta(hours=1),
                    server_timestamp=d + timedelta(hours=1),
                    status=CheckInStatus.VALID,
                    flags=[],
                ),
            ])
        db.commit()

        calc_cap = calculate_monthly_clearances(db, test_c.id, period=period)
        assert calc_cap["verified_clearances"] == 10
        assert calc_cap["earned_so_far"] == 50000.00  # Capped at stipend
        assert calc_cap["progress_percent"] == 100.0

    finally:
        pass


def test_agency_update_contractor_payout_details():
    """Agency sets contractor stipend and bank details; creates recipient with Bachs."""
    agency_headers = get_auth_header("agency@mundus.org")

    # Get a contractor
    c_resp = client.get("/contractors", headers=agency_headers)
    contractor = c_resp.json()[0]
    contractor_id = contractor["id"]

    payload = {
        "monthly_stipend": 65000.0,
        "bank_account_number": "0123456789",
        "bank_code": "058",
        "bank_name": "Guaranty Trust Bank",
        "bank_account_name": "CleanCity Waste Ops",
    }

    resp = client.put(
        f"/agency/contractors/{contractor_id}/payout-details",
        headers=agency_headers,
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["monthly_stipend"] == 65000.0
    assert data["bank_code"] == "058"
    assert data["payment_provider_recipient_id"] is not None
    assert data["payment_provider_recipient_id"].startswith("pd_")
    assert data["is_payout_ready"] is True


def test_contractor_progressive_earnings_endpoint():
    """Contractor can view their own real-time progressive monthly earnings."""
    contractor_headers = get_auth_header("contractor@mundus.org")

    resp = client.get("/contractor/earnings", headers=contractor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "monthly_stipend" in data
    assert "expected_clearances" in data
    assert "verified_clearances" in data
    assert "held_clearances" in data
    assert "earned_so_far" in data
    assert "progress_percent" in data
    assert "sites_breakdown" in data


def test_agency_payouts_workflow_and_idempotency():
    """Full monthly payout flow:

    1. Agency generates statements
    2. Agency lists statements
    3. Agency inspects statement
    4. Agency approves payout (triggers Bachs transfer)
    5. Duplicate approval is idempotent (does NOT transfer twice)
    """
    agency_headers = get_auth_header("agency@mundus.org")
    period = "2026-10"

    # 1. Generate statements for period
    gen_resp = client.post(f"/agency/payouts/generate?period={period}", headers=agency_headers)
    assert gen_resp.status_code == 200
    statements = gen_resp.json()
    assert len(statements) > 0

    target_statement = statements[0]
    stmt_id = target_statement["id"]
    assert target_statement["status"] in ("PENDING_APPROVAL", "DRAFT", "SUCCESS")
    assert target_statement["unique_payout_reference"].startswith("MND-PO-202610-")

    # 2. List payouts with filter
    list_resp = client.get(f"/agency/payouts?period={period}", headers=agency_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total_count"] >= 1
    assert "total_stipend_pool" in list_data
    assert "total_earned_amount" in list_data

    # 3. Get single statement detail
    detail_resp = client.get(f"/agency/payouts/{stmt_id}", headers=agency_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == stmt_id

    # 4. Approve payout statement
    approve_resp = client.post(
        f"/agency/payouts/{stmt_id}/approve",
        headers=agency_headers,
        json={"notes": "Approved by State Director"},
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()
    assert approved_data["status"] in ("SUCCESS", "PROCESSING")
    first_transfer_code = approved_data["transfer_code"]
    first_ref = approved_data["unique_payout_reference"]

    # 5. IDEMPOTENCY TEST: Call approve again
    retry_resp = client.post(
        f"/agency/payouts/{stmt_id}/approve",
        headers=agency_headers,
        json={"notes": "Retry attempt duplicate click"},
    )
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    # Must preserve exact same reference and transfer code without re-initiating
    assert retry_data["transfer_code"] == first_transfer_code
    assert retry_data["unique_payout_reference"] == first_ref


def test_contractor_forbidden_from_approving_payout():
    """Security check: Contractors cannot approve or trigger payouts."""
    contractor_headers = get_auth_header("contractor@mundus.org")

    resp = client.post("/agency/payouts/some-fake-id/approve", headers=contractor_headers)
    assert resp.status_code in (401, 403)


def test_bachs_webhook_signature_and_event_handling(db):
    """Secure Webhook:

    1. Invalid signature rejected with 401
    2. Valid signature for payout.paid transitions statement to SUCCESS
    3. Duplicate webhook is idempotent
    4. payout.failed transitions statement to FAILED
    """
    try:
        # Create a statement in PROCESSING state
        unique_ref = f"MND-PO-WEBHOOK-{uuid.uuid4().hex[:8]}"
        transfer_code = f"pay_{uuid.uuid4().hex[:12]}"
        stmt = PayoutStatement(
            id=uuid.uuid4().hex,
            contractor_id="CTR-AK-001",
            period="2026-10",
            monthly_stipend=50000.0,
            expected_clearances=4,
            verified_clearances=3,
            held_clearances=0,
            calculated_payout_amount=37500.0,
            status=PayoutStatus.PROCESSING,
            unique_payout_reference=unique_ref,
            transfer_code=transfer_code,
            payment_provider="bachs",
        )
        db.add(stmt)
        db.commit()

        webhook_secret = settings.BACHS_WEBHOOK_SECRET or "whsec_test"
        now_ts = int(time.time())

        # Payload for payout.paid
        payload = {
            "id": f"evt_{uuid.uuid4().hex[:16]}",
            "type": "payout.paid",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "withdrawal_id": transfer_code,
                "reference": unique_ref,
                "status": "completed",
                "amount": "37500.00",
                "currency": "NGN",
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        # 1. Invalid signature
        inv_resp = client.post(
            "/payouts/webhooks/bachs",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Bachs-Signature-V2": f"t={now_ts},v1=invalid_fake_signature_hash",
            },
        )
        assert inv_resp.status_code == 401

        # 2. Valid signature (V2 scheme)
        valid_digest = hmac.new(
            webhook_secret.encode(),
            f"{now_ts}.".encode() + body_bytes,
            hashlib.sha256,
        ).hexdigest()
        v2_header = f"t={now_ts},v1={valid_digest}"

        valid_resp = client.post(
            "/payouts/webhooks/bachs",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Bachs-Signature-V2": v2_header,
            },
        )
        assert valid_resp.status_code == 200
        assert valid_resp.json()["status"] == "SUCCESS"

        db.refresh(stmt)
        assert stmt.status == PayoutStatus.SUCCESS

        # 3. Duplicate webhook delivery (Idempotency)
        dup_resp = client.post(
            "/payouts/webhooks/bachs",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Bachs-Signature-V2": v2_header,
            },
        )
        assert dup_resp.status_code == 200
        assert dup_resp.json()["action"] == "already_successful"

        # 4. Failure webhook on another statement
        stmt_fail = PayoutStatement(
            id=uuid.uuid4().hex,
            contractor_id="CTR-AK-001",
            period="2026-10",
            monthly_stipend=50000.0,
            expected_clearances=4,
            verified_clearances=3,
            held_clearances=0,
            calculated_payout_amount=37500.0,
            status=PayoutStatus.PROCESSING,
            unique_payout_reference=f"MND-PO-FAIL-{uuid.uuid4().hex[:8]}",
            transfer_code=f"pay_fail_{uuid.uuid4().hex[:8]}",
            payment_provider="bachs",
        )
        db.add(stmt_fail)
        db.commit()

        fail_payload = {
            "id": f"evt_{uuid.uuid4().hex[:16]}",
            "type": "payout.failed",
            "data": {
                "withdrawal_id": stmt_fail.transfer_code,
                "reference": stmt_fail.unique_payout_reference,
                "status": "failed",
                "failure_reason": "Destination account blocked",
            },
        }
        fail_body = json.dumps(fail_payload).encode("utf-8")
        fail_digest = hmac.new(
            webhook_secret.encode(),
            f"{now_ts}.".encode() + fail_body,
            hashlib.sha256,
        ).hexdigest()

        fail_resp = client.post(
            "/payouts/webhooks/bachs",
            content=fail_body,
            headers={
                "Content-Type": "application/json",
                "X-Bachs-Signature-V2": f"t={now_ts},v1={fail_digest}",
            },
        )
        assert fail_resp.status_code == 200
        db.refresh(stmt_fail)
        assert stmt_fail.status == PayoutStatus.FAILED
        assert stmt_fail.failure_reason == "Destination account blocked"

    finally:
        pass


def test_bank_reference_and_resolution():
    """Public bank directory & account resolution endpoints."""
    # List banks
    banks_resp = client.get("/payouts/banks")
    assert banks_resp.status_code == 200
    banks = banks_resp.json()
    assert len(banks) >= 10
    gtbank = next((b for b in banks if b["code"] == "058"), None)
    assert gtbank is not None
    assert "Guaranty Trust" in gtbank["name"]

    # Resolve account
    resolve_resp = client.post(
        "/payouts/resolve-account",
        json={"account_number": "0123456789", "bank_code": "058"},
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["account_number"] == "0123456789"
    assert "account_name" in res_data


def test_csv_export_and_receipt_endpoints():
    """Agency CSV export and individual payout receipt."""
    agency_headers = get_auth_header("agency@mundus.org")

    # CSV Export
    csv_resp = client.get("/agency/payouts/export", headers=agency_headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["Content-Type"]
    assert "Reference" in csv_resp.text
    assert "Monthly Stipend" in csv_resp.text

    # Receipt for existing statement
    p_resp = client.get("/agency/payouts", headers=agency_headers)
    statements = p_resp.json()["statements"]
    if statements:
        target_id = statements[0]["id"]
        receipt_resp = client.get(f"/agency/payouts/{target_id}/receipt", headers=agency_headers)
        assert receipt_resp.status_code == 200
        rcpt = receipt_resp.json()
        assert rcpt["receipt_id"].startswith("RCT-")
        assert rcpt["currency"] == "NGN"
        assert "sandbox" in rcpt["environment"]


def test_held_clearance_review_and_clear_action(db):
    """Held clearances can be inspected and approved/cleared by agency."""
    agency_headers = get_auth_header("agency@mundus.org")

    try:
        # Create a site and check-in with flag
        test_site = DumpPoint(
            id=uuid.uuid4().hex,
            name="Flagged Test Dump Site",
            latitude=5.020,
            longitude=7.910,
            interval_days=7,
        )
        db.add(test_site)
        db.commit()

        d_now = datetime.now(timezone.utc)
        d_str = d_now.strftime("%Y-%m-%d")

        ci_flagged = CheckIn(
            site_id=test_site.id,
            user_id=1,
            type=CheckInType.BEFORE,
            photo_url="https://res.cloudinary.com/demo/image/upload/b_flag.jpg",
            photo_hash=uuid.uuid4().hex,
            latitude=5.020,
            longitude=7.910,
            distance_from_site_meters=250.0,
            device_timestamp=d_now,
            server_timestamp=d_now,
            status=CheckInStatus.FLAGGED,
            flags=["photo_flagged_for_review"],
        )
        db.add(ci_flagged)
        db.commit()

        # 1. Agency lists held clearances
        held_resp = client.get("/agency/clearances/held", headers=agency_headers)
        assert held_resp.status_code == 200
        held_list = held_resp.json()
        assert any(item["site_id"] == test_site.id for item in held_list)

        # 2. Agency clears the held clearance
        clear_resp = client.post(
            f"/agency/clearances/{test_site.id}/{d_str}/approve",
            headers=agency_headers,
        )
        assert clear_resp.status_code == 200

        # Check-in status is now VALID
        db.refresh(ci_flagged)
        assert ci_flagged.status == CheckInStatus.VALID
        assert len(ci_flagged.flags) == 0

    finally:
        pass


def test_agency_payments_ui_endpoint():
    """Agency Payments Dashboard HTML endpoint serves responsive UI."""
    resp = client.get("/agency/payments/ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["Content-Type"]
    assert "Mundus" in resp.text
    assert "Bachs Sandbox" in resp.text

    # Shortcut endpoint
    resp_shortcut = client.get("/payments")
    assert resp_shortcut.status_code == 200

