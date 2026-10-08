# Mundus Backend — Monthly Contractor Payout Integration

> **Core System Philosophy:**  
> *"Mundus doesn't hold government money. It works out how much of an existing monthly stipend was earned, and the agency releases it."*

---

## 1. Scope & Operating Principles

**Mundus does not create a new compensation stream.** It calculates the portion of an existing monthly contractor stipend earned through verified service and provides the agency with a controlled mechanism to release that amount.

* **Never pay per clearance:** Individual verified visits track progress throughout the month, but no payments or transfers move per visit.
* **Monthly Stipend Base:** Each contractor has a pre-agreed monthly stipend and assigned waste dump sites with configured clearance intervals.
* **Agency Approval Gate:** Actual money moves only after the government waste agency inspects and approves the monthly payout statement.
* **Test / Sandbox Mode:** The demo payment integration operates exclusively in test mode with **Bachs** (`https://sandbox-api.bachs.io`) and **does not move real money**.

---

## 2. Payout Formula & Mathematical Logic

### A. Expected Clearances
For each dump site assigned to a contractor:
$$\text{expected clearances per site} = \left\lfloor \frac{\text{days in month}}{\text{clearance interval (days)}} \right\rfloor$$

Total expected clearances for a contractor across all assigned sites:
$$\text{expected clearances} = \sum_{\text{sites}} \left\lfloor \frac{\text{days in month}}{\text{interval\_days}} \right\rfloor$$

*Example:* In February (28 days) with a 7-day clearance interval on 2 assigned sites:
$$\text{Site 1: } \lfloor 28 / 7 \rfloor = 4$$
$$\text{Site 2: } \lfloor 28 / 7 \rfloor = 4$$
$$\text{Total Expected} = 8 \text{ clearances}$$

If the agency requires daily service, configure the site interval to **1 day** ($\lfloor 28 / 1 \rfloor = 28$ expected).

### B. Verified Clearances
A clearance visit counts as **verified** only when:
1. Completed **BEFORE** photo submitted.
2. Completed **AFTER** photo submitted.
3. Both check-ins are within the geofence radius ($\le 100\text{m}$ of site coordinates).
4. Passes SHA-256 duplicate-photo detection.
5. Has **not** been flagged for review.

### C. Held Clearances
Any visit with anomalies (location mismatch $> 100\text{m}$, duplicate image hash, reporter issue) is placed on **HOLD**. Held clearances do **not** contribute to earned amounts until the agency inspects and clears them.

### D. Payout Amount
$$\text{payout} = \min\left( \text{monthly\_stipend} \times \frac{\text{verified\_clearances}}{\text{expected\_clearances}}, \; \text{monthly\_stipend} \right)$$

*Example:*
* Monthly stipend: ₦50,000
* Expected clearances: 8
* Verified clearances: 6
* Held clearances: 1
$$\text{Earned so far} = ₦50,000 \times \left(\frac{6}{8}\right) = ₦37,500$$

Edge cases such as zero expected clearances or zero verified clearances evaluate safely to `₦0.00`.

---

## 3. End-to-End Payout Lifecycle

```text
[Field Service Check-Ins]
         │
         ▼
[Anti-Fraud Geofence & Photo Validation]
         │
         ├── Passes ───► Counted as Verified
         └── Fails ────► Placed on Hold for Review (Agency Queue)
                             │
                             └── (Agency clears flag) ──► Becomes Verified
         │
         ▼
[Progressive Earnings Tracker (In-Month)]
(Contractor views live progress; no money moves)
         │
         ▼
[Month-End Payout Statement Generation]
(Immutable snapshot of stipend, verified count, & earned amount)
         │
         ▼
[Agency Review & Approval] ──► Idempotent Bachs Transfer Initiation
                               (Unique Reference: MND-PO-YYYYMM-...)
                               (Idempotency-Key header sent)
         │
         ▼
[Bachs Payment Provider Webhook]
(HMAC-SHA256 signature verified)
         │
         ├── payout.paid   ───► Marked SUCCESS & Receipt Generated
         └── payout.failed ───► Marked FAILED & Audit Logged
```

---

## 4. Payment Provider: Bachs Sandbox Integration

