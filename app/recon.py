"""Gateway reconciliation. Pure function over a snapshot of agreements/plans."""
import calendar
from collections import Counter
from datetime import date

from . import schedule
from .countries import CURRENCIES
from .errors import ApiError, validation
from .validate import parse_month, require_object, req_date, req_int, req_str

VERDICTS = ["MATCHED", "DUE_DAY_DRIFT", "DOUBLE_CHARGE_RISK", "MISSING_FROM_LEDGER", "DECLINED"]


def parse_request(body) -> tuple[str, date, date, list[dict]]:
    body = require_object(body)
    if "month" not in body:
        raise validation("month is required")
    year, month = parse_month(body["month"])
    if "rows" not in body:
        raise validation("rows is required")
    raw_rows = body["rows"]
    if not isinstance(raw_rows, list):
        raise validation("rows must be an array")
    rows = []
    for i, r in enumerate(raw_rows):
        r = require_object(r, f"rows[{i}]")
        status = req_str(r, "status")
        if status not in ("SETTLED", "DECLINED"):
            raise validation(f"rows[{i}].status must be SETTLED or DECLINED")
        currency = req_str(r, "currency")
        if currency not in CURRENCIES:
            raise validation(f"rows[{i}].currency must be one of AED, SAR, BHD")
        rows.append({
            "gateway_txn_id": req_str(r, "gateway_txn_id", non_empty=True),
            "agreement_id": req_str(r, "agreement_id", non_empty=True),
            "amount": req_int(r, "amount", min_value=1),
            "currency": currency,
            "status": status,
            "attempted_on": req_date(r, "attempted_on"),
        })
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return f"{year:04d}-{month:02d}", first, last, rows


def run(month: str, first: date, last: date, rows: list[dict],
        agreements: dict, plans: dict) -> dict:
    # --- Row-level rules: the whole request fails if any row breaks one.
    counts = Counter(r["gateway_txn_id"] for r in rows)
    errors = []
    for r in rows:
        tid = r["gateway_txn_id"]
        if counts[tid] > 1:
            errors.append({"gateway_txn_id": tid, "code": "DUPLICATE_TXN"})
        if not first <= r["attempted_on"] <= last:
            errors.append({"gateway_txn_id": tid, "code": "ROW_OUTSIDE_MONTH"})
        ag = agreements.get(r["agreement_id"])
        if ag is not None and schedule.terms_for(plans[ag["plan_id"]]).currency != r["currency"]:
            errors.append({"gateway_txn_id": tid, "code": "CURRENCY_MISMATCH"})
    if errors:
        raise ApiError(422, "INVALID_ROWS", "One or more rows are invalid", errors=errors)

    # --- Expected invoices: every agreement's invoices due in the month.
    expected: dict[str, list[dict]] = {}
    for ag_id, ag in agreements.items():
        terms = schedule.terms_for(plans[ag["plan_id"]])
        expected[ag_id] = schedule.invoices_between(ag["_anchor"], terms, first, last)

    # --- Link each settled row to a candidate. Independent of other rows => order-independent.
    links: list[tuple[str, int] | None] = []
    for r in rows:
        link = None
        if r["status"] == "SETTLED":
            candidates = [inv for inv in expected.get(r["agreement_id"], [])
                          if abs(inv["total"] - r["amount"]) <= 1]
            if candidates:
                best = min(candidates, key=lambda inv: (inv["due_date"], inv["invoice_no"]))
                link = (r["agreement_id"], best["invoice_no"])
        links.append(link)

    per_invoice = Counter(l for l in links if l is not None)
    due_by_key = {(ag_id, inv["invoice_no"]): inv
                  for ag_id, invs in expected.items() for inv in invs}

    out_rows = []
    summary = {v: 0 for v in VERDICTS}
    for r, link in zip(rows, links):
        if r["status"] == "DECLINED":
            verdict = "DECLINED"
        elif link is None:
            verdict = "MISSING_FROM_LEDGER"
        elif per_invoice[link] > 1:
            verdict = "DOUBLE_CHARGE_RISK"
        elif r["attempted_on"].isoformat() == due_by_key[link]["due_date"]:
            verdict = "MATCHED"
        else:
            verdict = "DUE_DAY_DRIFT"
        summary[verdict] += 1
        out_rows.append({
            "gateway_txn_id": r["gateway_txn_id"],
            "verdict": verdict,
            "invoice": {"agreement_id": link[0], "invoice_no": link[1]} if link else None,
        })

    unmatched = [
        {"agreement_id": ag_id, "invoice_no": inv["invoice_no"], "due_date": inv["due_date"],
         "total": inv["total"], "currency": inv["currency"]}
        for (ag_id, no), inv in due_by_key.items() if (ag_id, no) not in per_invoice
    ]
    unmatched.sort(key=lambda u: (u["due_date"], u["agreement_id"], u["invoice_no"]))

    return {"month": month, "summary": summary, "rows": out_rows, "unmatched_invoices": unmatched}
