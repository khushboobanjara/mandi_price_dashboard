import csv
import io
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..scheduler import next_run_time
from ..services import queries
from ..services.queries import Filters
from ..services.validation import ALLOWED_COMMODITIES

router = APIRouter(prefix="/api", tags=["dashboard"])


def get_filters(
    commodity: str | None = Query(None, description="Wheat or Mustard"),
    district: str | None = Query(None),
    market: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> Filters:
    if commodity:
        norm = ALLOWED_COMMODITIES.get(commodity.strip().casefold())
        if not norm:
            raise HTTPException(422, f"commodity must be one of {sorted(ALLOWED_COMMODITIES.values())}")
        commodity = norm
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    return Filters(commodity, (district or "").strip() or None, (market or "").strip() or None,
                   date_from, date_to)


def require_commodity(f: Filters = Depends(get_filters)) -> Filters:
    if not f.commodity:
        raise HTTPException(422, "commodity is required (Wheat or Mustard); prices of different commodities must not be mixed")
    return f


@router.get("/filters")
def filters(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    """Dropdown options. Pass commodity/district to narrow districts and markets."""
    return queries.filter_options(db, f)


@router.get("/kpis")
def kpis(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    commodities = [f.commodity] if f.commodity else list(queries.COMMODITIES)
    return {
        "commodities": {c: queries.kpis_for_commodity(db, f, c) for c in commodities},
        "freshness": queries.freshness(db, settings.refresh_interval_hours, next_run_time()),
        "note": "Percentage changes compare only markets that reported on both dates.",
    }


@router.get("/trends")
def trends(
    group_by: Literal["none", "market", "district"] = "none",
    top: int = Query(5, ge=1, le=10),
    f: Filters = Depends(require_commodity),
    db: Session = Depends(get_db),
):
    return {"commodity": f.commodity, "group_by": group_by,
            "series": queries.trends(db, f, group_by, top)}


@router.get("/markets/compare")
def compare(
    level: Literal["market", "district"] = "market",
    on: date | None = Query(None, alias="date", description="Defaults to the latest date available"),
    limit: int = Query(30, ge=1, le=200),
    f: Filters = Depends(require_commodity),
    db: Session = Depends(get_db),
):
    return {"commodity": f.commodity, **queries.compare_markets(db, f, level, on, limit)}


@router.get("/prices")
def prices(
    sort_by: Literal["date", "district", "market", "commodity", "min_price", "max_price", "modal_price"] = "date",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    f: Filters = Depends(get_filters),
    db: Session = Depends(get_db),
):
    return queries.list_prices(db, f, sort_by, order, page, page_size)


@router.get("/export/csv")
def export_csv(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    rows = queries.export_rows(db, f)
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM so Excel shows Hindi/UTF-8 names correctly
    writer = csv.DictWriter(buf, fieldnames=queries.EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    name = f"mandi_prices_{(f.commodity or 'all').lower()}_{datetime.now():%Y%m%d_%H%M}.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/freshness")
def freshness(db: Session = Depends(get_db)):
    return queries.freshness(db, settings.refresh_interval_hours, next_run_time())
