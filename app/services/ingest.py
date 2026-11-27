"""Fetch -> validate -> de-duplicate -> upsert into MySQL, with a fetch_logs audit row."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import FetchLog, MandiPrice
from .api_client import ApiError, MandiApiClient
from .validation import validate_record

logger = logging.getLogger(__name__)

COMMODITIES = ("Wheat", "Mustard")
PRICE_FIELDS = ("min_price", "max_price", "modal_price")
CHUNK = 500
MAX_REJECT_SAMPLES = 5

# One refresh at a time per process (scheduler and manual button share this lock).
_refresh_lock = threading.Lock()


def utcnow() -> datetime:
    """Naive UTC, so every timestamp in the DB is UTC regardless of MySQL server timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_refresh_running() -> bool:
    return _refresh_lock.locked()


def _same_price(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return Decimal(str(a)) == Decimal(str(b))


def upsert_prices(db, rows: list[dict], now: datetime) -> tuple[int, int]:
    """Insert new rows, update rows whose prices changed, skip identical ones."""
    hashes = [r["record_hash"] for r in rows]
    existing: dict[str, MandiPrice] = {}
    for i in range(0, len(hashes), CHUNK):
        stmt = select(MandiPrice).where(MandiPrice.record_hash.in_(hashes[i:i + CHUNK]))
        for obj in db.execute(stmt).scalars():
            existing[obj.record_hash] = obj

    inserted = updated = 0
    for row in rows:
        obj = existing.get(row["record_hash"])
        if obj is None:
            db.add(MandiPrice(**row, fetched_at=now, updated_at=now))
            inserted += 1
        elif not all(_same_price(getattr(obj, f), row[f]) for f in PRICE_FIELDS):
            for f in PRICE_FIELDS:
                setattr(obj, f, row[f])
            obj.updated_at = now
            updated += 1
    return inserted, updated


def log_to_dict(log: FetchLog) -> dict:
    def iso(dt):
        return dt.isoformat() + "Z" if dt else None
    return {
        "id": log.id, "trigger": log.trigger_source, "status": log.status,
        "records_fetched": log.records_fetched, "records_inserted": log.records_inserted,
        "records_updated": log.records_updated, "records_rejected": log.records_rejected,
        "error_message": log.error_message,
        "started_at": iso(log.started_at), "finished_at": iso(log.finished_at),
    }


def run_refresh(trigger: str = "manual", client: MandiApiClient | None = None,
                session_factory=SessionLocal) -> dict | None:
    """Run one refresh. Returns the fetch-log dict, or None if one is already running."""
    if not _refresh_lock.acquire(blocking=False):
        logger.warning("Refresh (%s) skipped: another refresh is already running", trigger)
        return None
    try:
        return _run(trigger, client or MandiApiClient(), session_factory)
    finally:
        _refresh_lock.release()


def _run(trigger: str, client: MandiApiClient, session_factory) -> dict:
    db = session_factory()
    log = FetchLog(trigger_source=trigger, status="running", started_at=utcnow())
    db.add(log)
    db.commit()  # visible immediately as 'running'
    logger.info("Refresh #%s started (%s)", log.id, trigger)

    notes: list[str] = []
    rejected_samples: list[str] = []
    fetched = rejected = failed_calls = 0
    valid: dict[str, dict] = {}

    try:
        for commodity in COMMODITIES:
            try:
                result = client.fetch(settings.target_state, commodity)
            except ApiError as exc:
                failed_calls += 1
                notes.append(f"{commodity}: API failure - {exc}")
                logger.error("API failure for %s: %s", commodity, exc)
                continue

            notes.extend(result.warnings)
            if not result.records:
                failed_calls += 1  # an empty answer is treated as suspicious, not as success
                notes.append(f"{commodity}: API returned no records")
                continue

            fetched += len(result.records)
            for raw in result.records:
                row, reason = validate_record(raw, expected_state=settings.target_state)
                if row is None:
                    rejected += 1
                    if len(rejected_samples) < MAX_REJECT_SAMPLES:
                        rejected_samples.append(f"{commodity}: {reason}")
                else:
                    valid[row["record_hash"]] = row  # same key twice in one batch -> last wins

        inserted = updated = 0
        if valid:
            inserted, updated = upsert_prices(db, list(valid.values()), utcnow())

        if rejected_samples:
            notes.append(f"{rejected} rejected row(s), e.g. " + "; ".join(rejected_samples))

        if not valid:
            status = "failed"
            notes.append("No valid records were stored")
        elif failed_calls:
            status = "partial"
        else:
            status = "success"

        log.records_fetched, log.records_inserted = fetched, inserted
        log.records_updated, log.records_rejected = updated, rejected
        log.status = status
        log.error_message = "\n".join(notes)[:5000] or None
        log.finished_at = utcnow()
        db.commit()  # prices + log row in one transaction
    except Exception as exc:  # noqa: BLE001 - never let the scheduler thread die
        logger.exception("Refresh #%s crashed", log.id)
        db.rollback()
        log = db.get(FetchLog, log.id)
        log.status = "failed"
        log.error_message = f"Unexpected error: {exc}"[:5000]
        log.finished_at = utcnow()
        db.commit()

    out = log_to_dict(log)
    db.close()
    logger.info("Refresh #%s finished: %s", out["id"], out)
    return out
