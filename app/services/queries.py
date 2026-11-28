"""All dashboard read queries. Aggregations run in SQL; small comparisons run in Python."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..commodities import BY_NAME, COMMODITY_NAMES, label_for
from ..models import FetchLog, MandiPrice
from . import analytics
from .ingest import utcnow
from .msp import MspTable, load_msp_table

COMMODITIES = COMMODITY_NAMES  # Wheat, Mustard, Bajra, Soybean, Gram
EXPORT_COLUMNS = ["date", "state", "district", "market", "commodity", "variety", "grade",
                  "min_price", "max_price", "modal_price"]
SORTABLE = {
    "date": MandiPrice.price_date, "district": MandiPrice.district, "market": MandiPrice.market,
    "commodity": MandiPrice.commodity, "min_price": MandiPrice.min_price,
    "max_price": MandiPrice.max_price, "modal_price": MandiPrice.modal_price,
}
EXPORT_ROW_LIMIT = 200_000


@dataclass
class Filters:
    commodity: str | None = None
    district: str | None = None
    market: str | None = None
    date_from: date | None = None
    date_to: date | None = None


def f_(v):
    return float(v) if v is not None else None


def _conds(f: Filters, commodity: str | None = None, use_from: bool = True, use_to: bool = True):
    c = []
    commodity = commodity or f.commodity
    if commodity:
        c.append(MandiPrice.commodity == commodity)
    if f.district:
        c.append(MandiPrice.district == f.district)
    if f.market:
        c.append(MandiPrice.market == f.market)
    if use_from and f.date_from:
        c.append(MandiPrice.price_date >= f.date_from)
    if use_to and f.date_to:
        c.append(MandiPrice.price_date <= f.date_to)
    return c


def _rows_on(db: Session, f: Filters, commodity: str, day: date) -> list[dict]:
    stmt = select(
        MandiPrice.district, MandiPrice.market, MandiPrice.variety, MandiPrice.grade,
        MandiPrice.min_price, MandiPrice.max_price, MandiPrice.modal_price,
    ).where(*_conds(f, commodity, False, False), MandiPrice.price_date == day)
    return [
        {"district": r.district, "market": r.market, "variety": r.variety, "grade": r.grade,
         "min_price": f_(r.min_price), "max_price": f_(r.max_price), "modal_price": f_(r.modal_price)}
        for r in db.execute(stmt)
    ]


# ---------------------------------------------------------------- filters
def filter_options(db: Session, f: Filters) -> dict:
    def distinct(col, *conds):
        return [r[0] for r in db.execute(select(col).where(*conds).distinct().order_by(col))]

    base = [MandiPrice.commodity == f.commodity] if f.commodity else []
    district_cond = base
    market_cond = base + ([MandiPrice.district == f.district] if f.district else [])
    markets = db.execute(
        select(MandiPrice.market, MandiPrice.district).where(*market_cond).distinct()
        .order_by(MandiPrice.market)
    ).all()
    first, last = db.execute(select(func.min(MandiPrice.price_date), func.max(MandiPrice.price_date))).one()
    return {
        "commodities": distinct(MandiPrice.commodity),   # only those that have stored data
        "supported_commodities": [{"name": c, "label": label_for(c)} for c in COMMODITIES],
        "districts": distinct(MandiPrice.district, *district_cond),
        "markets": [{"market": m, "district": d} for m, d in markets],
        "date_range": {"min": first.isoformat() if first else None,
                       "max": last.isoformat() if last else None},
    }


# ------------------------------------------------------------------- kpis
def msp_block(table: MspTable, commodity: str, day: date | None, rows: list[dict],
              avg_modal: float | None) -> dict:
    """MSP comparison for one commodity on one day (rows = that day's price rows)."""
    info = table.lookup(commodity, day)
    if info is None:
        return {"available": False,
                "reason": "No MSP on record for this commodity and date"}
    cmp_ = analytics.msp_compare(avg_modal, info["msp"])
    averages = analytics.market_modal_averages(rows)
    below = sum(1 for v in averages.values() if v < info["msp"])
    total = len(averages)
    return {
        "available": True, "msp": info["msp"], "season": info["season"],
        "avg_modal": avg_modal, "gap": cmp_["gap"], "pct": cmp_["pct"], "status": cmp_["status"],
        "markets_total": total, "markets_below_msp": below,
        "share_below_pct": round(below / total * 100, 1) if total else None,
    }


def kpis_for_commodity(db: Session, f: Filters, commodity: str, on: date | None = None,
                       msp_table: MspTable | None = None) -> dict:
    conds = _conds(f, commodity)
    if on:
        conds = conds + [MandiPrice.price_date == on]
    latest = db.scalar(select(func.max(MandiPrice.price_date)).where(*conds))
    if latest is None:
        return {"has_data": False}

    no_from = _conds(f, commodity, use_from=False)
    prev_date = db.scalar(select(func.max(MandiPrice.price_date)).where(*no_from, MandiPrice.price_date < latest))
    week_date = db.scalar(select(func.max(MandiPrice.price_date)).where(
        *no_from, MandiPrice.price_date <= latest - timedelta(days=7)))

    now_rows = _rows_on(db, f, commodity, latest)
    summary = analytics.summarize(now_rows)
    table = msp_table or load_msp_table(db)
    out = {
        "has_data": True,
        "latest_date": latest.isoformat(),
        "previous_date": prev_date.isoformat() if prev_date else None,
        "week_compare_date": week_date.isoformat() if week_date else None,
        "summary": summary,
        "change_vs_previous": analytics.like_for_like(
            now_rows, _rows_on(db, f, commodity, prev_date) if prev_date else []),
        "change_vs_week": analytics.like_for_like(
            now_rows, _rows_on(db, f, commodity, week_date) if week_date else []),
        "msp": msp_block(table, commodity, latest, now_rows, summary["avg_modal"]),
    }
    return out


# ----------------------------------------------------------------- trends
def trends(db: Session, f: Filters, group_by: str, top: int,
           msp_table: MspTable | None = None) -> list[dict]:
    group_col = {"market": MandiPrice.market, "district": MandiPrice.district}.get(group_by)
    conds = _conds(f)
    table = msp_table or load_msp_table(db)
    names: list[str | None] = [None]
    if group_col is not None:
        n = func.count(MandiPrice.id).label("n")
        names = [r[0] for r in db.execute(
            select(group_col, n).where(*conds).group_by(group_col).order_by(n.desc(), group_col).limit(top))]

    series = []
    for name in names:
        extra = [] if name is None else [group_col == name]
        stmt = (
            select(
                MandiPrice.price_date, func.avg(MandiPrice.modal_price),
                func.min(MandiPrice.min_price), func.max(MandiPrice.max_price),
                func.count(func.distinct(MandiPrice.market)), func.count(MandiPrice.id),
            ).where(*conds, *extra).group_by(MandiPrice.price_date).order_by(MandiPrice.price_date)
        )
        points = [
            {"date": d.isoformat(),
             "avg_modal": round(float(avg), 2) if avg is not None else None,
             "min_price": f_(mn), "max_price": f_(mx),
             "markets_reporting": int(mk), "records": int(cnt),
             "msp": (table.lookup(f.commodity, d) or {}).get("msp")}
            for d, avg, mn, mx, mk, cnt in db.execute(stmt)
        ]
        series.append({"name": name or "All markets", "points": points})
    return series


# ---------------------------------------------------------- market compare
def compare_markets(db: Session, f: Filters, level: str, on: date | None, limit: int) -> dict:
    day = on or db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(f)))
    if day is None:
        return {"date": None, "level": level, "average_modal": None, "msp": None, "rows": []}

    conds = _conds(f, use_from=False, use_to=False)
    avg_modal = func.avg(MandiPrice.modal_price)
    cols = [MandiPrice.market, MandiPrice.district] if level == "market" else [MandiPrice.district]
    stmt = (
        select(*cols, avg_modal, func.min(MandiPrice.min_price), func.max(MandiPrice.max_price),
               func.count(MandiPrice.id))
        .where(*conds, MandiPrice.price_date == day)
        .group_by(*cols).order_by(avg_modal.desc()).limit(limit)
    )
    overall = db.scalar(select(func.avg(MandiPrice.modal_price)).where(*conds, MandiPrice.price_date == day))
    overall = float(overall) if overall is not None else None

    rows = []
    for r in db.execute(stmt):
        *names, avg, mn, mx, cnt = r
        avg = float(avg) if avg is not None else None
        rows.append({
            "market": names[0] if level == "market" else None,
            "district": names[1] if level == "market" else names[0],
            "avg_modal": round(avg, 2) if avg is not None else None,
            "min_price": f_(mn), "max_price": f_(mx),
            "spread": round(float(mx) - float(mn), 2) if mn is not None and mx is not None else None,
            "diff_vs_avg_pct": analytics.pct_change(avg, overall),
            "records": int(cnt),
        })
    info = load_msp_table(db).lookup(f.commodity, day)
    return {"date": day.isoformat(), "level": level,
            "average_modal": round(overall, 2) if overall is not None else None,
            "msp": info["msp"] if info else None, "rows": rows}


