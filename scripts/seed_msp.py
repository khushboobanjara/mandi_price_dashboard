"""Add any missing built-in MSP rates to the msp_rates table (never overwrites existing rows).
Run from the project root:  python -m scripts.seed_msp
To record a newly announced MSP, INSERT a row into msp_rates (see README) - no code change needed.
"""
from app.database import SessionLocal, check_connection, engine
from app.services.msp import init_reference_data


def main() -> None:
    try:
        check_connection()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Cannot connect to MySQL: {exc}")
    inserted, present = init_reference_data(engine, SessionLocal)
    print(f"MSP rates: {inserted} added, {present} already present")


if __name__ == "__main__":
    main()
