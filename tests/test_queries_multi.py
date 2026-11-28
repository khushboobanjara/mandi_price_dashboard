"""Multi-commodity analytics (queries layer, SQLite). No web framework needed."""
from datetime import date

import pytest

from app.models import MandiPrice
from app.services import queries
from app.services.queries import Filters
from app.services.validation import make_record_hash

ROWS = [  # date, district, market, commodity, min, max, modal
    ("2026-11-26", "Jaipur", "Bassi APMC", "Wheat", 2700, 2900, 2800),
    ("2026-11-26", "Baran", "Anta APMC", "Wheat", 2800, 3000, 2900),
    ("2026-11-26", "Bundi", "Bundi APMC", "Wheat", 2600, 2800, 2700),
    ("2026-11-27", "Jaipur", "Bassi APMC", "Wheat", 2780, 2980, 2940),
    ("2026-11-27", "Swai Madhopur", "Sawai Madhopur APMC", "Wheat", 2640, 2770, 2702),
    ("2026-11-26", "Jaipur", "Bassi APMC", "Mustard", 5900, 6300, 6100),
    ("2026-11-27", "Jaipur", "Bassi APMC", "Mustard", 5800, 6200, 6000),
    ("2026-11-27", "Baran", "Anta APMC", "Mustard", 6200, 6600, 6400),
    ("2026-11-27", "Jodhpur", "Jodhpur APMC", "Bajra", 2600, 2800, 2700),
    ("2026-11-27", "Nagaur", "Merta City APMC", "Bajra", 2900, 3100, 3000),
    ("2026-11-27", "Kota", "Kota APMC", "Soybean", 5300, 5700, 5500),
    # no Gram rows on purpose: "data not available" must be handled, not crash or be faked
]


@pytest.fixture()
def db(session_factory):
    with session_factory() as s:
        for d, dist, mkt, com, mn, mx, mo in ROWS:
            dt = date.fromisoformat(d)
            s.add(MandiPrice(
                record_hash=make_record_hash(dt, "Rajasthan", dist, mkt, com, "Other", "Local"),
                price_date=dt, state="Rajasthan", district=dist, market=mkt, commodity=com,
                variety="Other", grade="Local", min_price=mn, max_price=mx, modal_price=mo))
        s.commit()
    with session_factory() as s:
        yield s


def row(body, name):
    return next(r for r in body["rows"] if r["commodity"] == name)


# ------------------------------------------------------------- commodity comparison
def test_comparison_has_one_row_per_commodity_and_flags_missing_data(db):
    body = queries.commodity_comparison(db, Filters())
    assert [r["commodity"] for r in body["rows"]] == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
    gram = row(body, "Gram")
    assert gram["has_data"] is False and gram["avg_modal"] is None and gram["reason"]
    assert gram["msp"]["available"] is False and gram["records"] == 0
    assert body["newest_date"] == "2026-11-27"
    assert row(body, "Wheat")["days_behind_newest"] == 0


def test_comparison_prices_and_msp_position(db):
    body = queries.commodity_comparison(db, Filters())
    w, m, b, s = (row(body, n) for n in ("Wheat", "Mustard", "Bajra", "Soybean"))
    assert w["avg_modal"] == 2821.0 and w["msp"]["msp"] == 2585
    assert w["msp"]["status"] == "above" and w["msp"]["pct"] == 9.13 and w["msp"]["markets_below_msp"] == 0
    assert m["avg_modal"] == 6200.0 and m["msp"]["msp"] == 6200 and m["msp"]["status"] == "at"
    assert m["msp"]["markets_below_msp"] == 1 and m["msp"]["markets_total"] == 2
    assert b["msp"]["msp"] == 2900 and b["msp"]["status"] == "below" and b["msp"]["pct"] == -1.72
    assert s["msp"]["msp"] == 5708 and s["msp"]["pct"] == -3.64 and s["msp"]["share_below_pct"] == 100.0
    assert m["change_vs_previous"]["pct_change"] == -1.64        # like-for-like: Bassi only


def test_comparison_for_an_exact_date_and_for_district_filter(db):
    on = queries.commodity_comparison(db, Filters(), date(2026, 11, 26))
    assert row(on, "Wheat")["date"] == "2026-11-26" and row(on, "Wheat")["avg_modal"] == 2800.0
    assert row(on, "Bajra")["has_data"] is False and "2026-11-26" in row(on, "Bajra")["reason"]
    jaipur = queries.commodity_comparison(db, Filters(district="Jaipur"))
    assert row(jaipur, "Wheat")["avg_modal"] == 2940.0 and row(jaipur, "Bajra")["has_data"] is False


