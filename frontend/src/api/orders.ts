import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Order {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  size_usd: number;
  status: string;
  mode: "PAPER" | "LIVE";
  strategy: string;
  reason: string;
  created_at: string;
}

export async function fetchOrders(limit = 50): Promise<Order[]> {
  const res = await fetch(`${BASE}/api/orders?limit=${limit}`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch orders");
  const data = await res.json();
  return data.orders;
}
