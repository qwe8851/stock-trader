"""
Risk Manager — enforces position and drawdown limits before any order is placed.

Rules (all configurable via settings):
  - Max portfolio allocation per trade: 2%
  - Daily loss circuit breaker: halt trading if drawdown > 5%
  - Max open positions: 3
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from core.logging import get_logger
from engine.strategies.base import Signal, SignalAction

logger = get_logger(__name__)


@dataclass
class RiskConfig:
    max_position_pct: float = 0.02    # 2% of portfolio per trade
    daily_loss_limit_pct: float = 0.05  # halt if daily drawdown > 5%
    max_open_positions: int = 3


@dataclass
class PortfolioSnapshot:
    total_value_usd: float
    open_positions: int
    daily_start_value: float
    today: date = field(default_factory=lambda: datetime.now(timezone.utc).date())


class RiskManager:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._halted = False
        self._halt_reason = ""

    @property
    def is_halted(self) -> bool:
        return self._halted

    def resume(self) -> None:
        """Manually resume trading after a halt."""
        self._halted = False
        self._halt_reason = ""
        logger.info("RiskManager: trading resumed")

    def check(self, signal: Signal, portfolio: PortfolioSnapshot) -> tuple[bool, str]:
        """
        Returns (approved, reason).
        If approved is False the order must NOT be placed.
        """
        if not signal.is_actionable:
            return False, "HOLD signal — no action needed"

        # --- Circuit breaker ---
        if self._halted:
            return False, f"Trading halted: {self._halt_reason}"

        # --- Daily drawdown check ---
        if portfolio.daily_start_value > 0:
            drawdown = (portfolio.daily_start_value - portfolio.total_value_usd) / portfolio.daily_start_value
            if drawdown >= self._config.daily_loss_limit_pct:
                self._halt("Daily loss limit reached", drawdown)
                return False, self._halt_reason

        # --- Max open positions ---
        if (signal.action == SignalAction.BUY
                and portfolio.open_positions >= self._config.max_open_positions):
            return False, (
                f"Max open positions reached ({portfolio.open_positions}/"
                f"{self._config.max_open_positions})"
            )

        return True, "OK"

    def position_size_usd(self, portfolio: PortfolioSnapshot, confidence: float) -> float:
        """
        Calculate the USD amount to allocate for this trade.
        Scales linearly with signal confidence.
        """
        base = portfolio.total_value_usd * self._config.max_position_pct
        return round(base * max(0.1, min(1.0, confidence)), 2)

    def _halt(self, reason: str, value: float | None = None) -> None:
        suffix = f" ({value:.2%})" if value is not None else ""
        self._halt_reason = reason + suffix
        self._halted = True
        logger.warning("RiskManager: trading HALTED", extra={"reason": self._halt_reason})
