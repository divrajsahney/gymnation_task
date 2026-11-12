"""Country reference data from the brief."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    code: str
    dial: str
    currency: str
    vat_percent: int
    # National mobile, e.g. 0551234567 (AE/SA) or 31234567 (BH)
    national_re: re.Pattern
    # Subscriber part after the dial code, e.g. 551234567 / 31234567
    subscriber_re: re.Pattern
    # Digits to strip from a national number to get the subscriber part
    trunk: str


COUNTRIES: dict[str, Country] = {
    "AE": Country("AE", "971", "AED", 5, re.compile(r"05[0-9]{8}"), re.compile(r"5[0-9]{8}"), "0"),
    "SA": Country("SA", "966", "SAR", 15, re.compile(r"05[0-9]{8}"), re.compile(r"5[0-9]{8}"), "0"),
    "BH": Country("BH", "973", "BHD", 10, re.compile(r"3[0-9]{7}"), re.compile(r"3[0-9]{7}"), ""),
}

CURRENCIES = {c.currency for c in COUNTRIES.values()}
