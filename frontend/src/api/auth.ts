import { getToken } from "../store/authStore";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  is_superuser: boolean;
}

export async function register(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Registration failed");
  }
  return res.json();
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Login failed");
  }
  return res.json();
}

export async function fetchMe(): Promise<UserResponse> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error("Unauthorized");
  return res.json();
}

export function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
