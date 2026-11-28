"""Minimum Support Price (MSP) reference data and lookup.

MSP is announced by the Government of India per crop and marketing season, in Rs per quintal.
A mandi price is compared with the MSP of the season it belongs to:
  * Rabi crops (Wheat, Mustard, Gram): Rabi Marketing Season (RMS) runs 1 April - 31 March.
  * Kharif crops (Bajra, Soybean):     Kharif Marketing Season (KMS) runs 1 October - 30 September.

BUILTIN_MSP below is only the default data set. Rows in the `msp_rates` table override it (same
commodity + season), so a new announcement is a one-row INSERT, not a code change. If a date is
not covered by any season the lookup returns None and the UI shows "MSP not available".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import MspRate

logger = logging.getLogger(__name__)

SRC_RABI = "Govt. of India CCEA MSP approval / DA&FW MSP statement"

# (commodity, season, applies_from, applies_to, msp Rs/quintal, source)
BUILTIN_MSP: list[tuple[str, str, date, date, float, str]] = [
    # Rabi Marketing Seasons (1 Apr - 31 Mar)
    ("Wheat",   "RMS 2024-25", date(2024, 4, 1), date(2025, 3, 31), 2275, SRC_RABI),
    ("Mustard", "RMS 2024-25", date(2024, 4, 1), date(2025, 3, 31), 5650, SRC_RABI),
    ("Gram",    "RMS 2024-25", date(2024, 4, 1), date(2025, 3, 31), 5440, SRC_RABI),
    ("Wheat",   "RMS 2025-26", date(2025, 4, 1), date(2026, 3, 31), 2425, SRC_RABI),
    ("Mustard", "RMS 2025-26", date(2025, 4, 1), date(2026, 3, 31), 5950, SRC_RABI),
    ("Gram",    "RMS 2025-26", date(2025, 4, 1), date(2026, 3, 31), 5650, SRC_RABI),
    ("Wheat",   "RMS 2026-27", date(2026, 4, 1), date(2027, 3, 31), 2585, SRC_RABI),
    ("Mustard", "RMS 2026-27", date(2026, 4, 1), date(2027, 3, 31), 6200, SRC_RABI),
    ("Gram",    "RMS 2026-27", date(2026, 4, 1), date(2027, 3, 31), 5875, SRC_RABI),
    # Announced 30 Sep 2026; applies from the April 2027 marketing season
    ("Wheat",   "RMS 2027-28", date(2027, 4, 1), date(2028, 3, 31), 2610, SRC_RABI),
    ("Mustard", "RMS 2027-28", date(2027, 4, 1), date(2028, 3, 31), 6613, SRC_RABI),
    ("Gram",    "RMS 2027-28", date(2027, 4, 1), date(2028, 3, 31), 5958, SRC_RABI),
    # Kharif Marketing Seasons (1 Oct - 30 Sep). Bajra = hybrid, Soybean = yellow.
    ("Bajra",   "KMS 2025-26", date(2025, 10, 1), date(2026, 9, 30), 2775, "Govt. of India CCEA MSP approval, KMS 2025-26"),
    ("Soybean", "KMS 2025-26", date(2025, 10, 1), date(2026, 9, 30), 5328, "Govt. of India CCEA MSP approval, KMS 2025-26"),
    ("Bajra",   "KMS 2026-27", date(2026, 10, 1), date(2027, 9, 30), 2900, "Govt. of India CCEA MSP approval, 13 May 2026"),
    ("Soybean", "KMS 2026-27", date(2026, 10, 1), date(2027, 9, 30), 5708, "Govt. of India CCEA MSP approval, 13 May 2026"),
]


@dataclass(frozen=True)
class MspEntry:
    commodity: str
    season: str
    applies_from: date
    applies_to: date
    msp: float
    source: str = ""


class MspTable:
    """In-memory MSP lookup (a few dozen rows), built once per request."""

    def __init__(self, entries: list[MspEntry]):
        self._by_commodity: dict[str, list[MspEntry]] = {}
        for e in entries:
            self._by_commodity.setdefault(e.commodity, []).append(e)
        for lst in self._by_commodity.values():
            lst.sort(key=lambda e: e.applies_from)

    def lookup(self, commodity: str | None, day: date | None) -> dict | None:
        """MSP in force on `day`, or None when the commodity/date is not covered."""
        if not commodity or day is None:
            return None
        match = [e for e in self._by_commodity.get(commodity, ())
                 if e.applies_from <= day <= e.applies_to]
        if not match:
            return None
        e = match[-1]  # latest-starting season wins if rows ever overlap
        return {"msp": float(e.msp), "season": e.season,
                "applies_from": e.applies_from.isoformat(), "applies_to": e.applies_to.isoformat(),
                "source": e.source}

    def as_list(self) -> list[dict]:
        return [
            {"commodity": e.commodity, "season": e.season, "msp": float(e.msp),
             "applies_from": e.applies_from.isoformat(), "applies_to": e.applies_to.isoformat(),
             "source": e.source}
            for lst in self._by_commodity.values() for e in lst
        ]


def builtin_entries() -> list[MspEntry]:
    return [MspEntry(*row) for row in BUILTIN_MSP]


def load_msp_table(db: Session) -> MspTable:
    """Built-in rates overlaid with whatever is in the msp_rates table.

    A missing/unreadable table must never break the price endpoints, so failures fall back to the
    built-in data and are logged.
    """
    merged: dict[tuple[str, str], MspEntry] = {(e.commodity, e.season): e for e in builtin_entries()}
    try:
        for r in db.execute(select(MspRate)).scalars():
            merged[(r.commodity, r.season)] = MspEntry(
                r.commodity, r.season, r.applies_from, r.applies_to, float(r.msp), r.source or "")
    except SQLAlchemyError:
        db.rollback()
        logger.warning("msp_rates table not readable; using built-in MSP data", exc_info=True)
    return MspTable(list(merged.values()))


def seed_msp(db: Session) -> tuple[int, int]:
    """Idempotently write BUILTIN_MSP into msp_rates. Existing rows are left untouched.

    Returns (inserted, already_present). Rows an admin edited by hand are never overwritten.
    """
    existing = {(r.commodity, r.season) for r in db.execute(select(MspRate)).scalars()}
    inserted = 0
    for c, season, start, end, msp, source in BUILTIN_MSP:
        if (c, season) in existing:
            continue
        db.add(MspRate(commodity=c, season=season, applies_from=start, applies_to=end,
                       msp=msp, source=source))
        inserted += 1
    db.commit()
    return inserted, len(BUILTIN_MSP) - inserted


def init_reference_data(engine, session_factory) -> tuple[int, int]:
    """Create msp_rates if the database predates it, then seed. Safe to run on every start."""
    MspRate.__table__.create(bind=engine, checkfirst=True)
    with session_factory() as db:
        return seed_msp(db)