def test_comparison_ignores_the_commodity_filter(db):
    body = queries.commodity_comparison(db, Filters(commodity="Wheat"))
    assert len(body["rows"]) == 5 and row(body, "Mustard")["has_data"]


# ---------------------------------------------------------------- historical trends
def test_commodity_trends_index_msp_and_missing_commodity(db):
    body = queries.commodity_trends(db, Filters())
    assert body["dates"] == ["2026-11-26", "2026-11-27"]
    wheat = next(s for s in body["series"] if s["commodity"] == "Wheat")
    p0, p1 = wheat["points"]
    assert (p0["avg_modal"], p1["avg_modal"]) == (2800.0, 2821.0)
    assert (p0["index"], p1["index"]) == (100.0, 100.75) and wheat["base_date"] == "2026-11-26"
    assert p0["msp"] == 2585 and p0["vs_msp_pct"] == 8.32
    gram = next(s for s in body["series"] if s["commodity"] == "Gram")
    assert gram["has_data"] is False and gram["points"] == []
    bajra = next(s for s in body["series"] if s["commodity"] == "Bajra")
    assert len(bajra["points"]) == 1 and bajra["points"][0]["index"] == 100.0


def test_commodity_trends_respect_date_and_district_filters(db):
    only = queries.commodity_trends(db, Filters(date_from=date(2026, 11, 27)))
    assert only["dates"] == ["2026-11-27"]
    jaipur = queries.commodity_trends(db, Filters(district="Jaipur"))
    assert next(s for s in jaipur["series"] if s["commodity"] == "Bajra")["has_data"] is False


def test_single_commodity_trend_points_now_carry_msp(db):
    series = queries.trends(db, Filters(commodity="Mustard"), "none", 5)
    assert [p["msp"] for p in series[0]["points"]] == [6200, 6200]


# ------------------------------------------------------------------ district analysis
def test_district_analysis_for_one_commodity(db):
    d = queries.district_analysis(db, Filters(commodity="Mustard"))
    assert d["date"] == "2026-11-27" and d["msp"] == {"msp": 6200, "season": "RMS 2026-27"}
    assert [r["district"] for r in d["rows"]] == ["Baran", "Jaipur"]       # highest price first
    baran, jaipur = d["rows"]
    assert baran["avg_modal"] == 6400.0 and baran["msp_status"] == "above" and baran["markets_below_msp"] == 0
    assert jaipur["msp_status"] == "below" and jaipur["msp_pct"] == -3.23 and jaipur["markets_below_msp"] == 1
    assert d["state_average_modal"] == 6200.0 and baran["vs_state_avg_pct"] == 3.23


def test_district_analysis_unavailable_commodity_and_date(db):
    gram = queries.district_analysis(db, Filters(commodity="Gram"))
    assert gram["rows"] == [] and gram["date"] is None
    old = queries.district_analysis(db, Filters(commodity="Wheat"), date(2026, 11, 26))
    assert {r["district"] for r in old["rows"]} == {"Jaipur", "Baran", "Bundi"}


def test_district_matrix_uses_each_districts_latest_day_and_marks_old_cells(db):
    m = queries.district_matrix(db, Filters())
    by = {r["district"]: r["values"] for r in m["rows"]}
    assert by["Jaipur"]["Wheat"]["avg_modal"] == 2940.0 and by["Jaipur"]["Wheat"]["is_latest_date"] is True
    assert by["Baran"]["Wheat"]["date"] == "2026-11-26" and by["Baran"]["Wheat"]["is_latest_date"] is False
    assert by["Kota"]["Soybean"]["avg_modal"] == 5500.0 and by["Kota"]["Wheat"] is None
    assert all(v["Gram"] is None for v in by.values())
    gram_meta = next(c for c in m["commodities"] if c["name"] == "Gram")
    assert gram_meta["newest_date"] is None


# ---------------------------------------------------------------------- MSP comparison
def test_msp_overview_covers_all_five_and_lists_rates(db):
    o = queries.msp_overview(db, Filters())
    assert [r["commodity"] for r in o["rows"]] == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
    gram = row(o, "Gram")
    assert gram["has_data"] is False and gram["msp_available"] is False and gram["status"] == "unavailable"
    assert row(o, "Soybean")["gap"] == -208 and row(o, "Soybean")["status"] == "below"
    assert {r["commodity"] for r in o["rates"]} == {"Wheat", "Mustard", "Bajra", "Soybean", "Gram"}


