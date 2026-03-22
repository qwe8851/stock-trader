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

export async function fetchPortfolio(): Promise<Portfolio> {
  const res = await fetch(`${BASE}/api/portfolio`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch portfolio");
  return res.json();
}
