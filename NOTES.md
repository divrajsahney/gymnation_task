# GymNation invoices API

Python 3.12, Starlette + Uvicorn. Everything is in memory and each run starts empty. There are no runtime network calls.

## Run

```bash
docker build -t app .
docker run -p 8080:8080 app        # GET http://localhost:8080/health -> 200
docker build --target test .       # runs pytest inside the image
```

Without Docker:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Layout

| File | What it does |
|---|---|
| `app/countries.py` | Country table: dial code, currency, VAT %, mobile shapes |
| `app/phones.py` | Cleaning and classifying phones, E.164 normalisation, lookup rules |
| `app/schedule.py` | Due-date clamping, N/P anchor, proration, rounding, invoices in a range (pure functions) |
| `app/recon.py` | Reconciliation request parsing, row rules, matching and verdicts (pure function) |
| `app/store.py` | In-memory state; every check-then-write runs under one lock |
| `app/main.py` | HTTP layer: routes, strict input checks, error mapping |
| `app/validate.py` | Strict type checks (bools and floats are not integers) |

Money uses integer arithmetic only. `round_div(a, b) = (2a + b) // (2b)` is half-up rounding for non-negative values. It is applied once to the prorated amount and once to VAT (`net * pct / 100`).

## Concurrency

Uvicorn runs one process. Every rule that says something "may not" happen (phone uniqueness, plan id uniqueness) is a check-and-insert inside a single `threading.Lock`. Tests fire 20 parallel creates with mixed spellings of one number and 10 parallel creates of one plan id, and expect exactly one 201 each time.

## What I skipped

- Persistence. The brief says each run starts empty.
- List endpoints, update and delete endpoints, pagination, auth.
- Extra read endpoints (`GET /members/{id}`, `/plans/{id}`, `/agreements/{id}`) exist for debugging only and are not in the brief.

## Assumptions

- Validation order: body shape and types first (`VALIDATION`), then business rules in the order the brief lists them.
- Unknown JSON fields are ignored.
- Integers must be JSON integers. `true`, `1.0` and `"1"` are all `VALIDATION`.
- Name length is counted in Unicode code points after Python `str.strip()`.
- Phone cleaning removes only ASCII space, `-`, `(` and `)`. Tabs, dots and other characters cause `INVALID_PHONE`.
- Only ASCII digits 0-9 are accepted. Arabic-Indic digits cause `INVALID_PHONE`.
- A phone that is not a string, or is missing, is `VALIDATION`. A string that does not parse is `INVALID_PHONE`.
- On lookup, a missing `phone` parameter or a `country` value other than AE/SA/BH is `VALIDATION`.
- A raw `+` in a query string decodes to a space. It is then cleaned away and the number is read as international without `+`, so it still works.
- On lookup, a national number with a `country` that does not fit that country's shape is `INVALID_PHONE`.
- `POST /agreements`: when both member and plan are unknown, `UNKNOWN_MEMBER` is reported.
- Plan `id` must be a non-empty string. `joining_fee` is required.
- `GET /agreements/{id}/invoices`: an unknown agreement is 404 before query parameters are checked.
- Range of 366 days means `to - from <= 366` days.
- A start date whose N or P would fall outside years 1-9999 is `VALIDATION`.
- Reconciliation: a row `currency` other than AED/SAR/BHD is `VALIDATION`. Empty `gateway_txn_id` or `agreement_id` is `VALIDATION`. `rows: []` is allowed.
- `DUPLICATE_TXN` gives one error entry per occurring row. `ROW_OUTSIDE_MONTH` and `CURRENCY_MISMATCH` are checked on declined rows too.
- When two candidates share a due date, the lower `invoice_no` wins. Within one agreement this cannot happen, because due dates strictly increase.
- Expected invoices are computed against the agreements that exist when the run is created. A stored run is a frozen snapshot and is not recomputed on GET.
- Unknown routes return 404 `NOT_FOUND` and wrong methods return 405 `METHOD_NOT_ALLOWED`, both in the standard error format.
