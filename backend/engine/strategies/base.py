"""
Abstract base class for all trading strategies.

Every concrete strategy receives a window of OHLCV candles and returns
a Signal indicating what action the engine should take.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    action: SignalAction
    symbol: str
    # Confidence in [0.0, 1.0] — used by RiskManager to size positions
    confidence: float = 1.0
    # Human-readable reason for the signal (logged + stored)
    reason: str = ""
    # Extra metadata (indicator values, etc.) stored for debugging
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.action != SignalAction.HOLD


@dataclass
class Candle:
    time: int       # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""
    interval: str = "1m"
    is_closed: bool = True


class BaseStrategy(ABC):
    """
    All strategies implement this interface.

    The engine calls `on_candle()` for every incoming price update.
    Strategies maintain their own internal state (indicator windows, etc.).
    """

    def __init__(self, symbol: str, config: dict[str, Any] | None = None) -> None:
        self.symbol = symbol.upper()
        self.config: dict[str, Any] = config or {}
        self._candles: list[Candle] = []

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier."""

    @property
    @abstractmethod
    def min_candles(self) -> int:
        """Minimum number of candles needed before generating a signal."""

    def on_candle(self, candle: Candle) -> Signal:
        """
        Called by the engine on every candle update.
        Appends the candle to the internal window and evaluates the strategy.
        """
        self._candles.append(candle)
        # Keep a rolling window to avoid unbounded memory growth
        max_window = self.config.get("max_window", 500)
        if len(self._candles) > max_window:
            self._candles = self._candles[-max_window:]

        if len(self._candles) < self.min_candles:
            return Signal(action=SignalAction.HOLD, symbol=self.symbol,
                          reason=f"Warming up ({len(self._candles)}/{self.min_candles})")

        return self._evaluate(self._candles)

    @abstractmethod
    def _evaluate(self, candles: list[Candle]) -> Signal:
        """Core strategy logic — receives the full candle window."""

    def reset(self) -> None:
        """Clear internal state (used between backtests)."""
        self._candles = []
