"""
Strategy parameter optimizer using Optuna (TPE sampler).

The optimizer reuses the existing `run_backtest()` function as its
objective — it suggests parameter combinations, runs a fast backtest
over historical data, and maximises the chosen metric.

Supported strategies and their search spaces:
  RSI  — period, oversold, overbought
  MACD — fast, slow, signal
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import optuna

from services.backtesting.runner import run_backtest

# Silence Optuna's default progress output — we log ourselves
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ---------------------------------------------------------------------------
# Search spaces
# ---------------------------------------------------------------------------

def _rsi_space(trial: optuna.Trial) -> dict:
    period = trial.suggest_int("period", 5, 30)
    oversold = trial.suggest_float("oversold", 20.0, 45.0, step=1.0)
    overbought = trial.suggest_float("overbought", 55.0, 80.0, step=1.0)
    return {"period": period, "oversold": oversold, "overbought": overbought}


def _macd_space(trial: optuna.Trial) -> dict:
    fast = trial.suggest_int("fast", 5, 20)
    # slow must be > fast
    slow = trial.suggest_int("slow", fast + 5, fast + 30)
    signal = trial.suggest_int("signal", 3, 15)
    return {"fast": fast, "slow": slow, "signal": signal}


_SEARCH_SPACES: dict[str, Callable[[optuna.Trial], dict]] = {
    "RSI": _rsi_space,
    "MACD": _macd_space,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrialSummary:
    trial_number: int
    params: dict
    sharpe: float
    return_pct: float
    drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    value: float          # objective value (what was maximised)


@dataclass
class OptimizationResult:
    strategy: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    n_trials: int
    objective_metric: str
    best_params: dict
    best_value: float
    best_return_pct: float
    best_sharpe: float
    best_drawdown_pct: float
    best_win_rate_pct: float
    best_trades: int
    top_trials: list[TrialSummary] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def run_optimization(
    strategy_name: str,
    symbol: str,
    ohlcv: list[dict],
    n_trials: int = 50,
    objective_metric: str = "sharpe",   # "sharpe" | "return" | "calmar"
    interval: str = "1h",
    start_date: str = "",
    end_date: str = "",
    initial_capital: float = 10_000.0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> OptimizationResult:
    """
    Run an Optuna study over the given strategy's parameter space.

    ``objective_metric`` controls what is maximised:
      - "sharpe"  → Sharpe ratio  (default)
      - "return"  → total_return_pct
      - "calmar"  → return_pct / max_drawdown_pct  (risk-adjusted return)
    """
    name_upper = strategy_name.upper()
    suggest_fn = _SEARCH_SPACES.get(name_upper)
    if suggest_fn is None:
        raise ValueError(f"No search space defined for strategy '{strategy_name}'. "
                         f"Supported: {list(_SEARCH_SPACES)}")

    trial_results: list[TrialSummary] = []
    completed = [0]

    def objective(trial: optuna.Trial) -> float:
        config = suggest_fn(trial)
        try:
            result = run_backtest(
                strategy_name=name_upper,
                symbol=symbol,
                ohlcv=ohlcv,
                config=config,
                initial_capital=initial_capital,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception:
            return float("-inf")

        sharpe = result.sharpe_ratio
        ret = result.total_return_pct
        dd = result.max_drawdown_pct

        # Objective value
        if objective_metric == "return":
            value = ret
        elif objective_metric == "calmar":
            value = ret / dd if dd > 0 else ret
        else:  # "sharpe"
            value = sharpe if math.isfinite(sharpe) else float("-inf")

        trial_results.append(TrialSummary(
            trial_number=trial.number,
            params=config,
            sharpe=round(sharpe, 4),
            return_pct=round(ret, 2),
            drawdown_pct=round(dd, 2),
            win_rate_pct=round(result.win_rate_pct, 1),
            total_trades=result.total_trades,
            value=round(value, 4),
        ))

        completed[0] += 1
        if progress_callback:
            progress_callback(completed[0], n_trials)

        return value

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    best_config = _SEARCH_SPACES[name_upper].__wrapped__ if hasattr(
        _SEARCH_SPACES[name_upper], "__wrapped__") else None

    # Re-run the best config to get full metrics
    best_params = best.params
    best_result = run_backtest(
        strategy_name=name_upper,
        symbol=symbol,
        ohlcv=ohlcv,
        config=best_params,
        initial_capital=initial_capital,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )

    # Sort trials by objective value desc for the top-N summary
    top_trials = sorted(trial_results, key=lambda t: t.value, reverse=True)[:20]

    return OptimizationResult(
        strategy=name_upper,
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        n_trials=len(trial_results),
        objective_metric=objective_metric,
        best_params=best_params,
        best_value=round(best.value, 4),
        best_return_pct=round(best_result.total_return_pct, 2),
        best_sharpe=round(best_result.sharpe_ratio, 3),
        best_drawdown_pct=round(best_result.max_drawdown_pct, 2),
        best_win_rate_pct=round(best_result.win_rate_pct, 1),
        best_trades=best_result.total_trades,
        top_trials=top_trials,
    )
