"""Create tables via SQLAlchemy (alternative to running sql/schema.sql).
Run from the backend/ folder:  python -m scripts.init_db
"""
from sqlalchemy import inspect

from app.database import Base, check_connection, engine
from app import models  # noqa: F401  (registers tables)


def main() -> None:
    try:
        check_connection()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Cannot connect to MySQL: {exc}\n"
            "Check DB_* values in backend/.env and that MySQL is running."
        )
    Base.metadata.create_all(engine)
    print("Connected OK. Tables:", sorted(inspect(engine).get_table_names()))


if __name__ == "__main__":
    main()
