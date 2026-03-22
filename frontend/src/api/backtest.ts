import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface BacktestRequest {
  strategy: string;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  config?: Record<string, unknown>;
}

export interface EquityPoint {
  time: number;   // Unix seconds
  value: number;
}

export interface BacktestMetrics {
  strategy: string;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  equity_curve: EquityPoint[];
  trades: Array<{ time: number; side: string; price: number; pnl: number }>;
}

export interface BacktestStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  result?: BacktestMetrics;
  error?: string;
}

export interface BacktestSummary {
  task_id: string;
  status: string;
  strategy: string;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  total_return_pct: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  total_trades: number | null;
  created_at: string;
}

export async function submitBacktest(req: BacktestRequest): Promise<{ task_id: string }> {
  const res = await fetch(`${BASE}/api/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? "Failed to submit backtest");
  }
  return res.json();
}

export async function getBacktestStatus(taskId: string): Promise<BacktestStatusResponse> {
  const res = await fetch(`${BASE}/api/backtest/${taskId}`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch backtest status");
  return res.json();
}

export async function listBacktests(): Promise<BacktestSummary[]> {
  const res = await fetch(`${BASE}/api/backtest`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to list backtests");
  const data = await res.json();
  return data.results;
}
