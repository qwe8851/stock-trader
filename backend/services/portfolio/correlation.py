"""
Asset Correlation Service

심볼별 가격 이력으로 로그 수익률을 계산한 뒤
Pearson 상관계수 행렬을 반환합니다.
"""
from __future__ import annotations

import math


def compute_correlation_matrix(
    price_histories: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """
    Compute pairwise Pearson correlation between log-return series.

    Args:
        price_histories: {symbol: [close_price, ...]} — at least 2 data points per symbol.

    Returns:
        Symmetric matrix {symbol_a: {symbol_b: correlation}} where diagonal = 1.0.
    """
    log_returns: dict[str, list[float]] = {}
    for symbol, prices in price_histories.items():
        if len(prices) < 2:
            continue
        rets = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0 and prices[i] > 0
        ]
        if rets:
            log_returns[symbol] = rets

    symbols = list(log_returns.keys())
    matrix: dict[str, dict[str, float]] = {}

    for s1 in symbols:
        matrix[s1] = {}
        for s2 in symbols:
            if s1 == s2:
                matrix[s1][s2] = 1.0
            else:
                r1 = log_returns[s1]
                r2 = log_returns[s2]
                n = min(len(r1), len(r2))
                matrix[s1][s2] = round(_pearson(r1[-n:], r2[-n:]), 4)

    return matrix


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0.0 or std_y == 0.0:
        return 0.0
    return cov / (std_x * std_y)
