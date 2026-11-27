from app.services.analytics import freshness_status, like_for_like, pct_change, summarize


def row(market, modal, mn=None, mx=None, district="D", variety="Other", grade="Local"):
    return {"district": district, "market": market, "variety": variety, "grade": grade,
            "min_price": mn, "max_price": mx, "modal_price": modal}


def test_pct_change_basic_and_edge_cases():
    assert pct_change(110, 100) == 10.0
    assert pct_change(90, 100) == -10.0
    assert pct_change(100, 0) is None
    assert pct_change(None, 100) is None
    assert pct_change(100, None) is None


def test_like_for_like_ignores_markets_missing_on_one_date():
    now = [row("A", 2940), row("B", 2702)]
    before = [row("A", 2800), row("C", 2000), row("D", 5000)]
    out = like_for_like(now, before)
    assert out["markets_compared"] == 1 and out["pct_change"] == 5.0
    assert out["avg_now"] == 2940 and out["avg_before"] == 2800


def test_like_for_like_matches_on_variety_and_grade_too():
    now = [row("A", 100, grade="FAQ")]
    before = [row("A", 50, grade="Local")]
    assert like_for_like(now, before)["pct_change"] is None


def test_like_for_like_no_overlap_or_no_previous():
    assert like_for_like([row("A", 1)], [])["pct_change"] is None
    assert like_for_like([row("A", 1)], [row("B", 1)])["markets_compared"] == 0


def test_summarize():
    s = summarize([row("A", 2940, 2780, 2980), row("B", 2702, 2640, 2770), row("C", None, 1, 2)])
    assert s["records"] == 3 and s["markets_reporting"] == 3
    assert s["avg_modal"] == 2821.0
    assert s["min_price"] == 1 and s["max_price"] == 2980
    assert s["highest_modal_market"] == {"market": "A", "price": 2940.0}
    assert s["lowest_modal_market"] == {"market": "B", "price": 2702.0}
    assert s["missing_price_rows"] == 1


def test_summarize_empty():
    s = summarize([])
    assert s["avg_modal"] is None and s["highest_modal_market"] is None


def test_freshness_status():
    assert freshness_status(None, 3) == "never"
    assert freshness_status(0.5, 3) == "fresh"
    assert freshness_status(4.0, 3) == "fresh"
    assert freshness_status(8, 3) == "delayed"
    assert freshness_status(30, 3) == "stale"
