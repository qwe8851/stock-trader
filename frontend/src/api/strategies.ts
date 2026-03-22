import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface StrategyInfo {
  name: string;
  symbol: string;
  config: Record<string, unknown>;
  candles_loaded: number;
  min_candles: number;
  ready: boolean;
}

export async function fetchStrategies(): Promise<{
  strategies: StrategyInfo[];
  available: string[];
  status: unknown;
}> {
  const res = await fetch(`${BASE}/api/strategies`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch strategies");
  return res.json();
}

export async function addStrategy(
  name: string,
  symbol: string,
  config: Record<string, unknown> = {}
): Promise<void> {
  const res = await fetch(`${BASE}/api/strategies`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ name, symbol, config }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? "Failed to add strategy");
  }
}

export async function removeStrategy(name: string, symbol: string): Promise<void> {
  const res = await fetch(`${BASE}/api/strategies/${name}?symbol=${symbol}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to remove strategy");
}

export async function resumeTrading(): Promise<void> {
  await fetch(`${BASE}/api/strategies/resume`, { method: "POST", headers: authHeader() });
}
