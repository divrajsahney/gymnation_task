"""Invoice schedule. Pure functions, integer arithmetic only."""
import calendar
from dataclasses import dataclass
from datetime import date

from .countries import COUNTRIES
from .errors import validation

MAX_MONTH_INDEX = 9999 * 12 + 11  # December 9999


def round_div(numerator: int, denominator: int) -> int:
    """numerator / denominator rounded half up, for non-negative integers."""
    return (2 * numerator + denominator) // (2 * denominator)


def month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


def due_date_in(index: int, due_day: int) -> date:
    """Due date in the month with this index. The anchor stays due_day; only the date clamps."""
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(due_day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Terms:
    monthly: int
    joining_fee: int
    vat_percent: int
    currency: str


@dataclass(frozen=True)
class Anchor:
    start: date
    due_day: int
    n_index: int  # month index of N, the first due date strictly after start
    n: date
    p: date


def anchor(start: date, due_day: int) -> Anchor:
    """Compute N and P. Raises VALIDATION if they fall outside the supported calendar (years 1..9999)."""
    i = month_index(start)
    try:
        if due_date_in(i, due_day) > start:
            n_index = i
        else:
            n_index = i + 1
        if n_index - 1 < 12 or n_index > MAX_MONTH_INDEX:  # P must be in year >= 1
            raise ValueError
        n = due_date_in(n_index, due_day)
        p = due_date_in(n_index - 1, due_day)
    except ValueError:
        raise validation("start_date is outside the supported date range")
    return Anchor(start, due_day, n_index, n, p)


def _amounts(net: int, terms: Terms) -> dict:
    vat = round_div(net * terms.vat_percent, 100)
    return {"net": net, "vat": vat, "total": net + vat, "currency": terms.currency}


def first_invoice(a: Anchor, terms: Terms) -> dict:
    days = (a.n - a.start).days
    cycle = (a.n - a.p).days
    net = round_div(terms.monthly * days, cycle) + terms.joining_fee
    return {
        "invoice_no": 1,
        "due_date": a.start.isoformat(),
        "kind": "FIRST",
        "proration": {"days": days, "cycle_days": cycle},
        **_amounts(net, terms),
    }


def monthly_invoice(a: Anchor, terms: Terms, index: int) -> dict:
    return {
        "invoice_no": index - a.n_index + 2,
        "due_date": due_date_in(index, a.due_day).isoformat(),
        "kind": "MONTHLY",
        "proration": None,
        **_amounts(terms.monthly, terms),
    }


def invoices_between(a: Anchor, terms: Terms, start: date, end: date) -> list[dict]:
    """All invoices with start <= due_date <= end (inclusive), in schedule order."""
    out = []
    if start <= a.start <= end:
        out.append(first_invoice(a, terms))
    i = max(a.n_index, month_index(start))
    while i <= MAX_MONTH_INDEX:
        d = due_date_in(i, a.due_day)
        if d > end:
            break
        if d >= start:
            out.append(monthly_invoice(a, terms, i))
        i += 1
    return out


def terms_for(plan: dict) -> Terms:
    c = COUNTRIES[plan["country"]]
    return Terms(plan["monthly"], plan["joining_fee"], c.vat_percent, c.currency)
