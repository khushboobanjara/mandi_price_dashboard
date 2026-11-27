import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models


@pytest.fixture()
def session():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _row(h="a" * 64):
    from datetime import date
    return models.MandiPrice(
        record_hash=h, price_date=date(2026, 11, 26), state="Rajasthan",
        district="Baran", market="Anta APMC", commodity="Wheat",
        variety="Other", grade="Local", min_price=2800, max_price=2905, modal_price=2852,
    )


def test_tables_created(session):
    names = inspect(session.get_bind()).get_table_names()
    assert {"mandi_prices", "fetch_logs"} <= set(names)


def test_duplicate_hash_rejected(session):
    session.add(_row()); session.commit()
    session.add(_row())
    with pytest.raises(IntegrityError):
        session.commit()


def test_different_hash_allowed(session):
    session.add(_row("a" * 64)); session.add(_row("b" * 64)); session.commit()
    assert session.query(models.MandiPrice).count() == 2
