import random

from .conftest import err, make_agreement, make_member, make_plan


def setup_two(client):
    """SA agreement due 1st (Oct total 34385) and BH agreement due 1st (Oct total 26950)."""
    sa = make_member(client, "Noura", "SA", "0551234567")
    bh = make_member(client, "Ali", "BH", "31234567")
    make_plan(client, "anytime-sa", "SA", 29900, 0)
    make_plan(client, "anytime-bh", "BH", 24500, 0)
    a_sa = make_agreement(client, sa["id"], "anytime-sa", "2026-09-20", 1)
    a_bh = make_agreement(client, bh["id"], "anytime-bh", "2026-09-15", 1)
    return a_sa["id"], a_bh["id"]


def row(txn, ag, amount, currency, status="SETTLED", on="2026-10-01"):
    return {"gateway_txn_id": txn, "agreement_id": ag, "amount": amount,
            "currency": currency, "status": status, "attempted_on": on}


def test_spec_example(client):
    sa, bh = setup_two(client)
    r = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": [
        row("T-88121", sa, 34385, "SAR"),
        row("T-88122", bh, 26950, "BHD", "DECLINED", "2026-10-02")]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["month"] == "2026-10"
    assert body["summary"] == {"MATCHED": 1, "DUE_DAY_DRIFT": 0, "DOUBLE_CHARGE_RISK": 0,
                               "MISSING_FROM_LEDGER": 0, "DECLINED": 1}
    assert body["rows"] == [
        {"gateway_txn_id": "T-88121", "verdict": "MATCHED", "invoice": {"agreement_id": sa, "invoice_no": 2}},
        {"gateway_txn_id": "T-88122", "verdict": "DECLINED", "invoice": None}]
    assert body["unmatched_invoices"] == [
        {"agreement_id": bh, "invoice_no": 2, "due_date": "2026-10-01", "total": 26950, "currency": "BHD"}]
    got = client.get(f"/reconciliation/runs/{body['id']}")
    assert got.status_code == 200 and got.json() == body


def test_verdicts(client):
    sa, bh = setup_two(client)
    rows = [
        row("drift", bh, 26951, "BHD", on="2026-10-03"),      # within 1 minor unit, other day
        row("dup1", sa, 34385, "SAR"),
        row("dup2", sa, 34384, "SAR", on="2026-10-05"),
        row("miss-amt", sa, 99999, "SAR"),
        row("miss-ag", "ghost", 100, "AED"),
    ]
    body = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": rows}).json()
    v = {r["gateway_txn_id"]: r for r in body["rows"]}
    assert v["drift"]["verdict"] == "DUE_DAY_DRIFT"
    assert v["dup1"]["verdict"] == v["dup2"]["verdict"] == "DOUBLE_CHARGE_RISK"
    assert v["dup1"]["invoice"] == {"agreement_id": sa, "invoice_no": 2}
    assert v["miss-amt"]["verdict"] == "MISSING_FROM_LEDGER" and v["miss-amt"]["invoice"] is None
    assert v["miss-ag"]["verdict"] == "MISSING_FROM_LEDGER"
    assert body["summary"] == {"MATCHED": 0, "DUE_DAY_DRIFT": 1, "DOUBLE_CHARGE_RISK": 2,
                               "MISSING_FROM_LEDGER": 2, "DECLINED": 0}
    assert body["unmatched_invoices"] == []
    assert [r["gateway_txn_id"] for r in body["rows"]] == [r["gateway_txn_id"] for r in rows]


def test_earliest_candidate_and_two_invoices_in_month(client):
    m = make_member(client, "A", "AE", "0501234567")
    make_plan(client, "ae", "AE", 24900, 0)
    # Start 5 Sep, due 20 -> FIRST on 5 Sep (prorated) and MONTHLY on 20 Sep, both in September.
    a = make_agreement(client, m["id"], "ae", "2026-09-05", 20)
    full = 24900 + 1245
    body = client.post("/reconciliation/runs", json={"month": "2026-09", "rows": [
        row("t1", a["id"], full, "AED", on="2026-09-20")]}).json()
    assert body["rows"][0]["invoice"]["invoice_no"] == 2
    assert body["rows"][0]["verdict"] == "MATCHED"
    # FIRST invoice (5 Sep) is unmatched and listed first by due date
    assert [(u["invoice_no"], u["due_date"]) for u in body["unmatched_invoices"]] == [(1, "2026-09-05")]


