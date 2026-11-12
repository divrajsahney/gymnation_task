"""End-to-end check against a running server. Standard library only.

Usage:  python smoke_test.py                 (defaults to http://localhost:8080)
        python smoke_test.py http://host:port
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
passed = failed = 0


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


try:
    status, _ = call("GET", "/health")
except OSError as e:
    sys.exit(f"Cannot reach {BASE}: {e}\nIs the app running?")
check("health returns 200", status == 200)

print("Part 1: members and phones")
s, m = call("POST", "/members", {"name": " Noura Al Harbi ", "country": "SA", "phone": "055 123 4567"})
check("create member -> 201, phone normalised, name trimmed",
      s == 201 and m["phone"] == "+966551234567" and m["name"] == "Noura Al Harbi")
for q in ["966551234567", "%2B966551234567", "055%20123%204567&country=SA"]:
    s, b = call("GET", f"/members/lookup?phone={q}")
    check(f"lookup {q} finds the member", s == 200 and b["id"] == m["id"])
s, b = call("GET", "/members/lookup?phone=0551234567")
check("national number without country -> PHONE_NEEDS_COUNTRY", b["error"]["code"] == "PHONE_NEEDS_COUNTRY")
s, b = call("POST", "/members", {"name": "Copy", "country": "SA", "phone": "+966551234567"})
check("same phone again -> 409 PHONE_TAKEN with existing id",
      s == 409 and b["error"]["existing_member_id"] == m["id"])
s, b = call("POST", "/members", {"name": "X", "country": "SA", "phone": "00966551234567"})
check("00 prefix -> INVALID_PHONE", b["error"]["code"] == "INVALID_PHONE")

print("Part 2: plans and invoices")
s, p = call("POST", "/plans", {"id": "anytime-sa", "country": "SA", "monthly": 29900, "joining_fee": 0})
check("create plan -> 201 with currency SAR", s == 201 and p["currency"] == "SAR")
s, a = call("POST", "/agreements", {"member_id": m["id"], "plan_id": "anytime-sa",
                                    "start_date": "2026-09-20", "due_day": 1})
check("create agreement -> 201", s == 201)
s, inv = call("GET", f"/agreements/{a['id']}/invoices?from=2026-09-01&to=2026-12-31")
check("4 invoices Sep-Dec", s == 200 and len(inv) == 4)
check("invoice 1: 10963 + 1644 = 12607 (worked example)",
      inv[0]["net"] == 10963 and inv[0]["vat"] == 1644 and inv[0]["total"] == 12607)
check("invoice 2: due 2026-10-01, total 34385",
      inv[1]["due_date"] == "2026-10-01" and inv[1]["total"] == 34385)

ae = call("POST", "/members", {"name": "Omar", "country": "AE", "phone": "0501234567"})[1]
call("POST", "/plans", {"id": "anytime-ae", "country": "AE", "monthly": 24900, "joining_fee": 9900})
a2 = call("POST", "/agreements", {"member_id": ae["id"], "plan_id": "anytime-ae",
                                  "start_date": "2026-09-05", "due_day": 20})[1]
inv2 = call("GET", f"/agreements/{a2['id']}/invoices?from=2026-09-01&to=2026-09-30")[1]
check("AE worked example: two September invoices, first total 23045",
      len(inv2) == 2 and inv2[0]["total"] == 23045)

print("Part 3: reconciliation")
s, run = call("POST", "/reconciliation/runs", {"month": "2026-10", "rows": [
    {"gateway_txn_id": "T-1", "agreement_id": a["id"], "amount": 34385,
     "currency": "SAR", "status": "SETTLED", "attempted_on": "2026-10-01"},
    {"gateway_txn_id": "T-2", "agreement_id": "does-not-exist", "amount": 500,
     "currency": "SAR", "status": "SETTLED", "attempted_on": "2026-10-03"}]})
check("run -> 201", s == 201)
check("T-1 MATCHED to invoice 2, T-2 MISSING_FROM_LEDGER",
      run["rows"][0]["verdict"] == "MATCHED" and run["rows"][0]["invoice"]["invoice_no"] == 2
      and run["rows"][1]["verdict"] == "MISSING_FROM_LEDGER")
check("AE October invoice listed as unmatched",
      [u["agreement_id"] for u in run["unmatched_invoices"]] == [a2["id"]])
s, again = call("GET", f"/reconciliation/runs/{run['id']}")
check("run can be read back unchanged", s == 200 and again == run)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
