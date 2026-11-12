"""Strict input checks. Anything malformed is 422 VALIDATION.

Booleans are rejected where integers are expected (in Python bool is an int subclass),
and floats are rejected even when they are whole numbers.
"""
import re
from datetime import date

from .countries import COUNTRIES
from .errors import validation

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MONTH_RE = re.compile(r"([0-9]{4})-([0-9]{2})")


def require_object(body, what: str = "body") -> dict:
    if not isinstance(body, dict):
        raise validation(f"{what} must be a JSON object")
    return body


def req_str(obj: dict, key: str, *, non_empty: bool = False) -> str:
    if key not in obj:
        raise validation(f"{key} is required")
    v = obj[key]
    if not isinstance(v, str):
        raise validation(f"{key} must be a string")
    if non_empty and v == "":
        raise validation(f"{key} must not be empty")
    return v


def req_int(obj: dict, key: str, *, min_value=None, max_value=None) -> int:
    if key not in obj:
        raise validation(f"{key} is required")
    v = obj[key]
    if type(v) is not int:  # excludes bool and float
        raise validation(f"{key} must be an integer")
    if min_value is not None and v < min_value:
        raise validation(f"{key} must be >= {min_value}")
    if max_value is not None and v > max_value:
        raise validation(f"{key} must be <= {max_value}")
    return v


def parse_date(value, name: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise validation(f"{name} must be a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise validation(f"{name} is not a valid date")


def req_date(obj: dict, key: str) -> date:
    if key not in obj:
        raise validation(f"{key} is required")
    return parse_date(obj[key], key)


def parse_month(value, name: str = "month") -> tuple[int, int]:
    if not isinstance(value, str):
        raise validation(f"{name} must be a string in YYYY-MM format")
    m = _MONTH_RE.fullmatch(value)
    if not m:
        raise validation(f"{name} must be in YYYY-MM format")
    year, month = int(m.group(1)), int(m.group(2))
    if year < 1 or not 1 <= month <= 12:
        raise validation(f"{name} is not a valid month")
    return year, month


def country_code(value, name: str = "country") -> str:
    if not isinstance(value, str) or value not in COUNTRIES:
        raise validation(f"{name} must be one of AE, SA, BH")
    return value
