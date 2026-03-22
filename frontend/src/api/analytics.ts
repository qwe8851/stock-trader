const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface StrategyPerformance {
  strategy: string;
  total_trades: number;
  completed_trades: number;
  win_rate: number;
  total_pnl_usd: number;
  total_pnl_pct: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  profit_factor: number | null;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  gross_profit: number;
  gross_loss: number;
}

export interface AnalyticsSummary extends StrategyPerformance {
  portfolio_value: number;
  available_usd: number;
  exchange: string;
  paper_mode: boolean;
}

export interface PnlPoint {
  time: string;
  total_value_usd: number;
  available_usd: number;
  open_positions: number;
}

export async function fetchPerformance(): Promise<StrategyPerformance[]> {
  const res = await fetch(`${BASE}/api/analytics/performance`);
  if (!res.ok) throw new Error("Failed to fetch performance");
  return res.json();
}

export async function fetchSummary(): Promise<AnalyticsSummary> {
  const res = await fetch(`${BASE}/api/analytics/summary`);
  if (!res.ok) throw new Error("Failed to fetch summary");
  return res.json();
}

export async function fetchPnlHistory(limit = 168): Promise<PnlPoint[]> {
  const res = await fetch(`${BASE}/api/analytics/pnl-history?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch P&L history");
  return res.json();
}
