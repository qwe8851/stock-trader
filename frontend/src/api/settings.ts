const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ExchangeSettings {
  exchange: "binance" | "upbit";
  paper_mode: boolean;
  live_trading_enabled: boolean;
  risk_halted: boolean;
  credentials: {
    binance: { has_credentials: boolean; testnet: boolean };
    upbit: { has_credentials: boolean };
  };
}

export async function fetchSettings(): Promise<ExchangeSettings> {
  const res = await fetch(`${BASE}/api/settings`);
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function switchExchange(exchange: "binance" | "upbit"): Promise<void> {
  const res = await fetch(`${BASE}/api/settings/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ exchange }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to switch exchange");
  }
}

export async function toggleLiveTrading(
  enabled: boolean,
  confirm: boolean
): Promise<void> {
  const res = await fetch(`${BASE}/api/settings/live-trading`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, confirm }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to toggle live trading");
  }
}
