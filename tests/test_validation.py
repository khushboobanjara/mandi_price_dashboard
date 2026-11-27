from datetime import date

from app.services.validation import make_record_hash, validate_record

TODAY = date(2026, 11, 27)


def good(**over):
    rec = {"date": "2026-11-26", "state": "Rajasthan", "district": "Baran",
           "market": "Anta APMC", "commodity": "Wheat", "variety": "Other",
           "grade": "Local", "min_price": 2800, "max_price": 2905, "modal_price": 2852}
    rec.update(over)
    return rec


def check(rec):
    return validate_record(rec, "Rajasthan", TODAY)


def test_valid_record_is_cleaned_and_hashed():
    row, reason = check(good(market="  Anta   APMC "))
    assert reason is None
    assert row["market"] == "Anta APMC"
    assert row["price_date"] == date(2026, 11, 26)
    assert float(row["modal_price"]) == 2852.0
    assert len(row["record_hash"]) == 64


def test_hash_ignores_case_and_is_stable():
    a, _ = check(good())
    b, _ = check(good(market="ANTA APMC", district="baran"))
    assert a["record_hash"] == b["record_hash"]
    assert a["record_hash"] == make_record_hash(date(2026, 11, 26), "Rajasthan", "Baran",
                                                "Anta APMC", "Wheat", "Other", "Local")


def test_variety_and_grade_distinguish_records():
    a, _ = check(good(variety="Other"))
    b, _ = check(good(variety="147 Average"))
    assert a["record_hash"] != b["record_hash"]


def test_missing_price_value_is_kept_as_none():
    row, reason = check(good(min_price=None, max_price="NA"))
    assert reason is None and row["min_price"] is None and row["max_price"] is None


def test_alternate_date_format_and_commodity_case():
    row, _ = check(good(date="26/11/2026", commodity="mustard"))
    assert row["price_date"] == date(2026, 11, 26) and row["commodity"] == "Mustard"


def test_rejections():
    cases = {
        "missing date": good(date=None),
        "unparseable date": good(date="yesterday"),
        "out of range": good(date="2030-01-01"),
        "unexpected state": good(state="Punjab"),
        "missing district": good(district=" "),
        "missing market": good(market=""),
        "unsupported commodity": good(commodity="Rice"),
        "not numeric": good(modal_price="abc"),
        "negative": good(min_price=-5),
        "no prices": good(min_price=None, max_price=None, modal_price=None),
        "greater than": good(min_price=3000, max_price=2900),
    }
    for expected, rec in cases.items():
        row, reason = check(rec)
        assert row is None, expected
        assert expected in reason, (expected, reason)


def test_non_dict_rejected():
    assert check("oops")[0] is None