# ------------------------------------------------------------ price table
def _price_dict(p: MandiPrice) -> dict:
    return {"id": p.id, "date": p.price_date.isoformat(), "state": p.state, "district": p.district,
            "market": p.market, "commodity": p.commodity, "variety": p.variety, "grade": p.grade,
            "min_price": f_(p.min_price), "max_price": f_(p.max_price), "modal_price": f_(p.modal_price)}


def _ordered(f: Filters, sort_by: str, order: str):
    col = SORTABLE[sort_by]
    primary = col.asc() if order == "asc" else col.desc()
    return select(MandiPrice).where(*_conds(f)).order_by(primary, MandiPrice.market, MandiPrice.id)


def list_prices(db: Session, f: Filters, sort_by: str, order: str, page: int, page_size: int) -> dict:
    total = db.scalar(select(func.count(MandiPrice.id)).where(*_conds(f))) or 0
    stmt = _ordered(f, sort_by, order).limit(page_size).offset((page - 1) * page_size)
    items = [_price_dict(p) for p in db.execute(stmt).scalars()]
    return {"total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size, "items": items}


def export_rows(db: Session, f: Filters) -> list[dict]:
    stmt = _ordered(f, "date", "desc").limit(EXPORT_ROW_LIMIT)
    return [_price_dict(p) for p in db.execute(stmt).scalars()]


# -------------------------------------------------------------- freshness
def freshness(db: Session, interval_hours: int, next_run=None, today: date | None = None) -> dict:
    today = today or date.today()
    last_ok = db.execute(
        select(FetchLog).where(FetchLog.status.in_(["success", "partial"]))
        .order_by(FetchLog.finished_at.desc()).limit(1)).scalar_one_or_none()
    last_any = db.execute(select(FetchLog).order_by(FetchLog.id.desc()).limit(1)).scalar_one_or_none()
    latest_date = db.scalar(select(func.max(MandiPrice.price_date)))
    total = db.scalar(select(func.count(MandiPrice.id))) or 0

    hours = None
    if last_ok and last_ok.finished_at:
        hours = round((utcnow() - last_ok.finished_at).total_seconds() / 3600, 2)
    status = analytics.freshness_status(hours, interval_hours)
    return {
        "status": status,
        "last_successful_refresh_at": last_ok.finished_at.isoformat() + "Z" if last_ok else None,
        "hours_since_refresh": hours,
        "last_refresh_status": last_any.status if last_any else None,
        "last_refresh_error": last_any.error_message if last_any and last_any.status != "success" else None,
        "latest_price_date": latest_date.isoformat() if latest_date else None,
        "days_behind": (today - latest_date).days if latest_date else None,
        "total_records": total,
        "next_scheduled_refresh": next_run.isoformat() if next_run else None,
        "interval_hours": interval_hours,
    }


# ======================================================================================
# Multi-commodity analytics (commodity comparison, history, districts, MSP, reports)
# Prices of different commodities are shown side by side or rebased, never averaged together.
# ======================================================================================
def _without_commodity(f: Filters) -> Filters:
    return replace(f, commodity=None)


def _pick(change: dict | None) -> float | None:
    return change.get("pct_change") if change else None


def commodity_comparison(db: Session, f: Filters, on: date | None = None) -> dict:
    """One row per supported commodity (even those with no data, flagged as unavailable)."""
    table = load_msp_table(db)
    base = _without_commodity(f)
    rows = []
    for c in COMMODITIES:
        k = kpis_for_commodity(db, base, c, on, table)
        row = {"commodity": c, "label": label_for(c), "season": BY_NAME[c].season,
               "has_data": k["has_data"]}
        if not k["has_data"]:
            row.update({
                "date": None, "avg_modal": None, "min_price": None, "max_price": None,
                "markets_reporting": 0, "records": 0, "change_vs_previous": None,
                "change_vs_week": None, "msp": {"available": False, "reason": "No price data"},
                "reason": (f"No prices on {on.isoformat()} for these filters" if on
                           else "No prices stored for these filters"),
            })
        else:
            s_ = k["summary"]
            row.update({
                "date": k["latest_date"], "avg_modal": s_["avg_modal"],
                "min_price": s_["min_price"], "max_price": s_["max_price"],
                "markets_reporting": s_["markets_reporting"], "records": s_["records"],
                "change_vs_previous": k["change_vs_previous"], "change_vs_week": k["change_vs_week"],
                "previous_date": k["previous_date"], "week_compare_date": k["week_compare_date"],
                "msp": k["msp"], "reason": None,
            })
        rows.append(row)
    dates = [r["date"] for r in rows if r["date"]]
    newest = max(dates) if dates else None
    for r in rows:
        r["days_behind_newest"] = ((date.fromisoformat(newest) - date.fromisoformat(r["date"])).days
                                   if newest and r["date"] else None)
    return {"date_requested": on.isoformat() if on else None, "newest_date": newest, "rows": rows,
            "note": ("Each commodity is shown on its own latest available date. Prices of "
                     "different commodities are compared side by side, never averaged together.")}


def commodity_trends(db: Session, f: Filters, commodities: list[str] | None = None) -> dict:
    """Daily average modal price per commodity, plus a base-100 index and MSP for each day."""
    table = load_msp_table(db)
    out = []
    for c in commodities or COMMODITIES:
        series = trends(db, replace(f, commodity=c), "none", 1, table)
        points = series[0]["points"] if series else []
        base = next((p["avg_modal"] for p in points if p["avg_modal"] is not None), None)
        base_date = next((p["date"] for p in points if p["avg_modal"] is not None), None)
        for p in points:
            p["index"] = analytics.index_to_base(p["avg_modal"], base)
            p["vs_msp_pct"] = analytics.pct_change(p["avg_modal"], p["msp"])
        out.append({"commodity": c, "label": label_for(c), "has_data": bool(points),
                    "base_date": base_date, "points": points})
    all_dates = sorted({p["date"] for s_ in out for p in s_["points"]})
    return {"dates": all_dates, "series": out,
            "note": "Index = average modal price rebased to 100 on each commodity's first date in range."}


def district_analysis(db: Session, f: Filters, on: date | None = None, limit: int = 60) -> dict:
    """District-wise price analysis for ONE commodity on one date."""
    commodity = f.commodity
    day = on or db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(f)))
    empty = {"commodity": commodity, "date": None, "state_average_modal": None,
             "msp": None, "rows": []}
    if day is None:
        return empty
    conds = _conds(f, use_from=False, use_to=False)
    stmt = (
        select(MandiPrice.district, MandiPrice.market,
               func.sum(MandiPrice.modal_price), func.count(MandiPrice.modal_price),
               func.min(MandiPrice.min_price), func.max(MandiPrice.max_price),
               func.count(MandiPrice.id))
        .where(*conds, MandiPrice.price_date == day)
        .group_by(MandiPrice.district, MandiPrice.market)
    )
    table = load_msp_table(db)
    info = table.lookup(commodity, day)
    msp = info["msp"] if info else None

    agg: dict[str, dict] = {}
    tot_sum = tot_n = 0.0
    for district, market, ssum, n_modal, mn, mx, cnt in db.execute(stmt):
        a = agg.setdefault(district, {"sum": 0.0, "n": 0, "min": None, "max": None,
                                      "records": 0, "markets": 0, "below": 0})
        if n_modal:
            a["sum"] += float(ssum); a["n"] += int(n_modal)
            tot_sum += float(ssum); tot_n += int(n_modal)
            if msp is not None and float(ssum) / int(n_modal) < msp:
                a["below"] += 1
        a["markets"] += 1
        a["records"] += int(cnt)
        if mn is not None:
            a["min"] = float(mn) if a["min"] is None else min(a["min"], float(mn))
        if mx is not None:
            a["max"] = float(mx) if a["max"] is None else max(a["max"], float(mx))

    state_avg = tot_sum / tot_n if tot_n else None
    rows = []
    for district, a in agg.items():
        avg = a["sum"] / a["n"] if a["n"] else None
        cmp_ = analytics.msp_compare(avg, msp)
        rows.append({
            "district": district,
            "avg_modal": round(avg, 2) if avg is not None else None,
            "min_price": a["min"], "max_price": a["max"],
            "spread": round(a["max"] - a["min"], 2) if a["min"] is not None and a["max"] is not None else None,
            "markets": a["markets"], "records": a["records"],
            "vs_state_avg_pct": analytics.pct_change(avg, state_avg),
            "msp_gap": cmp_["gap"], "msp_pct": cmp_["pct"], "msp_status": cmp_["status"],
            "markets_below_msp": a["below"] if msp is not None else None,
        })
    # districts with no modal price sort last
    rows.sort(key=lambda r: (r["avg_modal"] is None, -(r["avg_modal"] or 0), r["district"]))
    return {"commodity": commodity, "date": day.isoformat(),
            "state_average_modal": round(state_avg, 2) if state_avg is not None else None,
            "msp": ({"msp": msp, "season": info["season"]} if info else None),
            "rows": rows[:limit]}


