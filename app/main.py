import logging
import mimetypes
import time
import uuid
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import BASE_DIR, settings
from .database import check_connection, get_db
from .models import FetchLog, MandiPrice
from .routes.dashboard import router as dashboard_router
from .scheduler import next_run_time, scheduler, start_scheduler, stop_scheduler
from .services import analytics
from .services.ingest import is_refresh_running, log_to_dict, run_refresh, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("mandi")

# Windows can map .js to text/plain through the registry, which makes browsers reject scripts.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

APP_VERSION = "0.5.0"
STARTED_AT = time.time()
FRONTEND_DIR = BASE_DIR / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"
SLOW_REQUEST_SECONDS = 1.0

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        check_connection()
    except Exception:  # noqa: BLE001 - keep the API up so /health can explain the problem
        logger.exception("MySQL is not reachable at startup")
    start_scheduler()  # automatic refresh every REFRESH_INTERVAL_HOURS (default 3)
    yield
    stop_scheduler()


app = FastAPI(
    title="Rajasthan Mandi Price API", version=APP_VERSION, lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list,
    allow_methods=["*"], allow_headers=["*"],
)


# ------------------------------------------------------------------ middleware
@app.middleware("http")
async def production_headers(request: Request, call_next):
    """Request id + timing + security headers + cache policy."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started

    path = request.url.path
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-ms"] = f"{elapsed * 1000:.0f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"

    if path == "/" or path.startswith("/static"):
        response.headers["Content-Security-Policy"] = CSP  # not applied to Swagger (/docs)
    if path.startswith("/api") or path.startswith("/health"):
        response.headers["Cache-Control"] = "no-cache"  # always revalidate live data
    if elapsed > SLOW_REQUEST_SECONDS and not path.startswith("/static"):
        logger.warning("Slow request %s %s took %.2fs", request.method, path, elapsed)
    return response


class CachedStatic(StaticFiles):
    """Static files: long cache in production (URLs carry ?v=<mtime>), revalidate in development."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
                if settings.app_env.lower() == "production" else "no-cache"
            )
        return response


# -------------------------------------------------------------- error handling
@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable or query failed"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None)
    logger.exception("Unhandled error on %s (request %s)", request.url.path, rid)
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error", "request_id": rid})


app.include_router(dashboard_router)


# --------------------------------------------------------------------- helpers
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


def _db_ok() -> bool:
    try:
        check_connection()
        return True
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------- health checks
@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Full status for the dashboard indicator. Always HTTP 200 (see /health/ready for probes)."""
    db_ok = _db_ok()
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "scheduler_running": scheduler.running,
        "next_scheduled_refresh": _iso_utc(next_run_time()),
        "refresh_running": is_refresh_running(),
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - STARTED_AT),
        "last_successful_refresh_at": None,
        "data_age_hours": None,
        "data_freshness": None,
    }
    if db_ok:
        try:
            ok = _last_success(db)
            if ok and ok.finished_at:
                hours = round((utcnow() - ok.finished_at).total_seconds() / 3600, 2)
                body["last_successful_refresh_at"] = _iso_utc(ok.finished_at)
                body["data_age_hours"] = hours
                body["data_freshness"] = analytics.freshness_status(hours, settings.refresh_interval_hours)
            else:
                body["data_freshness"] = "never"
        except SQLAlchemyError:
            logger.exception("Health check could not read fetch_logs")
            body["status"] = "degraded"
    return body


@app.get("/health/live")
def health_live():
    """Liveness probe: the process is up. Does not touch MySQL."""
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    """Readiness probe: MySQL reachable and the 3-hour scheduler running (503 otherwise)."""
    db_ok = _db_ok()
    ready = db_ok and scheduler.running
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready",
                 "database": db_ok, "scheduler_running": scheduler.running},
    )


# --------------------------------------------------------------------- refresh
_last_manual_started = 0.0


@app.post("/api/refresh", status_code=202)
def manual_refresh(background: BackgroundTasks):
    global _last_manual_started
    if is_refresh_running():
        raise HTTPException(status_code=409, detail="A refresh is already running")
    wait = settings.manual_refresh_cooldown_seconds - (time.monotonic() - _last_manual_started)
    if _last_manual_started and wait > 0:
        raise HTTPException(
            status_code=429, detail=f"Please wait {int(wait) + 1}s before refreshing again",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    _last_manual_started = time.monotonic()
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


# -------------------------------------------------------------------- frontend
def _asset_version() -> str:
    """Changes whenever any frontend file changes, so browsers fetch fresh CSS/JS."""
    newest = 0
    for p in FRONTEND_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".css", ".js", ".html", ".svg"}:
            newest = max(newest, p.stat().st_mtime_ns)
    return str(newest // 1_000_000_000)


@app.get("/", include_in_schema=False)
def index():
    if not INDEX_FILE.exists():
        return JSONResponse(status_code=404, content={
            "detail": "frontend/index.html not found. The API is running; see /docs."})
    html = INDEX_FILE.read_text(encoding="utf-8").replace("__ASSET_V__", _asset_version())
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    f = FRONTEND_DIR / "favicon.svg"
    if not f.exists():
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return FileResponse(f, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


# Only these sub-folders are public (so stray files in frontend/ are never exposed).
for _sub in ("css", "js", "vendor"):
    if (FRONTEND_DIR / _sub).is_dir():
        app.mount(f"/static/{_sub}", CachedStatic(directory=str(FRONTEND_DIR / _sub)), name=f"static-{_sub}")
