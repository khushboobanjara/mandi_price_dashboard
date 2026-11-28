"""HTTP layer for the five-commodity endpoints. Same fixture style as tests/test_dashboard.py."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import get_db
from app.models import MandiPrice
from app.services.validation import make_record_hash
from tests.test_queries_multi import ROWS


@pytest.fixture()
def client(session_factory):
    with session_factory() as s:
        for d, dist, mkt, com, mn, mx, mo in ROWS:
            dt = date.fromisoformat(d)
            s.add(MandiPrice(
                record_hash=make_record_hash(dt, "Rajasthan", dist, mkt, com, "Other", "Local"),
                price_date=dt, state="Rajasthan", district=dist, market=mkt, commodity=com,
                variety="Other", grade="Local", min_price=mn, max_price=mx, modal_price=mo))
        s.commit()

    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_commodities_endpoint_lists_all_five_with_availability(client):
    body = client.get("/api/commodities").json()["commodities"]
    assert [c["name"] for c in body] == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
    assert body[-1]["has_data"] is False and body[0]["current_msp"] == 2585


def test_compare_commodities(client):
    body = client.get("/api/compare/commodities").json()
    assert len(body["rows"]) == 5 and body["newest_date"] == "2026-11-27"
    gram = body["rows"][-1]
    assert gram["has_data"] is False and gram["msp"]["available"] is False
    assert client.get("/api/compare/commodities", params={"date": "2026-11-26"}).status_code == 200


def test_compare_trends_and_districts(client):
    t = client.get("/api/compare/trends").json()
    assert t["dates"] == ["2026-11-26", "2026-11-27"] and len(t["series"]) == 5
    d = client.get("/api/districts/analysis", params={"commodity": "Mustard"}).json()
    assert [r["district"] for r in d["rows"]] == ["Baran", "Jaipur"]
    m = client.get("/api/districts/matrix").json()
    assert {r["district"] for r in m["rows"]} >= {"Jaipur", "Kota"}


def test_new_commodity_filters_are_accepted_with_aliases(client):
    for name in ("Bajra", "Soybean", "Soyabean", "Gram", "chana", "Wheat"):
        assert client.get("/api/prices", params={"commodity": name}).status_code == 200
    assert client.get("/api/prices", params={"commodity": "Soyabean"}).json()["total"] == 1
    assert client.get("/api/prices", params={"commodity": "Gram"}).json()["total"] == 0   # empty, not an error
    assert client.get("/api/prices", params={"commodity": "Rice"}).status_code == 422


def test_msp_endpoints(client):
    o = client.get("/api/msp").json()
    assert len(o["rows"]) == 5 and o["rows"][-1]["status"] == "unavailable"
    b = client.get("/api/msp/breakdown", params={"commodity": "Mustard"}).json()
    assert b["below_count"] == 1 and b["rows"][0]["market"] == "Bassi APMC"
    assert client.get("/api/msp/breakdown").status_code == 422            # commodity required


def test_per_commodity_endpoints_still_require_a_commodity(client):
    assert client.get("/api/districts/analysis").status_code == 422
    assert client.get("/api/trends").status_code == 422
    assert client.get("/api/trends", params={"commodity": "Bajra"}).status_code == 200


def test_kpis_all_five_each_with_msp(client):
    k = client.get("/api/kpis").json()["commodities"]
    assert list(k) == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
    assert k["Bajra"]["msp"]["msp"] == 2900 and k["Gram"] == {"has_data": False}


@pytest.mark.parametrize("kind", ["commodity_summary", "district_analysis", "msp", "history"])
def test_report_csv_downloads(client, kind):
    r = client.get("/api/export/report", params={"kind": kind})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert kind in r.headers["content-disposition"]
    lines = r.text.lstrip("\ufeff").strip().splitlines()
    assert len(lines) >= 2 and lines[0].startswith("commodity,")


def test_commodity_summary_report_contains_no_data_row(client):
    text = client.get("/api/export/report", params={"kind": "commodity_summary"}).text
    assert "Gram (Chana)" in text and "no data" in text
    assert client.get("/api/export/report", params={"kind": "bogus"}).status_code == 422


def test_existing_csv_export_format_is_unchanged(client):
    r = client.get("/api/export/csv", params={"commodity": "Bajra"})
    lines = r.text.strip().splitlines()
    assert lines[0].lstrip("\ufeff") == "date,state,district,market,commodity,variety,grade,min_price,max_price,modal_price"
    assert len(lines) == 3


def test_market_compare_includes_msp(client):
    body = client.get("/api/markets/compare", params={"commodity": "Mustard"}).json()
    assert body["msp"] == 6200
