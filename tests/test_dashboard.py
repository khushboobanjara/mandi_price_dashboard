from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import get_db
from app.models import FetchLog, MandiPrice
from app.services.ingest import utcnow
from app.services.validation import make_record_hash

ROWS = [  # date, district, market, commodity, min, max, modal
    ("2026-11-20", "Jaipur", "Bassi APMC", "Wheat", 2500, 2700, 2600),
    ("2026-11-26", "Jaipur", "Bassi APMC", "Wheat", 2700, 2900, 2800),
    ("2026-11-26", "Baran", "Anta APMC", "Wheat", 2800, 3000, 2900),
    ("2026-11-26", "Bundi", "Bundi APMC", "Wheat", 2600, 2800, 2700),
    ("2026-11-27", "Jaipur", "Bassi APMC", "Wheat", 2780, 2980, 2940),
    ("2026-11-27", "Swai Madhopur", "Sawai Madhopur APMC", "Wheat", 2640, 2770, 2702),
    ("2026-11-27", "Jaipur", "Bassi APMC", "Mustard", 9180, 9780, 9480),
]


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


def test_kpis_wheat_like_for_like(client):
    w = client.get("/api/kpis", params={"commodity": "Wheat"}).json()["commodities"]["Wheat"]
    assert w["latest_date"] == "2026-11-27" and w["previous_date"] == "2026-11-26"
    assert w["week_compare_date"] == "2026-11-20"
    s = w["summary"]
    assert (s["avg_modal"], s["min_price"], s["max_price"], s["markets_reporting"]) == (2821.0, 2640.0, 2980.0, 2)
    assert s["highest_modal_market"]["market"] == "Bassi APMC"
    assert s["lowest_modal_market"]["market"] == "Sawai Madhopur APMC"
    assert w["change_vs_previous"]["pct_change"] == 5.0
    assert w["change_vs_previous"]["markets_compared"] == 1
    assert w["change_vs_week"]["pct_change"] == 13.08


def test_kpis_without_commodity_returns_both_and_freshness(client):
    body = client.get("/api/kpis").json()
    assert set(body["commodities"]) == {"Wheat", "Mustard"}
    m = body["commodities"]["Mustard"]
    assert m["previous_date"] is None and m["change_vs_previous"]["pct_change"] is None
    assert body["freshness"]["latest_price_date"] == "2026-11-27"


def test_kpis_respect_date_to_and_market_filters(client):
    w = client.get("/api/kpis", params={"commodity": "Wheat", "date_to": "2026-11-26"}).json()["commodities"]["Wheat"]
    assert w["latest_date"] == "2026-11-26" and w["previous_date"] == "2026-11-20"
    assert w["change_vs_previous"]["pct_change"] == 7.69
    assert w["change_vs_week"]["pct_change"] is None
    b = client.get("/api/kpis", params={"commodity": "Wheat", "market": "Bassi APMC"}).json()["commodities"]["Wheat"]
    assert b["summary"]["avg_modal"] == 2940.0


def test_kpis_no_data_for_filter(client):
    out = client.get("/api/kpis", params={"commodity": "Mustard", "district": "Baran"}).json()
    assert out["commodities"]["Mustard"] == {"has_data": False}


def test_trends(client):
    body = client.get("/api/trends", params={"commodity": "Wheat"}).json()
    pts = body["series"][0]["points"]
    assert [p["date"] for p in pts] == ["2026-11-20", "2026-11-26", "2026-11-27"]
    assert [p["avg_modal"] for p in pts] == [2600.0, 2800.0, 2821.0]
    assert [p["markets_reporting"] for p in pts] == [1, 3, 2]
    short = client.get("/api/trends", params={"commodity": "Wheat", "date_from": "2026-11-26"}).json()
    assert len(short["series"][0]["points"]) == 2