def district_matrix(db: Session, f: Filters) -> dict:
    """District x commodity grid of average modal price.

    Each cell is the district's most recent day for that commodity (inside the filters), so a
    district that has not reported on the newest date still shows its last price, marked with its own
    date and `is_latest_date: false`. Commodities/districts with no data give null cells.
    """
    base = _without_commodity(f)
    newest: dict[str, str | None] = {}
    cells: dict[str, dict[str, dict]] = {}
    for c in COMMODITIES:
        latest_overall = db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(base, c)))
        newest[c] = latest_overall.isoformat() if latest_overall else None
        if latest_overall is None:
            continue
        last_day = (
            select(MandiPrice.district.label("d"), func.max(MandiPrice.price_date).label("day"))
            .where(*_conds(base, c)).group_by(MandiPrice.district).subquery()
        )
        stmt = (
            select(MandiPrice.district, last_day.c.day, func.avg(MandiPrice.modal_price),
                   func.count(func.distinct(MandiPrice.market)), func.count(MandiPrice.id))
            .join(last_day, and_(MandiPrice.district == last_day.c.d,
                                 MandiPrice.price_date == last_day.c.day))
            .where(*_conds(base, c, use_from=False, use_to=False))
            .group_by(MandiPrice.district, last_day.c.day)
        )
        for district, day, avg, markets, cnt in db.execute(stmt):
            cells.setdefault(district, {})[c] = {
                "avg_modal": round(float(avg), 2) if avg is not None else None,
                "markets": int(markets), "records": int(cnt), "date": day.isoformat(),
                "is_latest_date": day.isoformat() == newest[c]}
    rows = [{"district": d, "values": {c: cells[d].get(c) for c in COMMODITIES}} for d in sorted(cells)]
    return {"commodities": [{"name": c, "label": label_for(c), "newest_date": newest[c]} for c in COMMODITIES],
            "rows": rows}


