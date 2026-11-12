import threading

from .conftest import err, make_agreement, make_member, make_plan


def test_health(client):
    assert client.get("/health").status_code == 200


def test_unknown_route_uses_error_format(client):
    r = client.get("/nope")
    assert r.status_code == 404 and err(r) == "NOT_FOUND"


# ------------------------------------------------------------- members
def test_create_member_normalises(client):
    r = client.post("/members", json={"name": "  Noura Al Harbi ", "country": "SA",
                                      "phone": "055 123 4567"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Noura Al Harbi"
    assert body["phone"] == "+966551234567"
    assert body["country"] == "SA" and body["id"]


def test_lookup_all_spellings(client):
    m = make_member(client)
    for url in ["/members/lookup?phone=966551234567",
                "/members/lookup?phone=%2B966551234567",
                "/members/lookup?phone=055%20123%204567&country=SA",
                "/members/lookup?phone=+966551234567"]:  # raw + decodes to space; still valid
        r = client.get(url)
        assert r.status_code == 200, url
        assert r.json() == m


def test_lookup_errors(client):
    make_member(client)
    assert err(client.get("/members/lookup?phone=0551234567")) == "PHONE_NEEDS_COUNTRY"
    assert err(client.get("/members/lookup?phone=%2B966551234567&country=AE")) == "PHONE_COUNTRY_MISMATCH"
    r = client.get("/members/lookup?phone=%2B966559999999")
    assert r.status_code == 404 and err(r) == "NOT_FOUND"
    r = client.get("/members/lookup")
    assert r.status_code == 422 and err(r) == "VALIDATION"
    assert err(client.get("/members/lookup?phone=0551234567&country=XX")) == "VALIDATION"
    assert err(client.get("/members/lookup?phone=00966551234567")) == "INVALID_PHONE"


def test_member_validation(client):
    bad = [
        {"country": "SA", "phone": "0551234567"},
        {"name": "   ", "country": "SA", "phone": "0551234567"},
        {"name": "x" * 121, "country": "SA", "phone": "0551234567"},
        {"name": 5, "country": "SA", "phone": "0551234567"},
        {"name": "A", "country": "US", "phone": "0551234567"},
        {"name": "A", "country": "SA"},
        {"name": "A", "country": "SA", "phone": 551234567},
    ]
    for body in bad:
        r = client.post("/members", json=body)
        assert r.status_code == 422 and err(r) == "VALIDATION", body
    r = client.post("/members", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and err(r) == "VALIDATION"
    r = client.post("/members", json=[1, 2])
    assert err(r) == "VALIDATION"
    assert client.post("/members", json={"name": "x" * 120, "country": "SA",
                                         "phone": "0551234567"}).status_code == 201


def test_member_bad_phone(client):
    r = client.post("/members", json={"name": "A", "country": "SA", "phone": "0031234567"})
    assert r.status_code == 422 and err(r) == "INVALID_PHONE"
    r = client.post("/members", json={"name": "A", "country": "BH", "phone": "0551234567"})
    assert err(r) == "INVALID_PHONE"


def test_phone_taken_any_spelling(client):
    m = make_member(client, phone="+966551234567")
    r = client.post("/members", json={"name": "B", "country": "SA", "phone": "0551234567"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PHONE_TAKEN"
    assert r.json()["error"]["existing_member_id"] == m["id"]


def test_phone_taken_race(client):
    spellings = ["+966551234567", "966551234567", "0551234567", "055 123 4567"] * 5
    results = []
    barrier = threading.Barrier(len(spellings))

    def go(p):
        barrier.wait()
        r = client.post("/members", json={"name": "Racer", "country": "SA", "phone": p})
        results.append(r.status_code)

    threads = [threading.Thread(target=go, args=(p,)) for p in spellings]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(201) == 1
    assert results.count(409) == len(spellings) - 1


# ------------------------------------------------------------- plans
def test_plan_create_and_duplicate(client):
    p = make_plan(client)
    assert p == {"id": "anytime-sa", "country": "SA", "currency": "SAR",
                 "monthly": 29900, "joining_fee": 0}
    r = client.post("/plans", json={"id": "anytime-sa", "country": "SA", "monthly": 1, "joining_fee": 0})
    assert r.status_code == 409 and err(r) == "PLAN_EXISTS"


def test_plan_validation(client):
    base = {"id": "p", "country": "AE", "monthly": 100, "joining_fee": 0}
    for patch in [{"monthly": 0}, {"monthly": -1}, {"monthly": 1.5}, {"monthly": 100.0},
                  {"monthly": "100"}, {"monthly": True}, {"joining_fee": -1},
                  {"joining_fee": None}, {"country": "KW"}, {"id": 7}, {"id": ""}]:
        r = client.post("/plans", json={**base, **patch})
        assert r.status_code == 422 and err(r) == "VALIDATION", patch
    for missing in base:
        body = {k: v for k, v in base.items() if k != missing}
        assert err(client.post("/plans", json=body)) == "VALIDATION", missing


def test_plan_race(client):
    results = []
    barrier = threading.Barrier(10)

    def go():
        barrier.wait()
        r = client.post("/plans", json={"id": "race", "country": "AE", "monthly": 1, "joining_fee": 0})
        results.append(r.status_code)

    threads = [threading.Thread(target=go) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201] + [409] * 9


# ------------------------------------------------------------- agreements
def test_agreement_and_invoices(client):
    m = make_member(client)
    make_plan(client)
    a = make_agreement(client, m["id"], "anytime-sa", "2026-09-20", 1)
    assert a["member_id"] == m["id"] and a["start_date"] == "2026-09-20" and a["due_day"] == 1
    r = client.get(f"/agreements/{a['id']}/invoices?from=2026-09-01&to=2026-12-31")
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 4
    assert out[0]["total"] == 12607 and out[1]["total"] == 34385


def test_agreement_errors(client):
    m = make_member(client)
    make_plan(client)
    make_plan(client, "ae", "AE", 1000, 0)
    def post(**kw):
        body = {"member_id": m["id"], "plan_id": "anytime-sa", "start_date": "2026-09-20", "due_day": 1}
        body.update(kw)
        return client.post("/agreements", json=body)
    assert err(post(member_id="nope")) == "UNKNOWN_MEMBER"
    assert post(member_id="nope").status_code == 422
    assert err(post(plan_id="nope")) == "UNKNOWN_PLAN"
    assert err(post(plan_id="ae")) == "PLAN_COUNTRY_MISMATCH"
    for bad in [{"due_day": 0}, {"due_day": 32}, {"due_day": "1"}, {"start_date": "2026-02-30"},
                {"start_date": "2026-9-1"}, {"start_date": "2026-09-20T00:00:00"}, {"start_date": 20260920}]:
        assert err(post(**bad)) == "VALIDATION", bad


def test_invoice_range_errors(client):
    m = make_member(client)
    make_plan(client)
    a = make_agreement(client, m["id"], "anytime-sa", "2026-09-20", 1)
    base = f"/agreements/{a['id']}/invoices"
    assert err(client.get(f"{base}?from=2026-09-01")) == "VALIDATION"
    assert err(client.get(f"{base}?to=2026-09-01")) == "VALIDATION"
    assert err(client.get(f"{base}?from=2026-13-01&to=2026-12-01")) == "VALIDATION"
    assert err(client.get(f"{base}?from=2026-09-02&to=2026-09-01")) == "INVALID_RANGE"
    assert err(client.get(f"{base}?from=2026-01-01&to=2027-01-03")) == "INVALID_RANGE"  # 367 days
    assert client.get(f"{base}?from=2026-01-01&to=2027-01-02").status_code == 200   # 366 days
    assert client.get(f"{base}?from=2026-09-01&to=2026-09-01").json() == []
    r = client.get("/agreements/nope/invoices?from=2026-09-01&to=2026-12-31")
    assert r.status_code == 404 and err(r) == "NOT_FOUND"
