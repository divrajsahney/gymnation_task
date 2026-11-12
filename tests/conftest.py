import pytest
from starlette.testclient import TestClient

import app.main as main
from app.store import Store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "store", Store())
    with TestClient(main.app) as c:
        yield c


def make_member(client, name="Noura", country="SA", phone="0551234567"):
    r = client.post("/members", json={"name": name, "country": country, "phone": phone})
    assert r.status_code == 201, r.text
    return r.json()


def make_plan(client, plan_id="anytime-sa", country="SA", monthly=29900, joining_fee=0):
    r = client.post("/plans", json={"id": plan_id, "country": country,
                                    "monthly": monthly, "joining_fee": joining_fee})
    assert r.status_code == 201, r.text
    return r.json()


def make_agreement(client, member_id, plan_id, start_date, due_day):
    r = client.post("/agreements", json={"member_id": member_id, "plan_id": plan_id,
                                         "start_date": start_date, "due_day": due_day})
    assert r.status_code == 201, r.text
    return r.json()


def err(r):
    return r.json()["error"]["code"]
