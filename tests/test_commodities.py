"""Five-commodity registry + validation rules (pure Python, no DB, no network)."""
from datetime import date

import pytest

from app.commodities import BY_NAME, COMMODITY_NAMES, label_for, normalize_commodity
from app.services.validation import make_record_hash, validate_record

TODAY = date(2026, 11, 27)


def rec(commodity="Wheat", modal=2852, **over):
    r = {"date": "2026-11-26", "state": "Rajasthan", "district": "Baran", "market": "Anta APMC",
         "commodity": commodity, "variety": "Other", "grade": "Local",
         "min_price": modal - 50, "max_price": modal + 50, "modal_price": modal}
    r.update(over)
    return r


def check(r, **kw):
    return validate_record(r, "Rajasthan", TODAY, **kw)


def test_exactly_five_supported_commodities_in_fixed_order():
    assert COMMODITY_NAMES == ("Wheat", "Mustard", "Bajra", "Soybean", "Gram")
    assert label_for("Gram") == "Gram (Chana)"
    assert BY_NAME["Bajra"].season == "kharif" and BY_NAME["Wheat"].season == "rabi"


@pytest.mark.parametrize("raw,expected", [
    ("Wheat", "Wheat"), (" wheat ", "Wheat"), ("MUSTARD", "Mustard"),
    ("Rapeseed & Mustard", "Mustard"),
    ("Bajra", "Bajra"), ("Bajra(Pearl Millet/Cumbu)", "Bajra"), ("bajra (pearl millet/cumbu)", "Bajra"),
    ("Soybean", "Soybean"), ("Soyabean", "Soybean"), ("soya bean", "Soybean"),
    ("Gram", "Gram"), ("Chana", "Gram"), ("Bengal Gram(Gram)(Whole)", "Gram"), ("Gram (Chana)", "Gram"),
])
def test_aliases_map_to_one_canonical_name(raw, expected):
    assert normalize_commodity(raw) == expected


@pytest.mark.parametrize("raw", [
    "Rice", "Maize", "", None, "Gram Dal", "Black Gram (Urd Beans)(Whole)", "Green Gram (Moong)(Whole)",
    "Soyabean Oil",
])
def test_other_commodities_are_not_supported(raw):
    assert normalize_commodity(raw) is None


@pytest.mark.parametrize("name,modal", [("Wheat", 2852), ("Mustard", 6000), ("Bajra", 2700),
                                         ("Soybean", 5400), ("Gram", 5700)])
def test_all_five_commodities_validate(name, modal):
    row, reason = check(rec(name, modal))
    assert reason is None and row["commodity"] == name


def test_api_spelling_is_stored_under_the_canonical_name():
    row, _ = check(rec("Soyabean", 5400))
    assert row["commodity"] == "Soybean"
    row, _ = check(rec("Bajra(Pearl Millet/Cumbu)", 2700))
    assert row["commodity"] == "Bajra"


def test_alias_spellings_produce_the_same_record_hash_so_no_duplicates():
    a, _ = check(rec("Soybean", 5400))
    b, _ = check(rec("Soyabean", 5400))
    assert a["record_hash"] == b["record_hash"]


def test_same_market_and_day_for_different_commodities_are_different_records():
    a, _ = check(rec("Wheat", 2852))
    b, _ = check(rec("Gram", 5700))
    assert a["record_hash"] != b["record_hash"]


def test_existing_wheat_hash_is_unchanged_by_the_upgrade():
    # Rows stored before the upgrade must still match, or they would be re-inserted as duplicates.
    row, _ = check(rec("Wheat", 2852))
    assert row["record_hash"] == make_record_hash(
        date(2026, 11, 26), "Rajasthan", "Baran", "Anta APMC", "Wheat", "Other", "Local")


def test_other_states_are_rejected_for_every_commodity():
    for name, modal in (("Wheat", 2852), ("Bajra", 2700), ("Soybean", 5400), ("Gram", 5700)):
        row, reason = check(rec(name, modal, state="Madhya Pradesh"))
        assert row is None and "unexpected state" in reason


def test_expected_commodity_blocks_cross_commodity_mixing():
    row, reason = check(rec("Wheat", 2852), expected_commodity="Gram")
    assert row is None and "Gram was requested" in reason
    assert check(rec("Gram", 5700), expected_commodity="Gram")[0] is not None


@pytest.mark.parametrize("name,modal", [
    ("Wheat", 28), ("Wheat", 28520), ("Bajra", 27), ("Soybean", 54), ("Gram", 57), ("Mustard", 60),
])
def test_prices_outside_the_plausible_range_are_rejected_as_possible_unit_errors(name, modal):
    row, reason = check(rec(name, modal, min_price=None, max_price=None))
    assert row is None and "plausible" in reason


def test_missing_prices_are_still_kept_as_missing_not_rejected():
    row, reason = check(rec("Bajra", 2700, min_price=None, max_price="NA"))
    assert reason is None and row["min_price"] is None and row["max_price"] is None
