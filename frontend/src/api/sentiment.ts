const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface NewsItem {
  title: string;
  source: string;
  url: string;
  published_at: string;
  sentiment_score: number | null;
}

export interface SentimentData {
  symbol: string;
  score: number;        // [-1, +1]
  label: "positive" | "negative" | "neutral";
  items: NewsItem[];
  updated_at: string;
  cached: boolean;
}

export async function fetchSentiment(symbol: string): Promise<SentimentData> {
  const res = await fetch(`${BASE}/api/sentiment/${symbol}`);
  if (!res.ok) throw new Error("Failed to fetch sentiment");
  return res.json();
}

export async function triggerSentimentRefresh(symbol: string): Promise<void> {
  await fetch(`${BASE}/api/sentiment/${symbol}/refresh`, { method: "POST" });
}
