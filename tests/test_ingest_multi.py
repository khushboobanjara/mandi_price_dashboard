"""Refresh pipeline with five commodities: fallbacks, unavailable data, duplicates."""
from sqlalchemy import func, select

from app.models import MandiPrice
from app.services import ingest
from app.services.api_client import ApiError
from tests.test_ingest import FakeClient, count, rec


def five():
    return {
        "Wheat": [rec("Anta APMC", "Wheat", 2852), rec("Baran APMC", "Wheat", 2946)],
        "Mustard": [rec("Anta APMC", "Mustard", 6000)],
        "Bajra": [rec("Jodhpur APMC", "Bajra", 2700, district="Jodhpur")],
        "Soybean": [rec("Kota APMC", "Soybean", 5500, district="Kota")],
        "Gram": [rec("Bundi APMC", "Gram", 5700, district="Bundi")],
    }


def by_commodity(session_factory):
    with session_factory() as s:
        return dict(s.execute(select(MandiPrice.commodity, func.count(MandiPrice.id))
                              .group_by(MandiPrice.commodity)).all())


def test_all_five_commodities_are_fetched_and_stored(session_factory):
    client = FakeClient(five())
    out = ingest.run_refresh("cli", client, session_factory)
    assert out["status"] == "success" and out["records_inserted"] == 6
    assert by_commodity(session_factory) == {"Wheat": 2, "Mustard": 1, "Bajra": 1, "Soybean": 1, "Gram": 1}
    assert client.calls == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]


def test_everything_stored_is_rajasthan_only(session_factory):
    data = five()
    data["Bajra"].append(rec("Indore APMC", "Bajra", 2700, state="Madhya Pradesh"))
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["records_rejected"] == 1
    with session_factory() as s:
        assert {r[0] for r in s.execute(select(MandiPrice.state).distinct())} == {"Rajasthan"}


def test_rerun_with_five_commodities_creates_no_duplicates(session_factory):
    ingest.run_refresh("cli", FakeClient(five()), session_factory)
    out = ingest.run_refresh("scheduler", FakeClient(five()), session_factory)
    assert (out["records_inserted"], out["records_updated"]) == (0, 0)
    assert count(session_factory) == 6


def test_alternate_upstream_spelling_does_not_duplicate_existing_rows(session_factory):
    ingest.run_refresh("cli", FakeClient(five()), session_factory)
    data = five()
    data["Soybean"] = [rec("Kota APMC", "Soyabean", 5500, district="Kota")]   # API spells it differently
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["records_inserted"] == 0 and by_commodity(session_factory)["Soybean"] == 1


def test_fallback_spelling_is_tried_when_first_name_has_no_data(session_factory):
    data = five()
    data["Soybean"] = []                                         # "Soybean" -> nothing
    data["Soyabean"] = [rec("Kota APMC", "Soyabean", 5500, district="Kota")]
    client = FakeClient(data)
    out = ingest.run_refresh("cli", client, session_factory)
    assert out["status"] == "success" and by_commodity(session_factory)["Soybean"] == 1
    assert "Soybean" in client.calls and "Soyabean" in client.calls


def test_fallback_is_tried_when_first_name_returns_only_other_commodities(session_factory):
    data = five()
    data["Gram"] = [rec("Bundi APMC", "Gram Dal", 7000, district="Bundi")]    # not whole gram
    data["Bengal Gram(Gram)(Whole)"] = [rec("Bundi APMC", "Bengal Gram(Gram)(Whole)", 5700, district="Bundi")]
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert by_commodity(session_factory)["Gram"] == 1
    assert out["records_rejected"] == 1


def test_a_commodity_with_no_published_data_is_noted_but_does_not_fail_the_refresh(session_factory):
    data = five()
    data["Bajra"] = []          # off-season / no arrivals
    data["Gram"] = []
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "success"
    assert out["records_inserted"] == 4
    assert "Bajra: no records published" in out["error_message"]
    assert "Gram: no records published" in out["error_message"]
    assert "Bajra" not in by_commodity(session_factory)


def test_api_error_for_one_of_five_is_partial_and_names_the_commodity(session_factory):
    data = five()
    data["Soybean"] = ApiError("request failed: timeout")
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "partial" and out["records_inserted"] == 5
    assert "Soybean: API failure" in out["error_message"]


def test_wrong_commodity_rows_in_a_response_are_never_stored_under_another_crop(session_factory):
    data = five()
    data["Gram"] = [rec("Bundi APMC", "Wheat", 2852, district="Bundi")]    # API ignored the filter
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert "Gram" not in by_commodity(session_factory)
    assert by_commodity(session_factory)["Wheat"] == 2
    assert out["records_rejected"] >= 1


def test_all_five_empty_is_failed_not_success(session_factory):
    out = ingest.run_refresh("cli", FakeClient({}), session_factory)
    assert out["status"] == "failed" and count(session_factory) == 0
