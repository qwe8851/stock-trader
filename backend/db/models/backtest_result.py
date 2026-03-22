"""
BacktestResult ORM model.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from db.session import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|completed|failed

    # Parameters
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=True)
    start_date: Mapped[str] = mapped_column(String(32), nullable=True)
    end_date: Mapped[str] = mapped_column(String(32), nullable=True)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=True)

    # Results
    final_capital: Mapped[float] = mapped_column(Float, nullable=True)
    total_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=True)
    win_rate_pct: Mapped[float] = mapped_column(Float, nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=True)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=True)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=True)

    # JSON blobs (equity curve + trade log)
    equity_curve: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    trades: Mapped[str] = mapped_column(Text, nullable=True)          # JSON string

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
