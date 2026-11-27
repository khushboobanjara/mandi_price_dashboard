"""Pure-Python analytics helpers (no DB). Rows are dicts with float prices or None."""
from __future__ import annotations

from statistics import mean

KEY_FIELDS = ("district", "market", "variety", "grade")


def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEY_FIELDS)


def pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / old * 100, 2)


def like_for_like(rows_now: list[dict], rows_before: list[dict], field: str = "modal_price") -> dict:
    """Percentage change using ONLY markets/varieties/grades present on both dates.

    Comparing plain averages is misleading when a different set of markets reported each day
    (e.g. 3 markets early in the day vs 55 the day before).
    """
    before = {_key(r): r[field] for r in rows_before if r.get(field) is not None}
    pairs, markets = [], set()
    for r in rows_now:
        k = _key(r)
        if r.get(field) is not None and k in before:
            pairs.append((r[field], before[k]))
            markets.add(r["market"])
    if not pairs:
        return {"pct_change": None, "avg_now": None, "avg_before": None,
                "markets_compared": 0, "rows_compared": 0}
    now_avg = mean(p[0] for p in pairs)
    before_avg = mean(p[1] for p in pairs)
    return {"pct_change": pct_change(now_avg, before_avg), "avg_now": round(now_avg, 2),
            "avg_before": round(before_avg, 2), "markets_compared": len(markets),
            "rows_compared": len(pairs)}


def summarize(rows: list[dict]) -> dict:
    modal_rows = [r for r in rows if r.get("modal_price") is not None]
    mins = [r["min_price"] for r in rows if r.get("min_price") is not None]
    maxs = [r["max_price"] for r in rows if r.get("max_price") is not None]

    per_market: dict[str, list[float]] = {}
    for r in modal_rows:
        per_market.setdefault(r["market"], []).append(r["modal_price"])
    market_avgs = {m: mean(v) for m, v in per_market.items()}

    def extreme(fn):
        if not market_avgs:
            return None
        name = fn(market_avgs, key=market_avgs.get)
        return {"market": name, "price": round(market_avgs[name], 2)}

    return {
        "records": len(rows),
        "markets_reporting": len({r["market"] for r in rows}),
        "avg_modal": round(mean(r["modal_price"] for r in modal_rows), 2) if modal_rows else None,
        "min_price": min(mins) if mins else None,
        "max_price": max(maxs) if maxs else None,
        "highest_modal_market": extreme(max),
        "lowest_modal_market": extreme(min),
        "missing_price_rows": sum(
            1 for r in rows
            if r.get("min_price") is None or r.get("max_price") is None or r.get("modal_price") is None
        ),
    }


def freshness_status(hours_since: float | None, interval_hours: int) -> str:
    if hours_since is None:
        return "never"
    if hours_since <= interval_hours + 1:
        return "fresh"
    if hours_since <= interval_hours * 4:
        return "delayed"
    return "stale"
