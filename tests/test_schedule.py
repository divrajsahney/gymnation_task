from datetime import date

import pytest

from app import schedule
from app.errors import ApiError
from app.schedule import Terms, anchor, invoices_between, round_div

SA = lambda monthly, fee=0: Terms(monthly, fee, 15, "SAR")
AE = lambda monthly, fee=0: Terms(monthly, fee, 5, "AED")
BH = lambda monthly, fee=0: Terms(monthly, fee, 10, "BHD")


def inv(start, due_day, terms, frm, to):
    return invoices_between(anchor(date.fromisoformat(start), due_day), terms,
                            date.fromisoformat(frm), date.fromisoformat(to))


def test_round_div_half_up():
    assert round_div(5, 2) == 3      # 2.5 -> 3
    assert round_div(7, 2) == 4      # 3.5 -> 4
    assert round_div(10, 4) == 3     # 2.5 -> 3
    assert round_div(9, 4) == 2      # 2.25 -> 2
    assert round_div(11, 4) == 3     # 2.75 -> 3
    assert round_div(0, 7) == 0


def test_worked_example_sa():
    out = inv("2026-09-20", 1, SA(29900), "2026-09-01", "2026-12-31")
    assert out[0] == {"invoice_no": 1, "due_date": "2026-09-20", "kind": "FIRST",
                      "proration": {"days": 11, "cycle_days": 30},
                      "net": 10963, "vat": 1644, "total": 12607, "currency": "SAR"}
    assert out[1] == {"invoice_no": 2, "due_date": "2026-10-01", "kind": "MONTHLY",
                      "proration": None, "net": 29900, "vat": 4485, "total": 34385,
                      "currency": "SAR"}
    assert [i["due_date"] for i in out] == ["2026-09-20", "2026-10-01", "2026-11-01", "2026-12-01"]
    assert [i["invoice_no"] for i in out] == [1, 2, 3, 4]


def test_worked_example_ae_joining_fee():
    out = inv("2026-09-05", 20, AE(24900, 9900), "2026-09-01", "2026-09-30")
    assert len(out) == 2  # September has two invoices
    first = out[0]
    assert first["proration"] == {"days": 15, "cycle_days": 31}
    assert (first["net"], first["vat"], first["total"]) == (21948, 1097, 23045)
    assert out[1]["due_date"] == "2026-09-20" and out[1]["invoice_no"] == 2


def test_due_day_31_clamps_without_drifting():
    out = inv("2027-01-31", 31, SA(10000), "2027-01-01", "2027-06-30")
    assert [i["due_date"] for i in out] == [
        "2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30", "2027-05-31", "2027-06-30"]
    # Start is a due date -> full price
    assert out[0]["proration"] == {"days": 28, "cycle_days": 28}
    assert out[0]["net"] == 10000


def test_leap_year_february():
    out = inv("2028-01-31", 31, SA(10000), "2028-02-01", "2028-03-31")
    assert [i["due_date"] for i in out] == ["2028-02-29", "2028-03-31"]


def test_start_on_due_date_full_price():
    out = inv("2026-10-01", 1, SA(29900), "2026-10-01", "2026-11-30")
    assert out[0]["proration"] == {"days": 31, "cycle_days": 31}
    assert out[0]["net"] == 29900
    assert out[1]["due_date"] == "2026-11-01"


def test_one_day_before_due_31():
    out = inv("2027-01-30", 31, SA(31000), "2027-01-01", "2027-02-28")
    assert out[0]["proration"] == {"days": 1, "cycle_days": 31}
    assert out[0]["net"] == 1000
    assert out[1]["due_date"] == "2027-01-31"
    assert out[2]["due_date"] == "2027-02-28"


def test_start_on_clamped_feb_date():
    # Due day 30, start 28 Feb 2027 which is the clamped due date -> full price, N = 30 Mar
    out = inv("2027-02-28", 30, SA(10000), "2027-02-01", "2027-03-31")
    assert out[0]["proration"] == {"days": 30, "cycle_days": 30}
    assert out[1]["due_date"] == "2027-03-30"


def test_bhd_three_decimal_vat_not_rounded_to_major():
    out = inv("2026-10-01", 1, BH(5790), "2026-10-01", "2026-10-31")
    assert (out[0]["net"], out[0]["vat"], out[0]["total"]) == (5790, 579, 6369)


def test_invoice_no_does_not_restart_in_range():
    out = inv("2026-09-20", 1, SA(29900), "2027-03-01", "2027-04-30")
    assert [(i["invoice_no"], i["due_date"]) for i in out] == [(7, "2027-03-01"), (8, "2027-04-01")]


def test_range_before_start_is_empty():
    assert inv("2026-09-20", 1, SA(29900), "2026-01-01", "2026-09-19") == []


def test_vat_rounds_once_on_full_net_including_fee():
    # prorated 12048.39 -> 12048; +9900 = 21948; VAT 5% = 1097.4 -> 1097 (not 602.4+495)
    out = inv("2026-09-05", 20, AE(24900, 9900), "2026-09-05", "2026-09-05")
    assert out[0]["vat"] == 1097


def test_date_extremes_rejected():
    with pytest.raises(ApiError):
        anchor(date(1, 1, 1), 5)
    with pytest.raises(ApiError):
        anchor(date(9999, 12, 31), 31)
    anchor(date(9999, 12, 1), 31)  # N = 31 Dec 9999 is fine
