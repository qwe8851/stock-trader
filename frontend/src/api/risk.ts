import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface StrategyRisk {
  strategy: string;
  cumulative_pnl: number;
  peak_pnl: number;
  drawdown_pct: number;
  paused: boolean;
  kelly_fraction: number;
}

export interface RiskConfig {
  max_position_pct: number;
  daily_loss_limit_pct: number;
  max_open_positions: number;
  use_kelly: boolean;
  half_kelly: boolean;
  kelly_lookback: number;
  strategy_drawdown_limit_pct: number;
  min_profit_pct: number;
  fee_pct: number;
}

export interface RiskMetrics {
  // Kelly
  kelly_raw: number;
  kelly_fraction: number;
  kelly_position_usd: number;
  kelly_lookback_trades: number;
  // VaR
  var_95_usd: number;
  var_95_pct: number;
  var_99_usd: number;
  var_99_pct: number;
  equity_curve_len: number;
  // Daily drawdown
  daily_drawdown_pct: number;
  daily_loss_limit_pct: number;
  // Circuit breaker
  halted: boolean;
  halt_reason: string;
  // Per-strategy
  strategy_risks: StrategyRisk[];
  // Config
  config: RiskConfig;
}

export interface RiskEvent {
  ts: string;
  type: string;
  detail: string;
  strategy?: string;
  pnl?: number;
}

export async function fetchRiskMetrics(): Promise<RiskMetrics> {
  const res = await fetch(`${BASE}/api/risk/metrics`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch risk metrics");
  return res.json();
}

export async function fetchRiskEvents(n = 50): Promise<RiskEvent[]> {
  const res = await fetch(`${BASE}/api/risk/events?n=${n}`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch risk events");
  const data = await res.json();
  return data.events;
}

export async function updateRiskConfig(
  updates: Partial<RiskConfig>
): Promise<void> {
  const res = await fetch(`${BASE}/api/risk/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update config");
  }
}

export async function resumeTrading(): Promise<void> {
  await fetch(`${BASE}/api/risk/resume`, { method: "POST", headers: authHeader() });
}

export async function resumeStrategy(strategy: string): Promise<void> {
  await fetch(`${BASE}/api/risk/resume/${strategy}`, {
    method: "POST",
    headers: authHeader(),
  });
}
