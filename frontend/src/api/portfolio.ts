import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Portfolio {
  total_value_usd: number;
  available_usd: number;
  holdings: Record<string, number>;
  open_positions: number;
  pnl_usd: number;
  pnl_pct: number;
  paper_mode: boolean;
  risk_halted: boolean;
}

export interface AllocationTarget {
  symbol: string;
  target_pct: number;
}

export interface AllocationResponse {
  targets: AllocationTarget[];
  total_pct: number;
}

export interface RebalanceTrade {
  symbol: string;
  side: "BUY" | "SELL";
  amount_usd: number;
  current_pct: number;
  target_pct: number;
  current_value_usd: number;
  target_value_usd: number;
}

export interface RebalancePreview {
  trades: RebalanceTrade[];
  message?: string;
}

export interface CorrelationResponse {
  symbols: string[];
  matrix: Record<string, Record<string, number>>;
  interval: string;
  data_points: Record<string, number>;
}

export async function fetchPortfolio(): Promise<Portfolio> {
  const res = await fetch(`${BASE}/api/portfolio`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch portfolio");
  return res.json();
}

export async function fetchAllocation(): Promise<AllocationResponse> {
  const res = await fetch(`${BASE}/api/portfolio/allocation`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to fetch allocation");
  return res.json();
}

export async function setAllocation(
  targets: AllocationTarget[]
): Promise<void> {
  const res = await fetch(`${BASE}/api/portfolio/allocation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ targets }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Failed to save allocation");
  }
}

export async function fetchWeights(): Promise<Record<string, number>> {
  const res = await fetch(`${BASE}/api/portfolio/weights`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to fetch weights");
  const data = await res.json();
  return data.weights;
}

export async function fetchRebalancePreview(): Promise<RebalancePreview> {
  const res = await fetch(`${BASE}/api/portfolio/rebalance`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to fetch rebalance preview");
  return res.json();
}

export async function executeRebalance(): Promise<{
  executed: number;
  orders: unknown[];
}> {
  const res = await fetch(`${BASE}/api/portfolio/rebalance`, {
    method: "POST",
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to execute rebalance");
  return res.json();
}

export async function fetchCorrelation(
  symbols = "BTCUSDT,ETHUSDT,SOLUSDT",
  interval = "1h",
  limit = 100
): Promise<CorrelationResponse> {
  const params = new URLSearchParams({ symbols, interval, limit: String(limit) });
  const res = await fetch(`${BASE}/api/portfolio/correlation?${params}`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to fetch correlation");
  return res.json();
}
