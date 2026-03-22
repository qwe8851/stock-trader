"""
LSTM price predictor.

Architecture:
  Input  : window of seq_len candles, 4 features each
           [close_norm, vol_norm, return_pct, rsi_norm]
  LSTM   : hidden=64, layers=2, dropout=0.2
  Output : next normalised close price (1 step, then autoregressive)

Training:
  - Min-max normalisation per feature (stored as Scaler for denorm)
  - Adam lr=0.001, MSE loss
  - Early stopping (patience=15)

Prediction:
  - Autoregressively generates `horizon` future steps
  - MC Dropout (model.train() during inference) × 30 samples → mean ± 2σ
"""
from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass, field

import torch
import torch.nn as nn
import numpy as np


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

class LSTMPredictor(nn.Module):
    INPUT_SIZE = 4

    def __init__(self, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            self.INPUT_SIZE,
            hidden_size,
            num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])  # last timestep → scalar


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _calc_rsi_series(closes: list[float], period: int = 14) -> list[float]:
    rsi = [50.0] * len(closes)
    for i in range(period + 1, len(closes)):
        deltas = [closes[j] - closes[j - 1] for j in range(i - period, i)]
        avg_gain = sum(d for d in deltas if d > 0) / period
        avg_loss = sum(-d for d in deltas if d < 0) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


@dataclass
class Scaler:
    close_min: float
    close_range: float
    vol_min: float
    vol_range: float

    def norm_close(self, v: float) -> float:
        return (v - self.close_min) / self.close_range

    def denorm_close(self, v: float) -> float:
        return v * self.close_range + self.close_min

    def to_dict(self) -> dict:
        return {
            "close_min": self.close_min,
            "close_range": self.close_range,
            "vol_min": self.vol_min,
            "vol_range": self.vol_range,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scaler":
        return cls(**d)


def _build_features(ohlcv: list[dict]) -> tuple[np.ndarray, Scaler]:
    """
    Returns (feature_array, scaler).
    Feature columns: [close_norm, vol_norm, return_clipped, rsi_norm]
    """
    closes = [float(c["close"]) for c in ohlcv]
    volumes = [float(c["volume"]) for c in ohlcv]

    c_min, c_max = min(closes), max(closes)
    v_min, v_max = min(volumes), max(volumes)
    c_range = (c_max - c_min) or 1.0
    v_range = (v_max - v_min) or 1.0
    scaler = Scaler(close_min=c_min, close_range=c_range, vol_min=v_min, vol_range=v_range)

    close_norm = [(c - c_min) / c_range for c in closes]
    vol_norm = [(v - v_min) / v_range for v in volumes]

    returns = [0.0] + [
        (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] != 0 else 0.0
        for i in range(1, len(closes))
    ]
    returns = [max(-0.2, min(0.2, r)) for r in returns]

    rsi_series = _calc_rsi_series(closes)
    rsi_norm = [r / 100.0 for r in rsi_series]

    features = np.array(
        list(zip(close_norm, vol_norm, returns, rsi_norm)), dtype=np.float32
    )
    return features, scaler


def _make_sequences(
    features: np.ndarray, seq_len: int
) -> tuple[torch.Tensor, torch.Tensor]:
    X, y = [], []
    for i in range(len(features) - seq_len):
        X.append(features[i : i + seq_len])
        y.append(features[i + seq_len, 0])  # target = next close_norm
    return (
        torch.tensor(np.array(X), dtype=torch.float32),
        torch.tensor(np.array(y), dtype=torch.float32).unsqueeze(1),
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@dataclass
class TrainResult:
    model_b64: str       # base64-encoded torch.save() bytes
    scaler: dict         # Scaler.to_dict()
    val_loss: float
    seq_len: int
    hidden_size: int
    num_layers: int
    epochs_trained: int
    n_train_samples: int


def train_model(
    ohlcv: list[dict],
    seq_len: int = 60,
    epochs: int = 100,
    hidden_size: int = 64,
    num_layers: int = 2,
    learning_rate: float = 0.001,
) -> TrainResult:
    features, scaler = _build_features(ohlcv)
    X, y = _make_sequences(features, seq_len)

    split = int(len(X) * 0.8)
    X_tr, y_tr = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    model = LSTMPredictor(hidden_size=hidden_size, num_layers=num_layers)
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.MSELoss()

    best_val = float("inf")
    best_state: dict | None = None
    patience = 15
    no_improve = 0
    actual_epochs = 0

    model.train()
    for ep in range(epochs):
        actual_epochs = ep + 1
        optimiser.zero_grad()
        loss = criterion(model(X_tr), y_tr)
        loss.backward()
        optimiser.step()

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_val), y_val).item()
        model.train()

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)

    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    model_b64 = base64.b64encode(buf.getvalue()).decode()

    return TrainResult(
        model_b64=model_b64,
        scaler=scaler.to_dict(),
        val_loss=round(best_val, 6),
        seq_len=seq_len,
        hidden_size=hidden_size,
        num_layers=num_layers,
        epochs_trained=actual_epochs,
        n_train_samples=split,
    )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