def test_msp_breakdown_lists_most_below_msp_first(db):
    b = queries.msp_breakdown(db, Filters(commodity="Mustard"), "market")
    assert b["below_count"] == 1 and b["total"] == 2
    assert [r["market"] for r in b["rows"]] == ["Bassi APMC", "Anta APMC"]
    assert b["rows"][0]["pct"] == -3.23 and b["rows"][0]["status"] == "below"
    d = queries.msp_breakdown(db, Filters(commodity="Bajra"), "district")
    assert [r["district"] for r in d["rows"]] == ["Jodhpur", "Nagaur"]
    assert d["rows"][0]["status"] == "below" and d["rows"][1]["status"] == "above"


def test_msp_unavailable_for_a_date_outside_every_known_season(db):
    dt = date(2023, 1, 10)
    db.add(MandiPrice(record_hash=make_record_hash(dt, "Rajasthan", "Jaipur", "Bassi APMC", "Wheat", "Other", "Local"),
                      price_date=dt, state="Rajasthan", district="Jaipur", market="Bassi APMC",
                      commodity="Wheat", variety="Other", grade="Local",
                      min_price=2000, max_price=2200, modal_price=2100))
    db.commit()
    f = Filters(commodity="Wheat", date_to=dt)
    k = queries.kpis_for_commodity(db, f, "Wheat")
    assert k["msp"]["available"] is False and "No MSP" in k["msp"]["reason"]
    b = queries.msp_breakdown(db, f, "market")
    assert b["msp"] is None and b["rows"][0]["status"] == "unavailable" and b["rows"][0]["pct"] is None
    assert queries.trends(db, f, "none", 1)[0]["points"][0]["msp"] is None


def test_kpis_include_msp_block_and_still_report_no_data_exactly(db):
    k = queries.kpis_for_commodity(db, Filters(), "Wheat")
    assert k["msp"]["available"] and k["msp"]["msp"] == 2585 and k["msp"]["season"] == "RMS 2026-27"
    assert k["summary"]["avg_modal"] == 2821.0                      # existing KPI output unchanged
    assert queries.kpis_for_commodity(db, Filters(), "Gram") == {"has_data": False}


def test_market_compare_returns_msp_for_the_day(db):
    body = queries.compare_markets(db, Filters(commodity="Mustard"), "market", None, 10)
    assert body["msp"] == 6200 and len(body["rows"]) == 2


# -------------------------------------------------------------------------- reports
def test_commodity_summary_report_marks_unavailable_commodities(db):
    cols, rows = queries.report_rows(db, Filters(), "commodity_summary")
    assert len(rows) == 5 and "pct_vs_msp" in cols
    gram = next(r for r in rows if r["commodity"] == "Gram (Chana)")
    assert gram["data_status"] == "no data" and gram["avg_modal"] is None
    wheat = next(r for r in rows if r["commodity"] == "Wheat")
    assert wheat["data_status"] == "ok" and wheat["msp"] == 2585 and wheat["status_vs_msp"] == "above"


def test_detail_reports_cover_only_commodities_that_have_data(db):
    _, dist = queries.report_rows(db, Filters(), "district_analysis")
    assert {r["commodity"] for r in dist} == {"Wheat", "Mustard", "Bajra", "Soybean"}
    _, msp_rows = queries.report_rows(db, Filters(commodity="Mustard"), "msp")
    assert {r["commodity"] for r in msp_rows} == {"Mustard"} and len(msp_rows) == 2
    cols, hist = queries.report_rows(db, Filters(), "history")
    assert "index_base_100" in cols and not any(r["commodity"] == "Gram (Chana)" for r in hist)
    assert len([r for r in hist if r["commodity"] == "Wheat"]) == 2


def test_unknown_report_kind_is_an_error(db):
    with pytest.raises(ValueError):
        queries.report_rows(db, Filters(), "nope")


# -------------------------------------------------------------------- availability
def test_commodity_availability(db):
    a = {c["name"]: c for c in queries.commodity_availability(db, Filters())}
    assert list(a) == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
    assert a["Wheat"]["records"] == 5 and a["Wheat"]["markets"] == 4 and a["Wheat"]["has_data"]
    assert a["Gram"]["has_data"] is False and a["Gram"]["latest_date"] is None
    assert a["Gram"]["label"] == "Gram (Chana)"
    jaipur = {c["name"]: c for c in queries.commodity_availability(db, Filters(district="Jaipur"))}
    assert jaipur["Bajra"]["has_data"] is False and jaipur["Wheat"]["has_data"]


def test_filter_options_lists_all_supported_commodities_even_without_data(db):
    o = queries.filter_options(db, Filters())
    assert o["commodities"] == ["Bajra", "Mustard", "Soybean", "Wheat"]           # stored data only
    assert [c["name"] for c in o["supported_commodities"]] == ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"]
