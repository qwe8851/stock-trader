import { authHeader } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface TrainRequest {
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  seq_len: number;
  epochs: number;
  hidden_size: number;
  num_layers: number;
}

export interface ModelInfo {
  task_id: string;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  seq_len: number;
  hidden_size: number;
  num_layers: number;
  epochs_trained: number | null;
  n_train_samples: number | null;
  val_loss: number | null;
  status: string;
  created_at: string;
}

export interface PredPoint {
  step: number;
  timestamp_ms: number;
  price: number;
  price_low: number;
  price_high: number;
}

export interface PredictionResult {
  task_id: string;
  symbol: string;
  interval: string;
  horizon: number;
  seed_candles: number;
  predictions: PredPoint[];
}

export async function submitTraining(
  req: TrainRequest
): Promise<{ task_id: string; status: string; message: string }> {
  const res = await fetch(`${BASE}/api/ml/train`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to submit training");
  }
  return res.json();
}

export async function getTrainingStatus(
  taskId: string
): Promise<{ task_id: string; status: string; val_loss?: number; epochs_trained?: number }> {
  const res = await fetch(`${BASE}/api/ml/train/${taskId}`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to fetch training status");
  return res.json();
}

export async function listModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${BASE}/api/ml/models`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to list models");
  const data = await res.json();
  return data.models;
}

export async function runPrediction(
  taskId: string,
  horizon: number
): Promise<PredictionResult> {
  const res = await fetch(`${BASE}/api/ml/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ task_id: taskId, horizon }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Prediction failed");
  }
  return res.json();
}
