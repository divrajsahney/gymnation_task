"""HTTP layer. Thin: parse + validate input, call the store, shape output."""
import json
import logging

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import recon
from .errors import ApiError, not_found, validation
from .store import Store
from .validate import country_code, parse_date, req_date, req_int, req_str, require_object

log = logging.getLogger("app")
store = Store()

MAX_RANGE_DAYS = 366


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


async def read_json(request: Request):
    raw = await request.body()
    if not raw:
        raise validation("Request body must be JSON")
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        raise validation("Request body is not valid JSON")


def ok(body, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status)


# ---------------------------------------------------------------- health
async def health(request: Request):
    return ok({"status": "ok"})


# ---------------------------------------------------------------- members
async def create_member(request: Request):
    body = require_object(await read_json(request))
    name = req_str(body, "name").strip()
    if not 1 <= len(name) <= 120:
        raise validation("name must be 1 to 120 characters after trimming")
    if "country" not in body:
        raise validation("country is required")
    country = country_code(body["country"])
    phone = req_str(body, "phone")
    return ok(store.create_member(name, country, phone), 201)


async def lookup_member(request: Request):
    params = request.query_params
    phone = params.get("phone")
    if phone is None:
        raise validation("phone is required")
    country = None
    if "country" in params:
        country = country_code(params.get("country"))
    return ok(store.lookup_member(phone, country))


async def get_member(request: Request):
    return ok(store.get_member(request.path_params["id"]))


# ---------------------------------------------------------------- plans
async def create_plan(request: Request):
    body = require_object(await read_json(request))
    plan_id = req_str(body, "id", non_empty=True)
    if "country" not in body:
        raise validation("country is required")
    country = country_code(body["country"])
    monthly = req_int(body, "monthly", min_value=1)
    joining_fee = req_int(body, "joining_fee", min_value=0)
    return ok(store.create_plan(plan_id, country, monthly, joining_fee), 201)


async def get_plan(request: Request):
    return ok(store.get_plan(request.path_params["id"]))


# ---------------------------------------------------------------- agreements
async def create_agreement(request: Request):
    body = require_object(await read_json(request))
    member_id = req_str(body, "member_id")
    plan_id = req_str(body, "plan_id")
    start_date = req_date(body, "start_date")
    due_day = req_int(body, "due_day", min_value=1, max_value=31)
    return ok(store.create_agreement(member_id, plan_id, start_date, due_day), 201)


async def get_agreement(request: Request):
    return ok(store.get_agreement(request.path_params["id"]))


async def agreement_invoices(request: Request):
    agreement_id = request.path_params["id"]
    if not store.agreement_exists(agreement_id):
        raise not_found("Unknown agreement")
    params = request.query_params
    if "from" not in params:
        raise validation("from is required")
    if "to" not in params:
        raise validation("to is required")
    start = parse_date(params.get("from"), "from")
    end = parse_date(params.get("to"), "to")
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise ApiError(422, "INVALID_RANGE", "to must be on or after from, and at most 366 days after it")
    return ok(store.invoices(agreement_id, start, end))


# ---------------------------------------------------------------- reconciliation
async def create_run(request: Request):
    month, first, last, rows = recon.parse_request(await read_json(request))
    return ok(store.create_run(month, first, last, rows), 201)


async def get_run(request: Request):
    return ok(store.get_run(request.path_params["id"]))


# ---------------------------------------------------------------- errors
async def api_error(request: Request, exc: ApiError):
    return JSONResponse(exc.body(), status_code=exc.status)


async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 404:
        err = not_found("Not found")
        return JSONResponse(err.body(), status_code=404)
    if exc.status_code == 405:
        return JSONResponse({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed"}},
                            status_code=405)
    return JSONResponse({"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
                        status_code=exc.status_code)


async def server_error(request: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL", "message": "Internal server error"}},
                        status_code=500)


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/members", create_member, methods=["POST"]),
    Route("/members/lookup", lookup_member, methods=["GET"]),
    Route("/members/{id}", get_member, methods=["GET"]),
    Route("/plans", create_plan, methods=["POST"]),
    Route("/plans/{id}", get_plan, methods=["GET"]),
    Route("/agreements", create_agreement, methods=["POST"]),
    Route("/agreements/{id}", get_agreement, methods=["GET"]),
    Route("/agreements/{id}/invoices", agreement_invoices, methods=["GET"]),
    Route("/reconciliation/runs", create_run, methods=["POST"]),
    Route("/reconciliation/runs/{id}", get_run, methods=["GET"]),
]

app = Starlette(
    routes=routes,
    exception_handlers={ApiError: api_error, HTTPException: http_error, Exception: server_error},
)
