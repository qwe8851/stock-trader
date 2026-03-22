"""
Performance analytics service.

주문 이력을 분석하여 전략별 성과 지표를 계산합니다.

지표:
  - total_trades   : 총 거래 수
  - win_rate       : 승률 (수익 거래 / 전체 완성된 거래)
  - total_pnl_usd  : 총 손익 (USD)
  - total_pnl_pct  : 총 수익률 (%)
  - avg_win_usd    : 평균 수익 거래 금액
  - avg_loss_usd   : 평균 손실 거래 금액
  - profit_factor  : 총 수익 / 총 손실 (>1이 좋음)
  - sharpe_ratio   : 일별 수익률의 Sharpe ratio
  - max_drawdown   : 최대 낙폭 (%)
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def compute_strategy_performance(
    orders: list[dict[str, Any]],
    initial_balance: float = 10_000.0,
) -> list[dict[str, Any]]:
    """
    전략별 성과를 계산합니다.

    Args:
        orders: OrderManager.get_orders() 형식의 주문 목록
        initial_balance: 초기 자금 (기본 $10,000)

    Returns:
        전략 이름별 성과 dict 리스트
    """
    # 전략별로 주문 분류
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for o in orders:
        strat = o.get("strategy") or "Unknown"
        by_strategy[strat].append(o)

    results = []
    for strategy_name, strat_orders in by_strategy.items():
        perf = _calc_performance(strat_orders, initial_balance, strategy_name)
        results.append(perf)

    # P&L 순으로 정렬
    results.sort(key=lambda x: x["total_pnl_usd"], reverse=True)
    return results


def compute_overall_performance(
    orders: list[dict[str, Any]],
    initial_balance: float = 10_000.0,
) -> dict[str, Any]:
    """전체 (전략 합산) 성과를 계산합니다."""
    return _calc_performance(orders, initial_balance, "Overall")


def _calc_performance(
    orders: list[dict[str, Any]],
    initial_balance: float,
    name: str,
) -> dict[str, Any]:
    if not orders:
        return _empty_perf(name)

    # BUY-SELL 쌍을 매칭하여 실현 손익 계산
    symbol_positions: dict[str, list[dict]] = defaultdict(list)
    for o in sorted(orders, key=lambda x: x.get("created_at", "")):
        symbol_positions[o["symbol"]].append(o)

    trades: list[dict] = []   # 완결된 거래 (BUY+SELL 쌍)
    pnl_series: list[float] = []

    for symbol, sym_orders in symbol_positions.items():
        buy_stack: list[dict] = []
        for o in sym_orders:
            if o["side"].upper() == "BUY":
                buy_stack.append(o)
            elif o["side"].upper() == "SELL" and buy_stack:
                buy = buy_stack.pop(0)
                entry = buy.get("price", 0)
                exit_p = o.get("price", 0)
                qty = min(buy.get("quantity", 0), o.get("quantity", 0))
                pnl = (exit_p - entry) * qty
                pnl_pct = (exit_p - entry) / entry * 100 if entry > 0 else 0
                trades.append({
                    "symbol": symbol,
                    "entry_price": entry,
                    "exit_price": exit_p,
                    "quantity": qty,
                    "pnl_usd": pnl,
                    "pnl_pct": pnl_pct,
                    "created_at": o.get("created_at", ""),
                })
                pnl_series.append(pnl)

    total_trades = len(orders)
    completed = len(trades)
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]

    win_rate = len(wins) / completed if completed > 0 else 0.0
    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_pnl_pct = total_pnl / initial_balance * 100

    avg_win = sum(t["pnl_usd"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["pnl_usd"] for t in losses) / len(losses) if losses else 0.0

    gross_profit = sum(t["pnl_usd"] for t in wins) if wins else 0.0
    gross_loss = abs(sum(t["pnl_usd"] for t in losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    sharpe = _sharpe_ratio(pnl_series)
    max_dd = _max_drawdown(pnl_series, initial_balance)

    return {
        "strategy": name,
        "total_trades": total_trades,
        "completed_trades": completed,
        "win_rate": round(win_rate, 4),
        "total_pnl_usd": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }


def _sharpe_ratio(pnl_series: list[float], risk_free: float = 0.0) -> float:
    """연간화 Sharpe ratio (일별 손익 기준)."""
    if len(pnl_series) < 2:
        return 0.0
    n = len(pnl_series)
    mean = sum(pnl_series) / n
    variance = sum((x - mean) ** 2 for x in pnl_series) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    # 거래 단위이므로 연간화는 sqrt(252) 사용 (일별 가정)
    return (mean - risk_free) / std * math.sqrt(252)


def _max_drawdown(pnl_series: list[float], initial_balance: float) -> float:
    """최대 낙폭 (% 기준)."""
    if not pnl_series:
        return 0.0
    equity = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for pnl in pnl_series:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _empty_perf(name: str) -> dict[str, Any]:
    return {
        "strategy": name,
        "total_trades": 0,
        "completed_trades": 0,
        "win_rate": 0.0,
        "total_pnl_usd": 0.0,
        "total_pnl_pct": 0.0,
        "avg_win_usd": 0.0,
        "avg_loss_usd": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
    }
