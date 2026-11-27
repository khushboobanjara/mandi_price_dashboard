import logging
from contextlib import asynccontextmanager
from datetime import timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .database import check_connection, get_db
from .models import FetchLog, MandiPrice
from .routes.dashboard import router as dashboard_router
from .scheduler import next_run_time, scheduler, start_scheduler, stop_scheduler
from .services.ingest import is_refresh_running, log_to_dict, run_refresh

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("mandi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        check_connection()
    except Exception:  # noqa: BLE001 - keep the API up so /health can explain the problem
        logger.exception("MySQL is not reachable at startup")
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Rajasthan Mandi Price API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list,
    allow_methods=["*"], allow_headers=["*"],
)


app.include_router(dashboard_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable or query failed"})


def _iso_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.isoformat() + "Z"


def _price_to_dict(p: MandiPrice) -> dict:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {
        "id": p.id, "date": p.price_date.isoformat(), "state": p.state,
        "district": p.district, "market": p.market, "commodity": p.commodity,
        "variety": p.variety, "grade": p.grade,
        "min_price": f(p.min_price), "max_price": f(p.max_price), "modal_price": f(p.modal_price),
    }


def _last_success(db: Session):
    return db.execute(
        select(FetchLog).where(FetchLog.status.in_(["success", "partial"]))
        .order_by(FetchLog.finished_at.desc()).limit(1)
    ).scalar_one_or_none()


@app.get("/health")
def health():
    db_ok = True
    try:
        check_connection()
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "scheduler_running": scheduler.running,
        "next_scheduled_refresh": _iso_utc(next_run_time()),
        "refresh_running": is_refresh_running(),
    }


@app.post("/api/refresh", status_code=202)
def manual_refresh(background: BackgroundTasks):
    if is_refresh_running():
        raise HTTPException(status_code=409, detail="A refresh is already running")
    background.add_task(run_refresh, "manual")
    return {"status": "started", "message": "Refresh started; poll GET /api/refresh/status"}


@app.get("/api/refresh/status")
def refresh_status(db: Session = Depends(get_db)):
    last = db.execute(select(FetchLog).order_by(FetchLog.id.desc()).limit(1)).scalar_one_or_none()
    ok = _last_success(db)
    return {
        "running": is_refresh_running(),
        "last_refresh": log_to_dict(last) if last else None,
        "last_successful_refresh_at": log_to_dict(ok)["finished_at"] if ok else None,
        "next_scheduled_refresh": _iso_utc(next_run_time()),
        "interval_hours": settings.refresh_interval_hours,
    }


@app.get("/api/fetch-logs")
def fetch_logs(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(select(FetchLog).order_by(FetchLog.id.desc()).limit(limit)).scalars().all()
    return [log_to_dict(r) for r in rows]


@app.get("/api/prices/latest")
def latest_prices(limit: int = Query(20, ge=1, le=500), commodity: str | None = None,
                  db: Session = Depends(get_db)):
    stmt = select(MandiPrice).order_by(MandiPrice.price_date.desc(), MandiPrice.id.desc()).limit(limit)
    if commodity:
        stmt = stmt.where(MandiPrice.commodity == commodity)
    return [_price_to_dict(p) for p in db.execute(stmt).scalars()]


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(MandiPrice.id))) or 0
    by_commodity = dict(db.execute(
        select(MandiPrice.commodity, func.count(MandiPrice.id)).group_by(MandiPrice.commodity)
    ).all())
    first, last = db.execute(select(func.min(MandiPrice.price_date), func.max(MandiPrice.price_date))).one()
    return {
        "total_records": total, "by_commodity": by_commodity,
        "first_date": first.isoformat() if first else None,
        "last_date": last.isoformat() if last else None,
    }