* **Documentation:** [https://docs.bachs.io/integrate/sandbox](https://docs.bachs.io/integrate/sandbox)
* **API Base URL:** `https://sandbox-api.bachs.io`
* **Recipient Destination:** Created once (`POST /v1/payouts/destinations`) when the contractor's bank account is configured and reused for subsequent monthly payouts.
* **Payout Initiation:** `POST /v1/payouts` with JSON body `{ destination_id, amount: "37500.00", currency: "NGN", reference }` and `Idempotency-Key` header.
* **Webhook Signature:** Verified with HMAC-SHA256 hex digest using `BACHS_WEBHOOK_SECRET` over `t={timestamp}.{body}` (`X-Bachs-Signature-V2` header).

---

## 5. API Reference

### Agency Payments & Statements
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/agency/payouts/ui` | Interactive Agency Payments Dashboard (Web UI) |
| `GET` | `/agency/payouts` | List monthly payout statements (filters: `period`, `status`) |
| `POST` | `/agency/payouts/generate` | Generate month-end payout statements from verified service |
| `GET` | `/agency/payouts/{id}` | Inspect payout statement details & formula breakdown |
| `POST` | `/agency/payouts/{id}/approve` | **Idempotent** approval & transfer initiation via Bachs |
| `POST` | `/agency/payouts/bulk-approve` | Bulk approve multiple statements |
| `GET` | `/agency/payouts/export` | Export payout statements to CSV |
| `GET` | `/agency/payouts/{id}/receipt` | Printable payment voucher / receipt |
| `GET` | `/agency/clearances/held` | Queue of flagged clearances on hold |
| `POST` | `/agency/clearances/{site_id}/{date}/approve` | Clear flagged visit into verified count |
| `PUT` | `/agency/contractors/{id}/payout-details` | Set contractor stipend & bank details (registers Bachs destination) |

### Contractor Progressive View
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/contractor/earnings` | Current month progressive earned amount & verification count |
| `GET` | `/contractor/payouts` | Contractor's historical payout statements |

### Webhooks & Utilities
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/payouts/webhooks/bachs` | Secure Bachs webhook listener (`payout.paid`, `payout.failed`) |
| `GET` | `/payouts/banks` | Nigerian bank directory lookup |
| `POST` | `/payouts/resolve-account` | Resolve bank account name |

---

## 6. Agency Payments Dashboard UI

Mundus includes a rich, responsive agency dashboard served directly by the backend at:
```text
http://localhost:8000/agency/payments/ui
(or shortcut: http://localhost:8000/payments)
```

**Features:**
* **Real-time KPI Cards:** Total Stipend Pool, Earned to Release, Verification Rate %, and Clearances on Hold.
* **Payout Statements Table:** Complete breakdown with service percentages, status badges, and action triggers.
* **Review & Approval Modal:** Interactive snapshot calculation breakdown, bank details, and idempotent transfer button.
* **Held Clearances Review Drawer:** Inspect flagged before/after photos with geofence distance and 1-click clearance approval.
* **Bachs Webhook Simulator:** Test incoming `payout.paid` and `payout.failed` sandbox events with HMAC-SHA256 signature verification.
* **Contractor Mobile View Preview:** In-month progressive tracker.

---

## 7. Environment Configuration

Add the following to your `.env`:

```ini
# Bachs Sandbox Payment Configuration
BACHS_API_KEY="sk_sandbox_your_bachs_api_key"
BACHS_BASE_URL="https://sandbox-api.bachs.io"
BACHS_WEBHOOK_SECRET="whsec_your_bachs_webhook_secret"
BACHS_TEST_MODE=True
```

---

## 8. Automated Test Suite

Run the full integration test suite with pytest:

```bash
PYTHONPATH=. .venv/bin/pytest
```

**Coverage:**
* Payout formula and mathematical clearance verification logic.
* Contractor stipend & bank details update (Bachs recipient registration).
* Contractor progressive in-month earnings endpoint.
* Agency monthly statement generation and filtering.
* Idempotent payout approval (double-click / duplicate request protection).
* Contractor permission barrier (contractors cannot approve payouts).
* Secure Bachs webhook signature validation and event handling (`payout.paid`, `payout.failed`, duplicate deliveries).
* Bank directory lookup and account resolution.
* CSV export and downloadable receipt generation.
* Held clearance review and clearance approval.
* Agency Payments Dashboard UI endpoint.
* Pre-existing core authentication, check-ins, dump points, reporters, and media endpoints.

*Results: 36 tests passing (100% pass rate).*