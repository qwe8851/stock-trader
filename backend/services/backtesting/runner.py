"""
Backtesting runner.

Uses the same pure-Python RSI/MACD logic from engine/strategies but
runs it over a historical OHLCV list instead of a live stream.

vectorbt is intentionally NOT used here to avoid a heavy binary dependency
during the Docker build. The strategies are replayed with simple loops,
which is fast enough for candle counts up to ~50k (a few seconds).

If you later want vectorbt, install it in pyproject.toml and swap in
the vectorbt runner — the interface (run_backtest) stays identical.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.strategies.base import BaseStrategy, Candle, SignalAction
from engine.strategies.macd_strategy import MACDStrategy
from engine.strategies.rsi_strategy import RSIStrategy

STRATEGY_MAP: dict[str, type[BaseStrategy]] = {
    "RSI": RSIStrategy,
    "MACD": MACDStrategy,
}


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    # List of {"time": unix_ms, "value": float} — equity curve for the chart
    equity_curve: list[dict] = field(default_factory=list)
    # List of {"time", "side", "price", "pnl"} — individual trade log
    trades: list[dict] = field(default_factory=list)


def run_backtest(
    strategy_name: str,
    symbol: str,
    ohlcv: list[dict],
    config: dict | None = None,
    initial_capital: float = 10_000.0,
    interval: str = "1h",
    start_date: str = "",
    end_date: str = "",
) -> BacktestResult:
    """
    Replay a strategy over historical OHLCV data.

    Each dict in ``ohlcv`` must have keys: time, open, high, low, close, volume.
    ``time`` is a Unix millisecond timestamp.
    """
    cls = STRATEGY_MAP.get(strategy_name.upper())
    if cls is None:
        raise ValueError(f"Unknown strategy '{strategy_name}'")

    strategy = cls(symbol=symbol, config=config or {})

    capital = initial_capital
    position_size = 0.0        # units of base asset held
    entry_price = 0.0
    trades: list[dict] = []
    equity_curve: list[dict] = []

    for bar in ohlcv:
        candle = Candle(
            time=bar["time"],
            open=float(bar["open"]),
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
            volume=float(bar["volume"]),
            symbol=symbol,
            is_closed=True,
        )
        signal = strategy.on_candle(candle)
        price = candle.close

        if signal.action == SignalAction.BUY and position_size == 0:
            # Invest 100% of available capital
            position_size = capital / price
            entry_price = price
            capital = 0.0
            trades.append({
                "time": candle.time,
                "side": "BUY",
                "price": price,
                "pnl": 0.0,
            })

        elif signal.action == SignalAction.SELL and position_size > 0:
            proceeds = position_size * price
            pnl = proceeds - (position_size * entry_price)
            capital = proceeds
            trades.append({
                "time": candle.time,
                "side": "SELL",
                "price": price,
                "pnl": round(pnl, 4),
            })
            position_size = 0.0
            entry_price = 0.0

        # Mark-to-market equity
        current_equity = capital + position_size * price
        equity_curve.append({"time": candle.time // 1000, "value": round(current_equity, 2)})

    # Close any open position at last price
    if position_size > 0 and ohlcv:
        last_price = float(ohlcv[-1]["close"])
        proceeds = position_size * last_price
        pnl = proceeds - (position_size * entry_price)
        capital = proceeds
        trades.append({
            "time": ohlcv[-1]["time"],
            "side": "SELL (close)",
            "price": last_price,
            "pnl": round(pnl, 4),
        })

    # ── Metrics ──────────────────────────────────────────────────────────────

    final_capital = capital
    total_return_pct = ((final_capital - initial_capital) / initial_capital) * 100

    # Max drawdown from equity curve
    peak = initial_capital
    max_dd = 0.0
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Win rate from completed round-trips (every SELL after a BUY)
    sell_trades = [t for t in trades if "SELL" in t["side"]]
    winning = [t for t in sell_trades if t["pnl"] > 0]
    losing = [t for t in sell_trades if t["pnl"] <= 0]
    win_rate = (len(winning) / len(sell_trades) * 100) if sell_trades else 0.0

    # Simplified Sharpe ratio (annualised, assuming each bar = 1 interval unit)
    sharpe = _sharpe(equity_curve, initial_capital, interval)

    return BacktestResult(
        strategy=strategy_name.upper(),
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=round(final_capital, 2),
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd * 100, 2),
        win_rate_pct=round(win_rate, 1),
        total_trades=len(sell_trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        equity_curve=equity_curve,
        trades=trades,
    )


def _sharpe(equity_curve: list[dict], initial: float, interval: str) -> float:
    """
    Annualised Sharpe ratio (risk-free rate = 0).
    Bars-per-year lookup for common intervals.
    """
    if len(equity_curve) < 2:
        return 0.0

    bars_per_year = {
        "1m": 525_600,
        "5m": 105_120,
        "15m": 35_040,
        "30m": 17_520,
        "1h": 8_760,
        "4h": 2_190,
        "1d": 365,
    }.get(interval, 8_760)

    values = [pt["value"] for pt in equity_curve]
    returns = [(values[i] - values[i - 1]) / values[i - 1]
               for i in range(1, len(values)) if values[i - 1] != 0]
    if not returns:
        return 0.0

    import math
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std_r = math.sqrt(variance) if variance > 0 else 0.0

    if std_r == 0:
        return 0.0
    return (mean_r / std_r) * math.sqrt(bars_per_year)
