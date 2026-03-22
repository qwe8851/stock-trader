"""
RSI (Relative Strength Index) strategy.

Buy when RSI crosses below the oversold threshold (default 30).
Sell when RSI crosses above the overbought threshold (default 70).
"""
from typing import Any

from engine.strategies.base import BaseStrategy, Candle, Signal, SignalAction


def _calc_rsi(closes: list[float], period: int) -> float:
    """Simple RSI calculation without external dependencies."""
    if len(closes) < period + 1:
        return 50.0

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]

    # Use the last `period` deltas
    recent = deltas[-period:]
    avg_gain = sum(d for d in recent if d > 0) / period
    avg_loss = sum(-d for d in recent if d < 0) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class RSIStrategy(BaseStrategy):
    """
    Config keys:
      period     (int)   RSI period, default 14
      oversold   (float) Buy threshold, default 30
      overbought (float) Sell threshold, default 70
    """

    @property
    def name(self) -> str:
        return "RSI"

    @property
    def min_candles(self) -> int:
        return self.config.get("period", 14) + 2

    def _evaluate(self, candles: list[Candle]) -> Signal:
        period: int = self.config.get("period", 14)
        oversold: float = self.config.get("oversold", 30.0)
        overbought: float = self.config.get("overbought", 70.0)

        closes = [c.close for c in candles]
        rsi = _calc_rsi(closes, period)

        # Previous RSI to detect crossover
        prev_rsi = _calc_rsi(closes[:-1], period) if len(closes) > period + 1 else rsi

        meta = {"rsi": round(rsi, 2), "prev_rsi": round(prev_rsi, 2),
                "oversold": oversold, "overbought": overbought}

        if prev_rsi >= oversold > rsi:
            # Crossed below oversold — buy signal
            confidence = min(1.0, (oversold - rsi) / oversold)
            return Signal(
                action=SignalAction.BUY,
                symbol=self.symbol,
                confidence=confidence,
                reason=f"RSI crossed below oversold ({rsi:.1f} < {oversold})",
                metadata=meta,
            )

        if prev_rsi <= overbought < rsi:
            # Crossed above overbought — sell signal
            confidence = min(1.0, (rsi - overbought) / (100 - overbought))
            return Signal(
                action=SignalAction.SELL,
                symbol=self.symbol,
                confidence=confidence,
                reason=f"RSI crossed above overbought ({rsi:.1f} > {overbought})",
                metadata=meta,
            )

        return Signal(action=SignalAction.HOLD, symbol=self.symbol,
                      reason=f"RSI neutral ({rsi:.1f})", metadata=meta)
