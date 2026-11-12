# AI conversations

- **Tool:** Claude (claude.ai), model Claude Opus 5.5
- **Sessions:** one conversation, from first look at the brief to submission
- **Format:** my prompts verbatim (long terminal output trimmed), each followed by a summary of Claude's reply and what it changed in the code

---

### 1. Reading the job page

> https://forms.gymnation.com/f/hAh5gfoF8s7MZgJEE-c6f8KE?src=basim
> can you access this page

Claude fetched the page and summarised the role, the three-part task, the technical contract and the form fields. It noted that it had only seen a summary of the spec, so I attached the full brief next.

### 2. Planning

> (attached the task brief as a text file)
> This is the task brief, give me steps to build this

Claude gave a step-by-step build plan:
- **Stack:** Python with strict validation, because default framework 422s don't match the required error shape and Pydantic coerces `"299"` to `299`.
- **Contract:** the Dockerfile must have a `test` stage, and the final stage must come last in the file.
- **Phones:** exact regex patterns for the three accepted spellings.
- **Money:** integer half-up rounding, `(2a + b) // (2b)`, applied exactly twice per invoice.
- **Due dates:** clamping that never carries the clamped date into the next month.
- **First invoice:** the N/P anchor.
- **Reconciliation:** the order of rules, and per-row linking, which makes the result independent of row order.
- **Concurrency:** the lock design and a test for it.

### 3. Building

> Write the whole codebase and give me the zip

Claude wrote:
- **App:** `app/` (errors, countries, validate, phones, schedule, recon, store, main)
- **Tests:** 71 pytest tests
- **Docker:** a three-stage Dockerfile
- **Docs:** NOTES.md

It then ran the tests and smoke-tested a live server with curl. That run included 30 parallel `POST /members` with the same phone, which gave 1×201 and 29×409.

Bugs it found and fixed in its own tests:
- **Wrong `invoice_no`.** An expectation said invoice 8 for March 2027 with a 20 Sep 2026 start. Counting Sep 20, Oct, Nov, Dec, Jan, Feb, Mar gives 7.
- **Missing tie.** A tie-break test didn't actually produce a tie. It was rewritten to use a 1-fils plan, where the FIRST and MONTHLY invoices fall in the same month with equal totals. That checks that the earliest due date wins and that already-linked invoices still count.

### 4. Learning

> What is starlette?

Starlette is a lightweight web framework that FastAPI is built on, and Uvicorn is the server that runs it. Starlette was chosen over FastAPI because FastAPI's automatic validation coerces types and returns the wrong error shape.

### 5. Running and verifying

> create a test python script to confirm end to end workflow

Claude added `smoke_test.py`, a standard-library script that checks a running server against the brief's worked examples. It also gave Docker and non-Docker run instructions for Windows.

> (pytest error collecting `smoke_test.py`: `unknown url type: '-q/health'`)

pytest collects `*_test.py` files, so it imported the smoke script as if it were a test. Claude added `pytest.ini` with `testpaths = tests` and copied it in the Dockerfile's test stage.

### 6. Submitting

> give me a readme.md and an updated prompts.md

Claude wrote: 
 - README.md: overview, quick start, endpoints, an example, conventions, code layout and concurrency.
 - PROMPTS.md: This file