def test_earliest_due_date_wins_when_totals_equal(client):
    m = make_member(client, "A", "AE", "0501234567")
    # monthly 1 fils: FIRST on 1 Sep = round(1 * 29/31) = 1, MONTHLY on 30 Sep = 1. Same total.
    make_plan(client, "tiny", "AE", 1, 0)
    a = make_agreement(client, m["id"], "tiny", "2026-09-01", 30)
    body = client.post("/reconciliation/runs", json={"month": "2026-09", "rows": [
        row("t1", a["id"], 1, "AED", on="2026-09-30"),
        row("t2", a["id"], 2, "AED", on="2026-09-30")]}).json()
    # Both rows pick the earlier invoice (1 Sep); already-linked invoices still count.
    assert body["rows"][0]["invoice"] == {"agreement_id": a["id"], "invoice_no": 1}
    assert body["rows"][1]["invoice"] == {"agreement_id": a["id"], "invoice_no": 1}
    assert {r["verdict"] for r in body["rows"]} == {"DOUBLE_CHARGE_RISK"}
    assert [u["invoice_no"] for u in body["unmatched_invoices"]] == [2]


def test_order_independence(client):
    sa, bh = setup_two(client)
    rows = [row("a", sa, 34385, "SAR"), row("b", sa, 34386, "SAR", on="2026-10-09"),
            row("c", bh, 26950, "BHD", on="2026-10-04"), row("d", bh, 26950, "BHD", "DECLINED"),
            row("e", "ghost", 1, "SAR")]
    ref = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": rows}).json()
    ref_by = {r["gateway_txn_id"]: r for r in ref["rows"]}
    for seed in range(5):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)
        out = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": shuffled}).json()
        assert out["summary"] == ref["summary"]
        assert out["unmatched_invoices"] == ref["unmatched_invoices"]
        assert {r["gateway_txn_id"]: r for r in out["rows"]} == ref_by
        assert [r["gateway_txn_id"] for r in out["rows"]] == [r["gateway_txn_id"] for r in shuffled]


def test_declined_only_invoice_is_unmatched(client):
    sa, bh = setup_two(client)
    body = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": [
        row("x", sa, 34385, "SAR", "DECLINED")]}).json()
    assert {u["agreement_id"] for u in body["unmatched_invoices"]} == {sa, bh}
    # sorted by due_date then agreement_id
    ids = [u["agreement_id"] for u in body["unmatched_invoices"]]
    assert ids == sorted(ids)


def test_invalid_rows(client):
    sa, bh = setup_two(client)
    r = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": [
        row("T1", sa, 34385, "SAR"),
        row("T1", sa, 34385, "SAR", on="2026-11-01"),
        row("T2", sa, 34385, "AED", "DECLINED"),
        row("T3", "ghost", 5, "BHD"),
        row("T4", bh, 26950, "BHD")]})
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "INVALID_ROWS"
    got = sorted((x["gateway_txn_id"], x["code"]) for x in e["errors"])
    assert got == sorted([("T1", "DUPLICATE_TXN"), ("T1", "DUPLICATE_TXN"),
                          ("T1", "ROW_OUTSIDE_MONTH"), ("T2", "CURRENCY_MISMATCH")])


def test_recon_validation(client):
    sa, _ = setup_two(client)
    good = row("t", sa, 34385, "SAR")
    for body in [
        {"rows": [good]},
        {"month": "2026-13", "rows": [good]},
        {"month": "2026-1", "rows": [good]},
        {"month": "2026-10"},
        {"month": "2026-10", "rows": {}},
        {"month": "2026-10", "rows": [{**good, "amount": 0}]},
        {"month": "2026-10", "rows": [{**good, "amount": 1.0}]},
        {"month": "2026-10", "rows": [{**good, "status": "PENDING"}]},
        {"month": "2026-10", "rows": [{**good, "attempted_on": "2026-10-32"}]},
        {"month": "2026-10", "rows": [{k: v for k, v in good.items() if k != "agreement_id"}]},
    ]:
        r = client.post("/reconciliation/runs", json=body)
        assert r.status_code == 422 and err(r) == "VALIDATION", body


def test_empty_rows_and_unknown_run(client):
    r = client.post("/reconciliation/runs", json={"month": "2026-10", "rows": []})
    assert r.status_code == 201
    assert r.json()["summary"] == {"MATCHED": 0, "DUE_DAY_DRIFT": 0, "DOUBLE_CHARGE_RISK": 0,
                                   "MISSING_FROM_LEDGER": 0, "DECLINED": 0}
    assert err(client.get("/reconciliation/runs/nope")) == "NOT_FOUND"