def msp_overview(db: Session, f: Filters, on: date | None = None) -> dict:
    """Latest price vs MSP for every commodity, plus the MSP rate table."""
    comp = commodity_comparison(db, f, on)
    rows = []
    for r in comp["rows"]:
        m = r["msp"] or {"available": False}
        rows.append({
            "commodity": r["commodity"], "label": r["label"], "has_data": r["has_data"],
            "date": r["date"], "avg_modal": r["avg_modal"], "msp_available": m.get("available", False),
            "msp": m.get("msp"), "season": m.get("season"), "gap": m.get("gap"), "pct": m.get("pct"),
            "status": m.get("status", "unavailable"),
            "markets_total": m.get("markets_total"), "markets_below_msp": m.get("markets_below_msp"),
            "share_below_pct": m.get("share_below_pct"),
            "reason": r["reason"] or (None if m.get("available") else m.get("reason")),
        })
    return {"date_requested": comp["date_requested"], "rows": rows,
            "rates": load_msp_table(db).as_list(),
            "note": ("MSP is the Government of India support price in Rs/quintal for the marketing season "
                     "the price date falls in. Mandi modal prices are compared with it; MSP applies to "
                     "government procurement, not to every mandi sale.")}


def msp_breakdown(db: Session, f: Filters, level: str = "market", on: date | None = None,
                  limit: int = 100) -> dict:
    """Markets (or districts) of ONE commodity against its MSP, most-below-MSP first."""
    commodity = f.commodity
    day = on or db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(f)))
    if day is None:
        return {"commodity": commodity, "date": None, "level": level, "msp": None,
                "below_count": 0, "total": 0, "rows": []}
    info = load_msp_table(db).lookup(commodity, day)
    msp = info["msp"] if info else None
    cols = [MandiPrice.market, MandiPrice.district] if level == "market" else [MandiPrice.district]
    avg = func.avg(MandiPrice.modal_price)
    stmt = (select(*cols, avg, func.count(MandiPrice.id))
            .where(*_conds(f, use_from=False, use_to=False), MandiPrice.price_date == day)
            .group_by(*cols))
    rows = []
    for r in db.execute(stmt):
        *names, a, cnt = r
        a = float(a) if a is not None else None
        cmp_ = analytics.msp_compare(a, msp)
        rows.append({
            "market": names[0] if level == "market" else None,
            "district": names[1] if level == "market" else names[0],
            "avg_modal": round(a, 2) if a is not None else None, "records": int(cnt),
            "msp": msp, "gap": cmp_["gap"], "pct": cmp_["pct"], "status": cmp_["status"],
        })
    # lowest (most negative) gap first; rows without a comparable price last
    rows.sort(key=lambda r: (r["pct"] is None, r["pct"] if r["pct"] is not None else 0,
                             r["market"] or "", r["district"]))
    below = sum(1 for r in rows if r["status"] == "below")
    return {"commodity": commodity, "date": day.isoformat(), "level": level,
            "msp": ({"msp": msp, "season": info["season"]} if info else None),
            "below_count": below, "total": len(rows), "rows": rows[:limit]}


