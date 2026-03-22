"""
Portfolio Allocation Service

목표 비중 대비 현재 비중의 차이를 계산하고
리밸런싱에 필요한 거래 목록을 반환합니다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RebalanceTrade:
    symbol: str
    side: str               # "BUY" | "SELL"
    amount_usd: float
    current_pct: float
    target_pct: float
    current_value_usd: float
    target_value_usd: float


def compute_rebalance(
    holdings: dict[str, float],         # asset → qty  e.g. {"BTC": 0.001}
    available_usd: float,
    prices: dict[str, float],           # symbol → price  e.g. {"BTCUSDT": 50000}
    targets: dict[str, float],          # symbol → target_%  e.g. {"BTCUSDT": 50.0}
    min_trade_usd: float = 10.0,
) -> list[RebalanceTrade]:
    """
    Compute the list of trades required to bring the portfolio
    from its current allocation to the target allocation.

    Only generates a trade when |delta| >= min_trade_usd.
    """
    # Total portfolio value
    holdings_value = sum(
        qty * prices.get(asset + "USDT", 0.0)
        for asset, qty in holdings.items()
    )
    total = available_usd + holdings_value
    if total <= 0:
        return []

    trades: list[RebalanceTrade] = []
    for symbol, target_pct in targets.items():
        base_asset = symbol.replace("USDT", "")
        price = prices.get(symbol, 0.0)
        if price <= 0:
            continue

        qty = holdings.get(base_asset, 0.0)
        current_value = qty * price
        current_pct = (current_value / total) * 100.0
        target_value = total * (target_pct / 100.0)
        delta = target_value - current_value

        if abs(delta) < min_trade_usd:
            continue

        trades.append(
            RebalanceTrade(
                symbol=symbol,
                side="BUY" if delta > 0 else "SELL",
                amount_usd=round(abs(delta), 2),
                current_pct=round(current_pct, 2),
                target_pct=target_pct,
                current_value_usd=round(current_value, 2),
                target_value_usd=round(target_value, 2),
            )
        )

    # Execute SELLs first to free up cash
    trades.sort(key=lambda t: 0 if t.side == "SELL" else 1)
    return trades


def compute_current_weights(
    holdings: dict[str, float],
    available_usd: float,
    prices: dict[str, float],
) -> dict[str, float]:
    """
    Return {symbol: current_pct} for all held assets plus unallocated cash.
    """
    holdings_value = sum(
        qty * prices.get(asset + "USDT", 0.0)
        for asset, qty in holdings.items()
    )
    total = available_usd + holdings_value
    if total <= 0:
        return {}

    weights: dict[str, float] = {}
    for asset, qty in holdings.items():
        price = prices.get(asset + "USDT", 0.0)
        value = qty * price
        weights[asset + "USDT"] = round((value / total) * 100.0, 2)

    weights["CASH"] = round((available_usd / total) * 100.0, 2)
    return weights
