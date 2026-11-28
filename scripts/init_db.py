"""Create tables via SQLAlchemy (alternative to running sql/schema.sql) and seed MSP rates.
Run from the project root:  python -m scripts.init_db
Safe to run on an existing database: only missing tables are created and MSP rows already present
are never overwritten.
"""
from sqlalchemy import inspect

from app.database import Base, SessionLocal, check_connection, engine
from app import models  # noqa: F401  (registers tables)
from app.services.msp import seed_msp


def main() -> None:
    try:
        check_connection()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Cannot connect to MySQL: {exc}\n"
            "Check DB_* values in .env and that MySQL is running."
        )
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        inserted, present = seed_msp(db)
    print("Connected OK. Tables:", sorted(inspect(engine).get_table_names()))
    print(f"MSP rates: {inserted} added, {present} already present")


if __name__ == "__main__":
    main()
