from datetime import date, datetime

from sqlalchemy import (
    BigInteger, CHAR, Date, DateTime, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# BigInteger autoincrement PKs don't work on SQLite; this variant keeps tests simple.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class MandiPrice(Base):
    __tablename__ = "mandi_prices"
    __table_args__ = (
        UniqueConstraint("record_hash", name="uq_record_hash"),
        Index("ix_commodity_date", "commodity", "price_date"),
        Index("ix_district_date", "district", "price_date"),
        Index("ix_market_date", "market", "price_date"),
        Index("ix_price_date", "price_date"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    record_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str] = mapped_column(String(150), nullable=False)
    market: Mapped[str] = mapped_column(String(200), nullable=False)
    commodity: Mapped[str] = mapped_column(String(100), nullable=False)
    variety: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    grade: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    min_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    max_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    modal_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class MspRate(Base):
    """Government Minimum Support Price (Rs/quintal) for one commodity and marketing season.

    Rows are editable data: when a new MSP is announced, insert a row (see README) - no code change.
    """
    __tablename__ = "msp_rates"
    __table_args__ = (
        UniqueConstraint("commodity", "season", name="uq_msp_commodity_season"),
        Index("ix_msp_commodity_from", "commodity", "applies_from"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    commodity: Mapped[str] = mapped_column(String(100), nullable=False)
    season: Mapped[str] = mapped_column(String(20), nullable=False)       # e.g. "RMS 2026-27"
    applies_from: Mapped[date] = mapped_column(Date, nullable=False)
    applies_to: Mapped[date] = mapped_column(Date, nullable=False)
    msp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class FetchLog(Base):
    __tablename__ = "fetch_logs"
    __table_args__ = (
        Index("ix_fetch_started", "started_at"),
        Index("ix_fetch_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    trigger_source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
