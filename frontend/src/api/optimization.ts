import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface OptimizeRequest {
  strategy: string;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  n_trials: number;
  objective_metric: "sharpe" | "return" | "calmar";
  initial_capital: number;
}

export interface TrialSummary {
  trial: number;
  params: Record<string, number>;
  sharpe: number;
  return_pct: number;
  drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
  value: number;
}

export interface OptimizationResult {
  task_id: string;
  strategy: string;
  symbol: string;
  interval: string;
  n_trials: number;
  objective_metric: string;
  best_params: Record<string, number>;
  best_value: number;
  best_return_pct: number;
  best_sharpe: number;
  best_drawdown_pct: number;
  best_win_rate_pct: number;
  best_trades: number;
  trials_summary: TrialSummary[];
}

export interface OptimizationStatus {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  result?: OptimizationResult;
  error?: string;
}

export interface OptimizationSummary {
  task_id: string;
  strategy: string;
  symbol: string;
  interval: string;
  n_trials: number;
  objective_metric: string;
  best_value: number | null;
  best_return_pct: number | null;
  best_sharpe: number | null;
  best_params: Record<string, number> | null;
  status: string;
  created_at: string;
}

export async function submitOptimization(
  req: OptimizeRequest
): Promise<{ task_id: string; status: string; message: string }> {
  const res = await fetch(`${BASE}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to submit optimization");
  }
  return res.json();
}

export async function getOptimizationStatus(taskId: string): Promise<OptimizationStatus> {
  const res = await fetch(`${BASE}/api/optimize/${taskId}`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch optimization status");
  return res.json();
}

export async function listOptimizations(): Promise<OptimizationSummary[]> {
  const res = await fetch(`${BASE}/api/optimize`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to list optimizations");
  const data = await res.json();
  return data.results;
}
