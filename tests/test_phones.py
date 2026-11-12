import pytest

from app import phones
from app.errors import ApiError


def code_of(fn, *args):
    with pytest.raises(ApiError) as e:
        fn(*args)
    return e.value.code


@pytest.mark.parametrize("raw,country,expected", [
    ("+966551234567", "SA", "+966551234567"),
    ("966551234567", "SA", "+966551234567"),
    ("0551234567", "SA", "+966551234567"),
    ("055 123 4567", "SA", "+966551234567"),
    ("(055) 123-4567", "SA", "+966551234567"),
    ("0501234567", "AE", "+971501234567"),
    ("+971 50 123 4567", "AE", "+971501234567"),
    ("31234567", "BH", "+97331234567"),
    ("+973 3123 4567", "BH", "+97331234567"),
    ("97331234567", "BH", "+97331234567"),
    # International number from another country is fine on a member (foreign SIM)
    ("+97331234567", "SA", "+97331234567"),
    ("971501234567", "SA", "+971501234567"),
])
def test_member_normalisation(raw, country, expected):
    assert phones.normalise_for_member(raw, country) == expected


@pytest.mark.parametrize("raw,country", [
    ("00966551234567", "SA"),   # 00 prefix
    ("+0551234567", "SA"),      # + with national
    ("0112345678", "SA"),       # landline
    ("055123456", "SA"),        # too short
    ("05512345678", "SA"),      # too long
    ("+96655123456", "SA"),     # intl too short
    ("+9665512345678", "SA"),   # intl too long
    ("+966451234567", "SA"),    # intl not a mobile
    ("+97341234567", "BH"),     # BH not starting 3
    ("031234567", "BH"),        # BH with trunk zero
    ("31234567", "SA"),         # BH national read in SA
    ("0551234567", "BH"),       # SA national read in BH
    ("055.123.4567", "SA"),     # dots are not removed
    ("055_123_4567", "SA"),
    ("+966+551234567", "SA"),   # second +
    ("966551234567+", "SA"),
    ("", "SA"),
    ("+", "SA"),
    ("abc", "SA"),
    ("٠٥٥١٢٣٤٥٦٧", "SA"),       # Arabic-Indic digits
    ("+1 555 123 4567", "SA"),  # other country
])
def test_member_invalid(raw, country):
    assert code_of(phones.normalise_for_member, raw, country) == "INVALID_PHONE"


def test_lookup_rules():
    assert phones.normalise_for_lookup("966551234567", None) == "+966551234567"
    assert phones.normalise_for_lookup("+966551234567", "SA") == "+966551234567"
    assert phones.normalise_for_lookup("055 123 4567", "SA") == "+966551234567"
    assert phones.normalise_for_lookup("055 123 4567", "AE") == "+971551234567"
    assert code_of(phones.normalise_for_lookup, "0551234567", None) == "PHONE_NEEDS_COUNTRY"
    assert code_of(phones.normalise_for_lookup, "31234567", None) == "PHONE_NEEDS_COUNTRY"
    assert code_of(phones.normalise_for_lookup, "31234567", "SA") == "INVALID_PHONE"
    assert code_of(phones.normalise_for_lookup, "0551234567", "BH") == "INVALID_PHONE"
    assert code_of(phones.normalise_for_lookup, "+966551234567", "AE") == "PHONE_COUNTRY_MISMATCH"
    assert code_of(phones.normalise_for_lookup, "97331234567", "SA") == "PHONE_COUNTRY_MISMATCH"
    assert code_of(phones.normalise_for_lookup, "00966551234567", None) == "INVALID_PHONE"
    assert code_of(phones.normalise_for_lookup, "00966551234567", "SA") == "INVALID_PHONE"
