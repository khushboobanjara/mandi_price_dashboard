"""All dashboard read queries. Aggregations run in SQL; small comparisons run in Python."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FetchLog, MandiPrice
from . import analytics
from .ingest import utcnow

COMMODITIES = ("Wheat", "Mustard")
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
        "commodities": distinct(MandiPrice.commodity),
        "districts": distinct(MandiPrice.district, *district_cond),
        "markets": [{"market": m, "district": d} for m, d in markets],
        "date_range": {"min": first.isoformat() if first else None,
                       "max": last.isoformat() if last else None},
    }


# ------------------------------------------------------------------- kpis
def kpis_for_commodity(db: Session, f: Filters, commodity: str) -> dict:
    latest = db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(f, commodity)))
    if latest is None:
        return {"has_data": False}

    no_from = _conds(f, commodity, use_from=False)
    prev_date = db.scalar(select(func.max(MandiPrice.price_date)).where(*no_from, MandiPrice.price_date < latest))
    week_date = db.scalar(select(func.max(MandiPrice.price_date)).where(
        *no_from, MandiPrice.price_date <= latest - timedelta(days=7)))

    now_rows = _rows_on(db, f, commodity, latest)
    out = {
        "has_data": True,
        "latest_date": latest.isoformat(),
        "previous_date": prev_date.isoformat() if prev_date else None,
        "week_compare_date": week_date.isoformat() if week_date else None,
        "summary": analytics.summarize(now_rows),
        "change_vs_previous": analytics.like_for_like(
            now_rows, _rows_on(db, f, commodity, prev_date) if prev_date else []),
        "change_vs_week": analytics.like_for_like(
            now_rows, _rows_on(db, f, commodity, week_date) if week_date else []),
    }
    return out


# ----------------------------------------------------------------- trends
def trends(db: Session, f: Filters, group_by: str, top: int) -> list[dict]:
    group_col = {"market": MandiPrice.market, "district": MandiPrice.district}.get(group_by)
    conds = _conds(f)
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
             "markets_reporting": int(mk), "records": int(cnt)}
            for d, avg, mn, mx, mk, cnt in db.execute(stmt)
        ]
        series.append({"name": name or "All markets", "points": points})
    return series


# ---------------------------------------------------------- market compare
def compare_markets(db: Session, f: Filters, level: str, on: date | None, limit: int) -> dict:
    day = on or db.scalar(select(func.max(MandiPrice.price_date)).where(*_conds(f)))
    if day is None:
        return {"date": None, "level": level, "average_modal": None, "rows": []}

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
    return {"date": day.isoformat(), "level": level,
            "average_modal": round(overall, 2) if overall is not None else None, "rows": rows}


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
