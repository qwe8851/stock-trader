"""
MACD (Moving Average Convergence Divergence) strategy.

Buy when MACD line crosses above the signal line (bullish crossover).
Sell when MACD line crosses below the signal line (bearish crossover).
"""
from typing import Any

from engine.strategies.base import BaseStrategy, Candle, Signal, SignalAction


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    emas = [values[0]]
    for v in values[1:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


def _calc_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float, float, float]:
    """
    Returns (macd_line, signal_line, histogram) for the most recent candle.
    """
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0

    fast_ema = _ema(closes, fast)
    slow_ema = _ema(closes, slow)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = _ema(macd_line, signal)

    last_macd = macd_line[-1]
    last_signal = signal_line[-1]
    histogram = last_macd - last_signal

    return last_macd, last_signal, histogram


class MACDStrategy(BaseStrategy):
    """
    Config keys:
      fast   (int) Fast EMA period, default 12
      slow   (int) Slow EMA period, default 26
      signal (int) Signal EMA period, default 9
    """

    @property
    def name(self) -> str:
        return "MACD"

    @property
    def min_candles(self) -> int:
        slow = self.config.get("slow", 26)
        signal = self.config.get("signal", 9)
        return slow + signal + 2

    def _evaluate(self, candles: list[Candle]) -> Signal:
        fast: int = self.config.get("fast", 12)
        slow: int = self.config.get("slow", 26)
        signal_period: int = self.config.get("signal", 9)

        closes = [c.close for c in candles]

        macd, sig, hist = _calc_macd(closes, fast, slow, signal_period)
        prev_macd, prev_sig, prev_hist = _calc_macd(closes[:-1], fast, slow, signal_period)

        meta = {
            "macd": round(macd, 4),
            "signal": round(sig, 4),
            "histogram": round(hist, 4),
            "prev_histogram": round(prev_hist, 4),
        }

        # Bullish crossover: histogram flipped from negative to positive
        if prev_hist <= 0 < hist:
            confidence = min(1.0, abs(hist) / (abs(macd) + 1e-9))
            return Signal(
                action=SignalAction.BUY,
                symbol=self.symbol,
                confidence=confidence,
                reason=f"MACD bullish crossover (hist {hist:.4f})",
                metadata=meta,
            )

        # Bearish crossover: histogram flipped from positive to negative
        if prev_hist >= 0 > hist:
            confidence = min(1.0, abs(hist) / (abs(macd) + 1e-9))
            return Signal(
                action=SignalAction.SELL,
                symbol=self.symbol,
                confidence=confidence,
                reason=f"MACD bearish crossover (hist {hist:.4f})",
                metadata=meta,
            )

        return Signal(action=SignalAction.HOLD, symbol=self.symbol,
                      reason=f"MACD neutral (hist {hist:.4f})", metadata=meta)
