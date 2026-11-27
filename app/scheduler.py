"""APScheduler: refresh every REFRESH_INTERVAL_HOURS (default 3)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import FetchLog
from .services.ingest import run_refresh

logger = logging.getLogger(__name__)

JOB_ID = "mandi_refresh"
scheduler = BackgroundScheduler(timezone="UTC")


def _job() -> None:
    try:
        result = run_refresh("scheduler")
    except Exception:  # noqa: BLE001 - e.g. MySQL down; the next interval will retry
        logger.exception("Scheduled refresh crashed")
        return
    if result is None:
        logger.info("Scheduled refresh skipped (already running)")


def _first_run_time() -> datetime:
    """Run now unless a good refresh finished recently (avoids API spam on --reload restarts)."""
    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            last = db.execute(
                select(FetchLog.finished_at)
                .where(FetchLog.status.in_(["success", "partial"]))
                .order_by(FetchLog.finished_at.desc()).limit(1)
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        logger.exception("Could not read last refresh time; refreshing now")
        return now
    if last is None:
        return now
    due = last.replace(tzinfo=timezone.utc) + timedelta(hours=settings.refresh_interval_hours)
    return max(now, due)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _job,
        IntervalTrigger(hours=settings.refresh_interval_hours),
        id=JOB_ID, replace_existing=True,
        max_instances=1, coalesce=True, misfire_grace_time=600,
        next_run_time=_first_run_time(),
    )
    scheduler.start()
    logger.info("Scheduler started: every %sh, next run %s",
                settings.refresh_interval_hours, next_run_time())


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def next_run_time() -> datetime | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    return job.next_run_time if job else None