def test_trends_grouped_by_market(client):
    body = client.get("/api/trends", params={"commodity": "Wheat", "group_by": "market", "top": 1}).json()
    assert len(body["series"]) == 1 and body["series"][0]["name"] == "Bassi APMC"
    assert len(body["series"][0]["points"]) == 3


def test_market_comparison(client):
    body = client.get("/api/markets/compare", params={"commodity": "Wheat"}).json()
    assert body["date"] == "2026-11-27" and body["average_modal"] == 2821.0
    first = body["rows"][0]
    assert first["market"] == "Bassi APMC" and first["spread"] == 200.0 and first["diff_vs_avg_pct"] == 4.22
    older = client.get("/api/markets/compare", params={"commodity": "Wheat", "date": "2026-11-26"}).json()
    assert len(older["rows"]) == 3 and older["rows"][0]["market"] == "Anta APMC"
    by_district = client.get("/api/markets/compare", params={"commodity": "Wheat", "level": "district"}).json()
    assert by_district["rows"][0]["market"] is None and by_district["rows"][0]["district"] == "Jaipur"


def test_prices_table_pagination_and_sorting(client):
    body = client.get("/api/prices", params={"commodity": "Wheat", "page_size": 2}).json()
    assert body["total"] == 6 and body["pages"] == 3 and len(body["items"]) == 2
    assert all(i["date"] == "2026-11-27" for i in body["items"])
    asc = client.get("/api/prices", params={"commodity": "Wheat", "sort_by": "modal_price", "order": "asc"}).json()
    assert asc["items"][0]["modal_price"] == 2600.0
    assert client.get("/api/prices", params={"commodity": "Mustard"}).json()["total"] == 1


def test_csv_export(client):
    r = client.get("/api/export/csv", params={"commodity": "Mustard"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].lstrip("\ufeff") == "date,state,district,market,commodity,variety,grade,min_price,max_price,modal_price"
    assert len(lines) == 2 and "Bassi APMC" in lines[1] and "9480" in lines[1]


def test_filter_options_cascade(client):
    body = client.get("/api/filters").json()
    assert body["commodities"] == ["Mustard", "Wheat"]
    assert body["date_range"] == {"min": "2026-11-20", "max": "2026-11-27"}
    only = client.get("/api/filters", params={"commodity": "Mustard"}).json()
    assert only["districts"] == ["Jaipur"]
    jaipur = client.get("/api/filters", params={"district": "Jaipur"}).json()
    assert {m["market"] for m in jaipur["markets"]} == {"Bassi APMC"}


def test_freshness_states(client, session_factory):
    assert client.get("/api/freshness").json()["status"] == "never"
    with session_factory() as s:
        s.add(FetchLog(trigger_source="scheduler", status="success", started_at=utcnow(), finished_at=utcnow()))
        s.commit()
    f = client.get("/api/freshness").json()
    assert f["status"] == "fresh" and f["last_refresh_status"] == "success"
    assert f["latest_price_date"] == "2026-11-27" and f["total_records"] == 7


def test_freshness_reports_failed_last_refresh(client, session_factory):
    with session_factory() as s:
        s.add(FetchLog(trigger_source="scheduler", status="failed", started_at=utcnow(),
                       finished_at=utcnow(), error_message="Wheat: API failure - 502"))
        s.commit()
    f = client.get("/api/freshness").json()
    assert f["last_refresh_status"] == "failed" and "502" in f["last_refresh_error"]


def test_validation_errors(client):
    assert client.get("/api/prices", params={"commodity": "Rice"}).status_code == 422
    assert client.get("/api/prices", params={"date_from": "2026-11-27", "date_to": "2026-11-01"}).status_code == 422
    assert client.get("/api/trends").status_code == 422
    assert client.get("/api/markets/compare").status_code == 422
    assert client.get("/api/prices", params={"page_size": 5000}).status_code == 422
    assert client.get("/api/prices", params={"commodity": "wheat"}).status_code == 200  # case-insensitive