@dataclass
class PredPoint:
    step: int
    price: float        # denormalised mean prediction
    price_low: float    # mean − 2σ
    price_high: float   # mean + 2σ
    timestamp_ms: int   # approximate future Unix ms (seed_last_ts + step * interval_ms)


def predict_future(
    model_b64: str,
    scaler_dict: dict,
    seed_ohlcv: list[dict],
    seq_len: int,
    hidden_size: int,
    num_layers: int,
    horizon: int = 24,
    n_mc: int = 30,
    interval_ms: int = 3_600_000,   # 1h default
) -> list[PredPoint]:
    """
    Autoregressively predict `horizon` steps using MC Dropout.
    seed_ohlcv must contain at least seq_len candles.
    """
    scaler = Scaler.from_dict(scaler_dict)

    # Load model
    state = torch.load(
        io.BytesIO(base64.b64decode(model_b64)),
        map_location="cpu",
        weights_only=True,
    )
    model = LSTMPredictor(hidden_size=hidden_size, num_layers=num_layers)
    model.load_state_dict(state)

    # Build seed feature window
    features, _ = _build_features(seed_ohlcv)
    window: list[list[float]] = features[-seq_len:].tolist()

    last_ts = int(seed_ohlcv[-1]["time"])

    results: list[PredPoint] = []
    for step in range(1, horizon + 1):
        # MC Dropout: keep model in train mode so dropout is active
        model.train()
        preds: list[float] = []
        x = torch.tensor([window], dtype=torch.float32)
        with torch.no_grad():
            for _ in range(n_mc):
                preds.append(model(x).item())

        mean_norm = sum(preds) / len(preds)
        std_norm = math.sqrt(
            sum((p - mean_norm) ** 2 for p in preds) / len(preds)
        ) if len(preds) > 1 else 0.0

        price = scaler.denorm_close(mean_norm)
        price_low = scaler.denorm_close(mean_norm - 2 * std_norm)
        price_high = scaler.denorm_close(mean_norm + 2 * std_norm)

        results.append(
            PredPoint(
                step=step,
                price=round(price, 2),
                price_low=round(max(0.0, price_low), 2),
                price_high=round(price_high, 2),
                timestamp_ms=last_ts + step * interval_ms,
            )
        )

        # Build next feature row (approximate: use mean values for vol/rsi)
        prev_close_norm = window[-1][0]
        ret = (mean_norm - prev_close_norm) / (abs(prev_close_norm) + 1e-9)
        ret = max(-0.2, min(0.2, ret))
        avg_vol = float(sum(row[1] for row in window) / len(window))
        avg_rsi = float(sum(row[3] for row in window[-14:]) / min(14, len(window)))

        window = window[1:] + [[mean_norm, avg_vol, ret, avg_rsi]]

    return results


# ---------------------------------------------------------------------------
# Interval → milliseconds helper
# ---------------------------------------------------------------------------

INTERVAL_MS: dict[str, int] = {
    "1m":  60_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "4h":  14_400_000,
    "1d":  86_400_000,
}
