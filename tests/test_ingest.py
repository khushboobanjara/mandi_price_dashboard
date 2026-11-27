from sqlalchemy import func, select

from app.models import FetchLog, MandiPrice
from app.services import ingest
from app.services.api_client import ApiError, FetchResult


def rec(market="Anta APMC", commodity="Wheat", modal=2852, date="2026-11-26", **over):
    r = {"date": date, "state": "Rajasthan", "district": "Baran", "market": market,
         "commodity": commodity, "variety": "Other", "grade": "Local",
         "min_price": 2800, "max_price": 2905, "modal_price": modal}
    r.update(over)
    return r


class FakeClient:
    def __init__(self, data):
        self.data = data  # commodity -> list | Exception

    def fetch(self, state, commodity):
        item = self.data[commodity]
        if isinstance(item, Exception):
            raise item
        return FetchResult(records=list(item))


def count(session_factory):
    with session_factory() as s:
        return s.scalar(select(func.count(MandiPrice.id)))


def good_data():
    return {"Wheat": [rec("Anta APMC"), rec("Baran APMC")],
            "Mustard": [rec("Anta APMC", "Mustard", 6000)]}


def test_first_run_inserts_all(session_factory):
    out = ingest.run_refresh("cli", FakeClient(good_data()), session_factory)
    assert out["status"] == "success"
    assert (out["records_fetched"], out["records_inserted"], out["records_updated"]) == (3, 3, 0)
    assert count(session_factory) == 3


def test_second_run_creates_no_duplicates(session_factory):
    ingest.run_refresh("cli", FakeClient(good_data()), session_factory)
    out = ingest.run_refresh("scheduler", FakeClient(good_data()), session_factory)
    assert (out["records_inserted"], out["records_updated"]) == (0, 0)
    assert count(session_factory) == 3
    with session_factory() as s:
        assert s.scalar(select(func.count(FetchLog.id))) == 2


def test_changed_price_updates_existing_row(session_factory):
    ingest.run_refresh("cli", FakeClient(good_data()), session_factory)
    data = good_data()
    data["Wheat"][0] = rec("Anta APMC", modal=2900)
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert (out["records_inserted"], out["records_updated"]) == (0, 1)
    with session_factory() as s:
        row = s.execute(select(MandiPrice).where(MandiPrice.market == "Anta APMC",
                                                 MandiPrice.commodity == "Wheat")).scalar_one()
        assert float(row.modal_price) == 2900.0


def test_new_date_is_stored_as_history(session_factory):
    ingest.run_refresh("cli", FakeClient(good_data()), session_factory)
    data = good_data()
    data["Wheat"] = [rec("Anta APMC", date="2026-11-27")]
    ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert count(session_factory) == 4


def test_duplicates_inside_one_api_batch_collapse(session_factory):
    data = {"Wheat": [rec(), rec()], "Mustard": [rec(commodity="Mustard")]}
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["records_inserted"] == 2 and count(session_factory) == 2


def test_invalid_rows_are_rejected_and_reported(session_factory):
    data = good_data()
    data["Wheat"].append(rec("Bad APMC", modal="abc"))
    data["Wheat"].append(rec("Neg APMC", min_price=-1))
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "success"
    assert out["records_rejected"] == 2 and out["records_inserted"] == 3
    assert "rejected" in out["error_message"]


def test_one_commodity_api_failure_is_partial(session_factory):
    data = good_data()
    data["Mustard"] = ApiError("request failed: timeout")
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "partial" and out["records_inserted"] == 2
    assert "Mustard" in out["error_message"]


def test_all_api_failures_mark_failed_and_store_nothing(session_factory):
    data = {"Wheat": ApiError("down"), "Mustard": ApiError("down")}
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "failed" and count(session_factory) == 0
    assert out["finished_at"] is not None


def test_empty_api_answer_is_not_success(session_factory):
    out = ingest.run_refresh("cli", FakeClient({"Wheat": [], "Mustard": []}), session_factory)
    assert out["status"] == "failed"


def test_all_rows_invalid_is_failed(session_factory):
    data = {"Wheat": [rec(modal="x")], "Mustard": [rec(commodity="Mustard", modal="x")]}
    out = ingest.run_refresh("cli", FakeClient(data), session_factory)
    assert out["status"] == "failed" and out["records_rejected"] == 2


def test_concurrent_refresh_is_refused(session_factory):
    assert ingest._refresh_lock.acquire(blocking=False)
    try:
        assert ingest.is_refresh_running()
        assert ingest.run_refresh("manual", FakeClient(good_data()), session_factory) is None
    finally:
        ingest._refresh_lock.release()
    assert not ingest.is_refresh_running()
