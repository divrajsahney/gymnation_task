"""In-memory state. Every read-check-write happens under one lock so "may not" rules hold under races."""
import threading
import uuid

from . import phones, recon, schedule
from .countries import COUNTRIES
from .errors import ApiError, not_found


def new_id() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.members: dict[str, dict] = {}
        self.member_by_phone: dict[str, str] = {}  # E.164 -> member id
        self.plans: dict[str, dict] = {}
        self.agreements: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}

    # ---- members
    def create_member(self, name: str, country: str, raw_phone: str) -> dict:
        e164 = phones.normalise_for_member(raw_phone, country)
        with self.lock:
            existing = self.member_by_phone.get(e164)
            if existing is not None:
                raise ApiError(409, "PHONE_TAKEN", "Another member already has this phone",
                               existing_member_id=existing)
            member = {"id": new_id(), "name": name, "country": country, "phone": e164}
            self.members[member["id"]] = member
            self.member_by_phone[e164] = member["id"]
            return dict(member)

    def lookup_member(self, raw_phone: str, country: str | None) -> dict:
        e164 = phones.normalise_for_lookup(raw_phone, country)
        with self.lock:
            mid = self.member_by_phone.get(e164)
            if mid is None:
                raise not_found("No member has that phone")
            return dict(self.members[mid])

    def get_member(self, member_id: str) -> dict:
        with self.lock:
            m = self.members.get(member_id)
            if m is None:
                raise not_found("Unknown member")
            return dict(m)

    # ---- plans
    def create_plan(self, plan_id: str, country: str, monthly: int, joining_fee: int) -> dict:
        plan = {"id": plan_id, "country": country, "currency": COUNTRIES[country].currency,
                "monthly": monthly, "joining_fee": joining_fee}
        with self.lock:
            if plan_id in self.plans:
                raise ApiError(409, "PLAN_EXISTS", f"Plan {plan_id} already exists")
            self.plans[plan_id] = plan
            return dict(plan)

    def get_plan(self, plan_id: str) -> dict:
        with self.lock:
            p = self.plans.get(plan_id)
            if p is None:
                raise not_found("Unknown plan")
            return dict(p)

    # ---- agreements
    @staticmethod
    def _public_agreement(a: dict) -> dict:
        return {k: v for k, v in a.items() if not k.startswith("_")}

    def create_agreement(self, member_id: str, plan_id: str, start_date, due_day: int) -> dict:
        with self.lock:
            member = self.members.get(member_id)
            if member is None:
                raise ApiError(422, "UNKNOWN_MEMBER", "Unknown member")
            plan = self.plans.get(plan_id)
            if plan is None:
                raise ApiError(422, "UNKNOWN_PLAN", "Unknown plan")
            if plan["country"] != member["country"]:
                raise ApiError(422, "PLAN_COUNTRY_MISMATCH",
                               "Plan country differs from the member's country")
            anchor = schedule.anchor(start_date, due_day)
            agreement = {"id": new_id(), "member_id": member_id, "plan_id": plan_id,
                         "start_date": start_date.isoformat(), "due_day": due_day,
                         "_anchor": anchor}
            self.agreements[agreement["id"]] = agreement
            return self._public_agreement(agreement)

    def get_agreement(self, agreement_id: str) -> dict:
        with self.lock:
            a = self.agreements.get(agreement_id)
            if a is None:
                raise not_found("Unknown agreement")
            return self._public_agreement(a)

    def invoices(self, agreement_id: str, start, end) -> list[dict]:
        with self.lock:
            a = self.agreements.get(agreement_id)
            if a is None:
                raise not_found("Unknown agreement")
            plan = self.plans[a["plan_id"]]
        return schedule.invoices_between(a["_anchor"], schedule.terms_for(plan), start, end)

    def agreement_exists(self, agreement_id: str) -> bool:
        with self.lock:
            return agreement_id in self.agreements

    # ---- reconciliation
    def create_run(self, month, first, last, rows) -> dict:
        with self.lock:
            agreements = dict(self.agreements)
            plans = dict(self.plans)
        result = recon.run(month, first, last, rows, agreements, plans)
        run = {"id": new_id(), **result}
        with self.lock:
            self.runs[run["id"]] = run
        return run

    def get_run(self, run_id: str) -> dict:
        with self.lock:
            r = self.runs.get(run_id)
            if r is None:
                raise not_found("Unknown reconciliation run")
            return r
