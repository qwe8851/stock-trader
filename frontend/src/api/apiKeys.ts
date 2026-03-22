import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ApiKeyInfo {
  exchange: string;
  access_key_preview: string;
}

export async function listApiKeys(): Promise<ApiKeyInfo[]> {
  const res = await fetch(`${BASE}/api/keys`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch API keys");
  return res.json();
}

export async function saveApiKey(
  exchange: string,
  access_key: string,
  secret_key: string
): Promise<void> {
  const res = await fetch(`${BASE}/api/keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ exchange, access_key, secret_key }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to save API key");
  }
}

export async function deleteApiKey(exchange: string): Promise<void> {
  const res = await fetch(`${BASE}/api/keys/${exchange}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Failed to delete API key");
}
