"""One-time import of a CSV (e.g. your data/mandi_prices.csv) using the same validation
and duplicate protection as the live refresh.

Run from the project root:
    python -m scripts.import_csv                      # defaults to data/mandi_prices.csv
    python -m scripts.import_csv path\\to\\file.csv
Safe to run more than once: existing rows are never duplicated.
"""
import csv
import sys
from pathlib import Path

from app.config import settings
from app.database import SessionLocal, check_connection
from app.services.ingest import upsert_prices, utcnow
from app.services.validation import validate_record


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/mandi_prices.csv")
    if not path.exists():
        raise SystemExit(f"File not found: {path.resolve()}")
    try:
        check_connection()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Cannot connect to MySQL: {exc}")

    valid, reasons, total = {}, [], 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            total += 1
            row, reason = validate_record(raw, expected_state=settings.target_state)
            if row is None:
                reasons.append(f"line {total + 1}: {reason}")
            else:
                valid[row["record_hash"]] = row

    with SessionLocal() as db:
        inserted, updated = upsert_prices(db, list(valid.values()), utcnow()) if valid else (0, 0)
        db.commit()

    print(f"Read {total} rows from {path}")
    print(f"  inserted: {inserted}   updated: {updated}   unchanged: {len(valid) - inserted - updated}")
    print(f"  rejected: {len(reasons)}")
    for r in reasons[:10]:
        print("   -", r)


if __name__ == "__main__":
    main()
