"""MSP reference data: season boundaries, overrides, seeding, graceful failure."""
from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import MspRate
from app.services import analytics
from app.services.msp import BUILTIN_MSP, MspTable, builtin_entries, load_msp_table, seed_msp

D = date.fromisoformat


@pytest.fixture()
def table():
    return MspTable(builtin_entries())


@pytest.mark.parametrize("commodity,day,msp,season", [
    ("Wheat", "2026-11-27", 2585, "RMS 2026-27"),
    ("Mustard", "2026-11-27", 6200, "RMS 2026-27"),
    ("Gram", "2026-11-27", 5875, "RMS 2026-27"),
    ("Bajra", "2026-11-27", 2900, "KMS 2026-27"),
    ("Soybean", "2026-11-27", 5708, "KMS 2026-27"),
])
def test_current_msp_for_each_of_the_five_commodities(table, commodity, day, msp, season):
    hit = table.lookup(commodity, D(day))
    assert hit["msp"] == msp and hit["season"] == season


def test_rabi_season_boundaries_are_1_april_to_31_march(table):
    assert table.lookup("Wheat", D("2026-03-31"))["msp"] == 2425   # RMS 2025-26
    assert table.lookup("Wheat", D("2026-04-01"))["msp"] == 2585   # RMS 2026-27
    assert table.lookup("Wheat", D("2027-03-31"))["msp"] == 2585
    assert table.lookup("Wheat", D("2027-04-01"))["msp"] == 2610   # RMS 2027-28 (announced Sep 2026)


def test_kharif_season_boundaries_are_1_october_to_30_september(table):
    assert table.lookup("Bajra", D("2026-09-30"))["msp"] == 2775   # KMS 2025-26
    assert table.lookup("Bajra", D("2026-10-01"))["msp"] == 2900   # KMS 2026-27
    assert table.lookup("Soybean", D("2026-09-30"))["msp"] == 5328
    assert table.lookup("Soybean", D("2026-10-01"))["msp"] == 5708


def test_dates_or_commodities_without_msp_return_none_not_a_guess(table):
    assert table.lookup("Wheat", D("2023-01-10")) is None          # before the oldest season on file
    assert table.lookup("Bajra", D("2027-10-01")) is None          # KMS 2027-28 not announced yet
    assert table.lookup("Rice", D("2026-11-27")) is None
    assert table.lookup("Wheat", None) is None and table.lookup(None, D("2026-11-27")) is None


def test_seed_is_idempotent_and_never_overwrites_edits(session_factory):
    with session_factory() as db:
        inserted, present = seed_msp(db)
        assert inserted == len(BUILTIN_MSP) and present == 0
        row = db.execute(select(MspRate).where(MspRate.commodity == "Wheat",
                                               MspRate.season == "RMS 2026-27")).scalar_one()
        row.msp = 2600          # an admin corrected the value
        db.commit()
        inserted, present = seed_msp(db)
        assert inserted == 0 and present == len(BUILTIN_MSP)
        assert db.scalar(select(func.count(MspRate.id))) == len(BUILTIN_MSP)
        assert float(db.execute(select(MspRate.msp).where(MspRate.commodity == "Wheat",
                                                          MspRate.season == "RMS 2026-27")).scalar_one()) == 2600.0


def test_database_rows_override_builtin_values_and_add_new_seasons(session_factory):
    with session_factory() as db:
        seed_msp(db)
        db.add(MspRate(commodity="Bajra", season="KMS 2027-28", applies_from=D("2027-10-01"),
                       applies_to=D("2028-09-30"), msp=3050, source="test"))
        r = db.execute(select(MspRate).where(MspRate.commodity == "Gram",
                                             MspRate.season == "RMS 2026-27")).scalar_one()
        r.msp = 5900
        db.commit()
        t = load_msp_table(db)
        assert t.lookup("Bajra", D("2027-11-01"))["msp"] == 3050
        assert t.lookup("Gram", D("2026-11-27"))["msp"] == 5900


def test_missing_msp_table_falls_back_to_builtin_data(engine, session_factory):
    MspRate.__table__.drop(engine)          # e.g. an old database that was never migrated
    with session_factory() as db:
        t = load_msp_table(db)              # must not raise
        assert t.lookup("Wheat", D("2026-11-27"))["msp"] == 2585


def test_msp_compare_statuses_and_edge_cases():
    assert analytics.msp_compare(2821, 2585) == {"msp": 2585, "gap": 236, "pct": 9.13, "status": "above"}
    assert analytics.msp_compare(2700, 2900)["status"] == "below"
    assert analytics.msp_compare(2900, 2900) == {"msp": 2900, "gap": 0, "pct": 0.0, "status": "at"}
    for price, msp in ((None, 2900), (2800, None), (2800, 0)):
        out = analytics.msp_compare(price, msp)
        assert out["status"] == "unavailable" and out["gap"] is None and out["pct"] is None


def test_index_to_base():
    assert analytics.index_to_base(2821, 2800) == 100.75
    assert analytics.index_to_base(None, 2800) is None
    assert analytics.index_to_base(2800, 0) is None and analytics.index_to_base(2800, None) is None
