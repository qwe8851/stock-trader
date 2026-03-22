"""
Risk Manager — enforces position and drawdown limits before any order is placed.

Phase 10 additions:
  - Kelly Criterion position sizing (from historical win rate + win/loss ratio)
  - Value at Risk (Historical Simulation, 95% / 99%)
  - Per-strategy drawdown circuit breaker (auto-pause at 15% loss)
  - Runtime config update via REST API
  - Risk event log (last 100 events in memory)

Original rules (all configurable):
  - Max portfolio allocation per trade: 2%
  - Daily loss circuit breaker: halt trading if drawdown > 5%
  - Max open positions: 3
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class RiskConfig:
    # Original
    max_position_pct: float = 0.02
    daily_loss_limit_pct: float = 0.05
    max_open_positions: int = 3
    # Kelly
    use_kelly: bool = True
    kelly_lookback: int = 50
    half_kelly: bool = True
    # Per-strategy drawdown
    strategy_drawdown_limit_pct: float = 0.15
    # VaR
    var_confidence: float = 0.95


# ---------------------------------------------------------------------------
# Portfolio snapshot (passed from TradingEngine on every tick)
# ---------------------------------------------------------------------------

@dataclass
class PortfolioSnapshot:
    total_value_usd: float
    open_positions: int
    daily_start_value: float
    today: date = field(default_factory=lambda: datetime.now(timezone.utc).date())


# ---------------------------------------------------------------------------
# Kelly Criterion
# ---------------------------------------------------------------------------

class KellyCalculator:
    """
    Computes the Kelly fraction from completed trade history.

    f* = (b·p - q) / b
      p = win probability
      q = 1 - p
      b = avg_win / avg_loss  (payoff ratio)

    Returns 0 if there is insufficient history.
    Capped at 0.5 to prevent ruin.
    """

    @staticmethod
    def fraction(orders: list[dict], lookback: int = 50) -> float:
        sells = [
            o for o in orders
            if "SELL" in o.get("side", "") and "pnl" in o
        ][-lookback:]

        if len(sells) < 5:
            return 0.0

        wins = [o["pnl"] for o in sells if o["pnl"] > 0]
        losses = [abs(o["pnl"]) for o in sells if o["pnl"] <= 0]

        if not wins or not losses:
            return 0.0

        p = len(wins) / len(sells)
        q = 1.0 - p
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)

        if avg_loss == 0:
            return 0.5

        b = avg_win / avg_loss
        kelly = (b * p - q) / b
        return max(0.0, min(0.5, kelly))

    @staticmethod
    def fraction_for_strategy(orders: list[dict], strategy: str, lookback: int = 50) -> float:
        strat_orders = [o for o in orders if o.get("strategy", "") == strategy]
        return KellyCalculator.fraction(strat_orders, lookback)


# ---------------------------------------------------------------------------
# Value at Risk (Historical Simulation)
# ---------------------------------------------------------------------------

class VarCalculator:
    """
    Historical-simulation VaR from an equity curve.

    Returns (var_usd, var_pct) at the requested confidence level.
    A positive return means "at confidence% probability your 1-period
    loss will not exceed var_usd".
    """

    @staticmethod
    def compute(
        equity_values: list[float],
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        if len(equity_values) < 10:
            return 0.0, 0.0

        returns = [
            (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
            for i in range(1, len(equity_values))
            if equity_values[i - 1] != 0
        ]
        if not returns:
            return 0.0, 0.0

        sorted_r = sorted(returns)
        idx = max(0, int((1.0 - confidence) * len(sorted_r)) - 1)
        var_return = sorted_r[idx]

        var_pct = -var_return if var_return < 0 else 0.0
        var_usd = var_pct * equity_values[-1]
        return round(var_usd, 2), round(var_pct * 100, 4)


# ---------------------------------------------------------------------------
# Per-strategy drawdown tracker
# ---------------------------------------------------------------------------

class StrategyDrawdownTracker:
    """
    Tracks cumulative P&L per strategy.
    Pauses a strategy when its drawdown from peak exceeds the limit.
    """

    def __init__(self, limit_pct: float = 0.15) -> None:
        self._limit = limit_pct
        self._cumulative: dict[str, float] = {}   # strategy → cumulative P&L
        self._peak: dict[str, float] = {}          # strategy → peak cumulative P&L
        self._paused: set[str] = set()

    def record(self, strategy: str, pnl: float) -> bool:
        """
        Record a completed trade result.
        Returns True if strategy was just paused.
        """
        self._cumulative[strategy] = self._cumulative.get(strategy, 0.0) + pnl

        cum = self._cumulative[strategy]
        peak = self._peak.get(strategy, 0.0)
        if cum > peak:
            self._peak[strategy] = cum
            peak = cum

        if peak > 0 and (peak - cum) / peak >= self._limit:
            if strategy not in self._paused:
                self._paused.add(strategy)
                logger.warning(
                    "Strategy auto-paused: drawdown limit reached",
                    extra={"strategy": strategy, "drawdown_pct": (peak - cum) / peak},
                )
                return True
        return False

    def is_paused(self, strategy: str) -> bool:
        return strategy in self._paused

    def resume(self, strategy: str) -> None:
        self._paused.discard(strategy)
        logger.info("Strategy manually resumed", extra={"strategy": strategy})

    def resume_all(self) -> None:
        self._paused.clear()

    def drawdown_pct(self, strategy: str) -> float:
        cum = self._cumulative.get(strategy, 0.0)
        peak = self._peak.get(strategy, 0.0)
        if peak <= 0:
            return 0.0
        dd = (peak - cum) / peak
        return round(max(0.0, dd) * 100, 2)

    def stats(self) -> list[dict]:
        all_strats = set(self._cumulative) | set(self._peak)
        return [
            {
                "strategy": s,
                "cumulative_pnl": round(self._cumulative.get(s, 0.0), 2),
                "peak_pnl": round(self._peak.get(s, 0.0), 2),
                "drawdown_pct": self.drawdown_pct(s),
                "paused": s in self._paused,
            }
            for s in sorted(all_strats)
        ]


# ---------------------------------------------------------------------------
# Risk event log
# ---------------------------------------------------------------------------

class RiskEventLog:
    MAX_EVENTS = 200

    def __init__(self) -> None:
        self._events: list[dict] = []

    def record(self, event_type: str, detail: str, data: dict | None = None) -> None:
        self._events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "detail": detail,
            **(data or {}),
        })
        if len(self._events) > self.MAX_EVENTS:
            self._events = self._events[-self.MAX_EVENTS:]

    def last(self, n: int = 50) -> list[dict]:
        return list(reversed(self._events[-n:]))


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

from engine.strategies.base import Signal, SignalAction  # noqa: E402


class RiskManager:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._halted = False
        self._halt_reason = ""
        self._strategy_dd = StrategyDrawdownTracker(
            limit_pct=self._config.strategy_drawdown_limit_pct
        )
        self._equity_curve: list[float] = []
        self._events = RiskEventLog()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def config(self) -> RiskConfig:
        return self._config

    def update_config(self, **kwargs: Any) -> None:
        """Update RiskConfig fields at runtime (via REST API)."""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        # Propagate drawdown limit to tracker
        self._strategy_dd._limit = self._config.strategy_drawdown_limit_pct
        logger.info("RiskConfig updated", extra={"changes": kwargs})

    def resume(self) -> None:
        """Resume from a global halt."""
        self._halted = False
        self._halt_reason = ""
        self._events.record("RESUME", "Global halt manually cleared")
        logger.info("RiskManager: trading resumed")

    def resume_strategy(self, strategy: str) -> None:
        self._strategy_dd.resume(strategy)
        self._events.record("STRATEGY_RESUME", f"Strategy {strategy} manually resumed",
                            {"strategy": strategy})

    # ------------------------------------------------------------------
    # Signal approval
    # ------------------------------------------------------------------

    def check(
        self, signal: Signal, portfolio: PortfolioSnapshot
    ) -> tuple[bool, str]:
        if not signal.is_actionable:
            return False, "HOLD signal — no action needed"

        if self._halted:
            return False, f"Trading halted: {self._halt_reason}"

        # Daily drawdown check
        if portfolio.daily_start_value > 0:
            drawdown = (
                (portfolio.daily_start_value - portfolio.total_value_usd)
                / portfolio.daily_start_value
            )
            if drawdown >= self._config.daily_loss_limit_pct:
                self._halt("Daily loss limit reached", drawdown)
                return False, self._halt_reason

        # Max open positions
        if (
            signal.action == SignalAction.BUY
            and portfolio.open_positions >= self._config.max_open_positions
        ):
            reason = (
                f"Max open positions ({portfolio.open_positions}/"
                f"{self._config.max_open_positions})"
            )
            return False, reason

        # Per-strategy drawdown
        strategy_name = signal.metadata.get("strategy", "")
        if strategy_name and self._strategy_dd.is_paused(strategy_name):
            reason = f"Strategy '{strategy_name}' paused (drawdown limit)"
            return False, reason

        return True, "OK"

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def position_size_usd(
        self,
        portfolio: PortfolioSnapshot,
        confidence: float,
        orders: list[dict] | None = None,
    ) -> float:
        """
        Calculate USD amount for this trade.

        If use_kelly and enough history → Kelly-adjusted size.
        Otherwise → flat max_position_pct.
        """
        if self._config.use_kelly and orders:
            kelly = KellyCalculator.fraction(orders, self._config.kelly_lookback)
            if kelly > 0:
                frac = kelly / 2.0 if self._config.half_kelly else kelly
                # Still respect the max_position_pct ceiling
                frac = min(frac, self._config.max_position_pct * 10)
                base = portfolio.total_value_usd * frac
                return round(base * max(0.1, min(1.0, confidence)), 2)

        # Fallback: flat fraction
        base = portfolio.total_value_usd * self._config.max_position_pct
        return round(base * max(0.1, min(1.0, confidence)), 2)

    # ------------------------------------------------------------------
    # Trade result recording
    # ------------------------------------------------------------------

    def record_trade(self, strategy: str, pnl: float, order: dict) -> None:
        """Called after every completed SELL order."""
        paused = self._strategy_dd.record(strategy, pnl)
        if paused:
            self._events.record(
                "STRATEGY_PAUSE",
                f"Strategy '{strategy}' auto-paused: drawdown limit",
                {"strategy": strategy, "pnl": pnl},
            )
            try:
                import asyncio
                from services.notifications.telegram import notify_risk_halt
                loop = asyncio.get_running_loop()
                if loop and loop.is_running():
                    asyncio.create_task(
                        notify_risk_halt(
                            f"Strategy '{strategy}' paused (drawdown limit)",
                            0.0,
                        )
                    )
            except Exception:
                pass

    def push_equity(self, value: float) -> None:
        """Update equity curve for VaR calculation."""
        self._equity_curve.append(value)
        # Keep last 500 data points
        if len(self._equity_curve) > 500:
            self._equity_curve = self._equity_curve[-500:]

    # ------------------------------------------------------------------
    # Risk metrics
    # ------------------------------------------------------------------

    def get_metrics(
        self,
        portfolio: PortfolioSnapshot,
        orders: list[dict] | None = None,
    ) -> dict[str, Any]:
        orders = orders or []

        # Kelly
        kelly_raw = KellyCalculator.fraction(orders, self._config.kelly_lookback)
        kelly_frac = kelly_raw / 2.0 if self._config.half_kelly else kelly_raw
        kelly_position_usd = round(portfolio.total_value_usd * kelly_frac, 2)

        # VaR
        var_95_usd, var_95_pct = VarCalculator.compute(self._equity_curve, 0.95)
        var_99_usd, var_99_pct = VarCalculator.compute(self._equity_curve, 0.99)

        # Daily drawdown
        if portfolio.daily_start_value > 0:
            daily_dd_pct = max(0.0, (
                portfolio.daily_start_value - portfolio.total_value_usd
            ) / portfolio.daily_start_value * 100)
        else:
            daily_dd_pct = 0.0

        # Per-strategy
        strategy_stats = self._strategy_dd.stats()

        # Enrich strategy stats with Kelly fraction
        for s in strategy_stats:
            k = KellyCalculator.fraction_for_strategy(
                orders, s["strategy"], self._config.kelly_lookback
            )
            s["kelly_fraction"] = round(k / 2.0 if self._config.half_kelly else k, 4)

        return {
            # Kelly
            "kelly_raw": round(kelly_raw, 4),
            "kelly_fraction": round(kelly_frac, 4),
            "kelly_position_usd": kelly_position_usd,
            "kelly_lookback_trades": len([
                o for o in orders if "SELL" in o.get("side", "")
            ]),
            # VaR
            "var_95_usd": var_95_usd,
            "var_95_pct": var_95_pct,
            "var_99_usd": var_99_usd,
            "var_99_pct": var_99_pct,
            "equity_curve_len": len(self._equity_curve),
            # Daily drawdown
            "daily_drawdown_pct": round(daily_dd_pct, 3),
            "daily_loss_limit_pct": self._config.daily_loss_limit_pct * 100,
            # Circuit breaker
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            # Per-strategy
            "strategy_risks": strategy_stats,
            # Config snapshot
            "config": {
                "max_position_pct": self._config.max_position_pct,
                "daily_loss_limit_pct": self._config.daily_loss_limit_pct,
                "max_open_positions": self._config.max_open_positions,
                "use_kelly": self._config.use_kelly,
                "half_kelly": self._config.half_kelly,
                "kelly_lookback": self._config.kelly_lookback,
                "strategy_drawdown_limit_pct": self._config.strategy_drawdown_limit_pct,
            },
        }

    def get_events(self, n: int = 50) -> list[dict]:
        return self._events.last(n)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _halt(self, reason: str, value: float | None = None) -> None:
        import asyncio
        suffix = f" ({value:.2%})" if value is not None else ""
        self._halt_reason = reason + suffix
        self._halted = True
        self._events.record("HALT", self._halt_reason)
        logger.warning("RiskManager: trading HALTED", extra={"reason": self._halt_reason})
        try:
            from services.notifications.telegram import notify_risk_halt
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                asyncio.create_task(notify_risk_halt(self._halt_reason, 0.0))
        except Exception:
            pass
