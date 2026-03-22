"""
OHLCV (Open/High/Low/Close/Volume) model for TimescaleDB hypertable.
Uses Numeric types to avoid floating-point precision issues with financial data.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class OHLCV(Base):
    """
    Candlestick data stored as a TimescaleDB hypertable partitioned by time.

    The primary key is (time, symbol) so we can efficiently query
    a specific symbol over a time range.
    """

    __tablename__ = "ohlcv"

    # TimescaleDB requires the time dimension to be part of the primary key
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        comment="Candle open time (UTC)",
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        comment="Trading pair, e.g. BTCUSDT",
    )
    interval: Mapped[str] = mapped_column(
        String(5),
        primary_key=True,
        comment="Candle interval, e.g. 1m, 5m, 1h",
    )

    # OHLCV values - Numeric(precision, scale) for exact financial arithmetic
    open: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        comment="Opening price",
    )
    high: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        comment="Highest price during the interval",
    )
    low: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        comment="Lowest price during the interval",
    )
    close: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        comment="Closing price",
    )
    volume: Mapped[Decimal] = mapped_column(
        Numeric(36, 8),
        nullable=False,
        comment="Base asset volume traded during the interval",
    )
    quote_volume: Mapped[Decimal] = mapped_column(
        Numeric(36, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Quote asset volume (e.g. USDT value traded)",
    )
    num_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Number of trades during the interval",
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_ohlcv_symbol_time", "symbol", "time"),
        Index("ix_ohlcv_symbol_interval_time", "symbol", "interval", "time"),
    )

    def __repr__(self) -> str:
        return (
            f"<OHLCV {self.symbol} {self.interval} "
            f"{self.time.isoformat()} O={self.open} C={self.close}>"
        )
