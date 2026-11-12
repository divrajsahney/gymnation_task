# GymNation Invoices API

A small HTTP API that does three things for gyms in the UAE, Saudi Arabia and Bahrain:

- It stores members under one standard phone format.
- It generates each membership's invoice schedule, with proration and VAT.
- It reconciles the card gateway's monthly file against the invoices that were due.

Built with Python 3.12, [Starlette](https://www.starlette.io/) and [Uvicorn](https://www.uvicorn.org/). All state is kept in memory, so every run starts empty.

## Quick start

```bash
docker build -t app .
docker run -p 8080:8080 app
curl http://localhost:8080/health      # {"status":"ok"}
```

Run the test suite inside Docker:

```bash
docker build --target test .
```

Without Docker:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q                    # unit + API tests
uvicorn app.main:app --port 8080       # start the server
python smoke_test.py                   # end-to-end check against the running server (needs a fresh start)
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/members` | Create a member; the phone is normalised to E.164 |
| GET | `/members/lookup?phone=…[&country=…]` | Find a member by any spelling of their phone |
| POST | `/plans` | Create a plan (monthly price and joining fee, in minor units) |
| POST | `/agreements` | Sign a member up to a plan with a start date and due day |
| GET | `/agreements/{id}/invoices?from=…&to=…` | Invoices due in a date range, computed on request |
| POST | `/reconciliation/runs` | Reconcile one month of gateway rows against expected invoices |
| GET | `/reconciliation/runs/{id}` | Read back a stored reconciliation run |

The extra read endpoints `GET /members/{id}`, `GET /plans/{id}` and `GET /agreements/{id}` are included for debugging.

## Example

```bash
# Member: any phone spelling is accepted and stored as +966551234567
curl -X POST localhost:8080/members -H "content-type: application/json" \
  -d '{"name":"Noura Al Harbi","country":"SA","phone":"055 123 4567"}'

# Plan: 299.00 SAR a month, no joining fee
curl -X POST localhost:8080/plans -H "content-type: application/json" \
  -d '{"id":"anytime-sa","country":"SA","monthly":29900,"joining_fee":0}'

# Agreement: starts 20 Sep, billed on the 1st
curl -X POST localhost:8080/agreements -H "content-type: application/json" \
  -d '{"member_id":"<id>","plan_id":"anytime-sa","start_date":"2026-09-20","due_day":1}'

# Invoices: first is prorated 11/30 -> net 10963, VAT 1644, total 12607 SAR halalas
curl "localhost:8080/agreements/<id>/invoices?from=2026-09-01&to=2026-12-31"
```

## Conventions

- **Money** is always an integer in minor units: fils for AED (1/100), halalas for SAR (1/100), fils for BHD (1/1000). Every invoice carries its currency.
- **Dates** are `YYYY-MM-DD`, with no time or timezone.
- **Errors** always have the shape `{"error": {"code": "...", "message": "..."}}`.
  - Malformed input is `422 VALIDATION`.
  - An unknown id in the URL is `404 NOT_FOUND`.
  - Business rules use their own codes, e.g. `409 PHONE_TAKEN` or `422 INVALID_RANGE`.

## How it works

```
Uvicorn → app/main.py → app/store.py → app/phones.py | app/schedule.py | app/recon.py
           (HTTP)       (state + lock)        (pure business logic)
```

| File | Responsibility |
|---|---|
| `app/main.py` | Routes, JSON parsing, strict input checks, error responses |
| `app/store.py` | In-memory data; every check-then-write runs under one lock |
| `app/phones.py` | Cleaning, classifying and normalising phone numbers |
| `app/schedule.py` | Due-date clamping, proration, half-up rounding, VAT, invoice lists |
| `app/recon.py` | Row validation, invoice matching and verdicts |
| `app/countries.py` | Dial codes, currencies, VAT rates and mobile formats |
| `app/validate.py` | Strict type and format checks |
| `app/errors.py` | The `ApiError` type behind every error response |

Key rules:

- **Phones.** Spaces, hyphens and brackets are removed. The result must be `+` dial code + mobile, dial code + mobile, or a national mobile; anything else is rejected. One member per phone, across every spelling.
- **Schedule.** A due day of 31 clamps to the month's last day without drifting. The first invoice is prorated from the start date to the next due date. Rounding is half-up in minor units, applied exactly once to the prorated amount and once to VAT.
- **Reconciliation.** Each settled row links to the earliest invoice of its agreement whose total is within 1 minor unit. Possible verdicts are `MATCHED`, `DUE_DAY_DRIFT`, `DOUBLE_CHARGE_RISK`, `MISSING_FROM_LEDGER` and `DECLINED`. The result does not depend on row order.

## Concurrency

The server runs one Uvicorn process. Uniqueness rules (phone, plan id) are checked and written inside a single lock, so two simultaneous requests cannot both succeed. The tests verify this with parallel requests.

## More

- [`NOTES.md`](NOTES.md): run instructions, what was skipped, and every assumption made where the brief was ambiguous.
- [`PROMPTS.md`](PROMPTS.md): the AI conversations used to build this.
