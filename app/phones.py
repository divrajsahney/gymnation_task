"""Phone normalisation to E.164 (+<dial><subscriber>)."""
import re
from dataclasses import dataclass

from .countries import COUNTRIES
from .errors import ApiError

_CLEAN_RE = re.compile(r"[ \-()]")
_SHAPE_RE = re.compile(r"\+?[0-9]+")  # [0-9], not \d: \d also matches non-ASCII digits


def invalid(msg: str = "Not a valid mobile number") -> ApiError:
    return ApiError(422, "INVALID_PHONE", msg)


@dataclass(frozen=True)
class Parsed:
    kind: str                 # "intl" or "national"
    digits: str               # cleaned digits, without "+"
    country: str | None = None  # set for intl
    e164: str | None = None     # set for intl


def clean(raw: str) -> str:
    s = _CLEAN_RE.sub("", raw)
    if not _SHAPE_RE.fullmatch(s):
        raise invalid("Phone may contain only digits, spaces, hyphens, brackets and one leading +")
    return s


def _match_intl(digits: str) -> Parsed | None:
    for c in COUNTRIES.values():
        if digits.startswith(c.dial) and c.subscriber_re.fullmatch(digits[len(c.dial):]):
            return Parsed("intl", digits, c.code, "+" + digits)
    return None


def parse(raw: str) -> Parsed:
    """Classify a phone as international or national. Raises INVALID_PHONE otherwise."""
    s = clean(raw)
    if s.startswith("+"):
        p = _match_intl(s[1:])
        if p is None:
            raise invalid()
        return p
    p = _match_intl(s)
    if p is not None:
        return p
    if any(c.national_re.fullmatch(s) for c in COUNTRIES.values()):
        return Parsed("national", s)
    raise invalid()


def national_to_e164(digits: str, country: str) -> str:
    c = COUNTRIES[country]
    if not c.national_re.fullmatch(digits):
        raise invalid(f"Not a valid {country} mobile number")
    return "+" + c.dial + digits[len(c.trunk):]


def normalise_for_member(raw: str, member_country: str) -> str:
    """POST /members: national numbers read in the member's country; intl may be any country."""
    p = parse(raw)
    if p.kind == "intl":
        return p.e164
    return national_to_e164(p.digits, member_country)


def normalise_for_lookup(raw: str, country: str | None) -> str:
    p = parse(raw)
    if p.kind == "intl":
        if country is not None and country != p.country:
            raise ApiError(422, "PHONE_COUNTRY_MISMATCH",
                           f"Number is from {p.country}, not {country}")
        return p.e164
    if country is None:
        raise ApiError(422, "PHONE_NEEDS_COUNTRY", "A national number needs a country parameter")
    return national_to_e164(p.digits, country)