# ------------------------------------------------------------------- reports
REPORT_KINDS = ("commodity_summary", "district_analysis", "msp", "history")


def report_rows(db: Session, f: Filters, kind: str, on: date | None = None) -> tuple[list[str], list[dict]]:
    """(columns, rows) for the CSV reports. Commodities with no data are marked, not hidden,
    in the summary report; the detailed reports simply have no rows for them."""
    if kind == "commodity_summary":
        cols = ["commodity", "date", "avg_modal", "min_price", "max_price", "markets_reporting",
                "records", "change_vs_previous_pct", "change_vs_week_pct", "msp", "msp_season",
                "gap_vs_msp", "pct_vs_msp", "status_vs_msp", "markets_below_msp", "data_status"]
        rows = []
        for r in commodity_comparison(db, f, on)["rows"]:
            m = r["msp"] or {}
            rows.append({
                "commodity": r["label"], "date": r["date"], "avg_modal": r["avg_modal"],
                "min_price": r["min_price"], "max_price": r["max_price"],
                "markets_reporting": r["markets_reporting"], "records": r["records"],
                "change_vs_previous_pct": _pick(r["change_vs_previous"]),
                "change_vs_week_pct": _pick(r["change_vs_week"]),
                "msp": m.get("msp"), "msp_season": m.get("season"), "gap_vs_msp": m.get("gap"),
                "pct_vs_msp": m.get("pct"), "status_vs_msp": m.get("status", "unavailable"),
                "markets_below_msp": m.get("markets_below_msp"),
                "data_status": "ok" if r["has_data"] else "no data",
            })
        return cols, rows

    commodities = [f.commodity] if f.commodity else list(COMMODITIES)
    if kind == "district_analysis":
        cols = ["commodity", "date", "district", "avg_modal", "min_price", "max_price", "markets",
                "records", "vs_state_avg_pct", "msp", "gap_vs_msp", "pct_vs_msp", "markets_below_msp"]
        rows = []
        for c in commodities:
            d = district_analysis(db, replace(f, commodity=c), on, limit=500)
            for r in d["rows"]:
                rows.append({
                    "commodity": label_for(c), "date": d["date"], "district": r["district"],
                    "avg_modal": r["avg_modal"], "min_price": r["min_price"], "max_price": r["max_price"],
                    "markets": r["markets"], "records": r["records"],
                    "vs_state_avg_pct": r["vs_state_avg_pct"],
                    "msp": (d["msp"] or {}).get("msp"), "gap_vs_msp": r["msp_gap"],
                    "pct_vs_msp": r["msp_pct"], "markets_below_msp": r["markets_below_msp"],
                })
        return cols, rows
    if kind == "msp":
        cols = ["commodity", "date", "district", "market", "avg_modal", "msp", "msp_season",
                "gap_vs_msp", "pct_vs_msp", "status_vs_msp"]
        rows = []
        for c in commodities:
            d = msp_breakdown(db, replace(f, commodity=c), "market", on, limit=1000)
            for r in d["rows"]:
                rows.append({
                    "commodity": label_for(c), "date": d["date"], "district": r["district"],
                    "market": r["market"], "avg_modal": r["avg_modal"],
                    "msp": r["msp"], "msp_season": (d["msp"] or {}).get("season"),
                    "gap_vs_msp": r["gap"], "pct_vs_msp": r["pct"], "status_vs_msp": r["status"],
                })
        return cols, rows
    if kind == "history":
        cols = ["commodity", "date", "avg_modal", "min_price", "max_price", "markets_reporting",
                "index_base_100", "msp", "pct_vs_msp"]
        rows = []
        for s_ in commodity_trends(db, f, commodities)["series"]:
            for p in s_["points"]:
                rows.append({
                    "commodity": s_["label"], "date": p["date"], "avg_modal": p["avg_modal"],
                    "min_price": p["min_price"], "max_price": p["max_price"],
                    "markets_reporting": p["markets_reporting"], "index_base_100": p["index"],
                    "msp": p["msp"], "pct_vs_msp": p["vs_msp_pct"],
                })
        return cols, rows
    raise ValueError(f"unknown report kind '{kind}'")


# ------------------------------------------------------------ availability
def commodity_availability(db: Session, f: Filters) -> list[dict]:
    """Per-commodity data availability under the current district/market/date filters."""
    base = _without_commodity(f)
    table = load_msp_table(db)
    out = []
    for c in COMMODITIES:
        conds = _conds(base, c)
        n, first, last, markets, districts = db.execute(
            select(func.count(MandiPrice.id), func.min(MandiPrice.price_date),
                   func.max(MandiPrice.price_date), func.count(func.distinct(MandiPrice.market)),
                   func.count(func.distinct(MandiPrice.district))).where(*conds)).one()
        info = table.lookup(c, last or date.today())   # MSP in force on the latest stored price date
        out.append({
            "name": c, "label": label_for(c), "season": BY_NAME[c].season,
            "has_data": bool(n), "records": int(n or 0), "markets": int(markets or 0),
            "districts": int(districts or 0),
            "first_date": first.isoformat() if first else None,
            "latest_date": last.isoformat() if last else None,
            "current_msp": info["msp"] if info else None,
            "current_msp_season": info["season"] if info else None,
        })
    return out
