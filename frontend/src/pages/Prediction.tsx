/**
 * Prediction page — LSTM price forecasting
 *
 * Layout:
 *  ┌──────────────────────────────────────────────────┐
 *  │  Train form (left) │ Model list (right)          │
 *  ├──────────────────────────────────────────────────┤
 *  │  Prediction chart  (historical + forecast + CI)  │
 *  └──────────────────────────────────────────────────┘
 */
import { useState, useEffect, useRef, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { createChart, type IChartApi, type ISeriesApi, LineStyle } from "lightweight-charts";
import { clsx } from "clsx";
import {
  submitTraining,
  getTrainingStatus,
  listModels,
  runPrediction,
  type ModelInfo,
  type PredPoint,
} from "../api/prediction";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 4): string {
  return n == null ? "—" : n.toFixed(dec);
}

const DEFAULT_FORM = {
  symbol: "BTCUSDT",
  interval: "1h",
  start_date: "2024-01-01",
  end_date: "2024-12-31",
  seq_len: 60,
  epochs: 100,
  hidden_size: 64,
  num_layers: 2,
};

// ── Prediction Chart ──────────────────────────────────────────────────────────

function PredictionChart({
  predictions,
  symbol,
}: {
  predictions: PredPoint[];
  symbol: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const meanRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const highRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    chartRef.current = createChart(containerRef.current, {
      layout: {
        background: { color: "#141414" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f1f1f" },
        horzLines: { color: "#1f1f1f" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#374151" },
      timeScale: { borderColor: "#374151", timeVisible: true },
      height: 360,
    });

    // Mean prediction line
    meanRef.current = chartRef.current.addLineSeries({
      color: "#6366f1",
      lineWidth: 2,
      title: `${symbol} forecast`,
    });

    // Upper bound (dashed)
    highRef.current = chartRef.current.addLineSeries({
      color: "#6366f1",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: "95% upper",
    });

    // Lower bound (dashed)
    lowRef.current = chartRef.current.addLineSeries({
      color: "#6366f1",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: "95% lower",
    });

    return () => {
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [symbol]);

  useEffect(() => {
    if (!predictions.length || !meanRef.current) return;

    const toSec = (ms: number) => Math.floor(ms / 1000) as unknown as import("lightweight-charts").Time;

    meanRef.current.setData(
      predictions.map((p) => ({ time: toSec(p.timestamp_ms), value: p.price }))
    );
    highRef.current?.setData(
      predictions.map((p) => ({ time: toSec(p.timestamp_ms), value: p.price_high }))
    );
    lowRef.current?.setData(
      predictions.map((p) => ({ time: toSec(p.timestamp_ms), value: p.price_low }))
    );

    chartRef.current?.timeScale().fitContent();
  }, [predictions]);

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Prediction() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [trainStatus, setTrainStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [trainError, setTrainError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [horizon, setHorizon] = useState(24);
  const [predictions, setPredictions] = useState<PredPoint[]>([]);
  const [predError, setPredError] = useState<string | null>(null);
  const [predLoading, setPredLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: models, refetch: refetchModels } = useQuery({
    queryKey: ["ml-models"],
    queryFn: listModels,
    refetchInterval: 15_000,
  });

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function handleTrain(e: FormEvent) {
    e.preventDefault();
    setTrainError(null);
    setTrainStatus("running");
    try {
      const res = await submitTraining({ ...form });
      startPolling(res.task_id);
    } catch (err: unknown) {
      setTrainError(err instanceof Error ? err.message : "Submission failed");
      setTrainStatus("failed");
    }
  }

  function startPolling(id: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await getTrainingStatus(id);
        if (s.status === "completed") {
          setTrainStatus("completed");
          clearInterval(pollRef.current!);
          refetchModels();
        } else if (s.status === "failed") {
          setTrainError("Training failed");
          setTrainStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch { /* keep polling */ }
    }, 4000);
  }

  async function handlePredict() {
    if (!selectedModel) return;
    setPredError(null);
    setPredLoading(true);
    setPredictions([]);
    try {
      const res = await runPrediction(selectedModel.task_id, horizon);
      setPredictions(res.predictions);
    } catch (err: unknown) {
      setPredError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setPredLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* ── Header ── */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white">
              <path d="M3 17l4-8 4 5 3-3 4 6" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="font-semibold text-lg tracking-tight">
            Stock<span className="text-brand">Trader</span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {[
            { label: "대시보드", to: "/dashboard" },
            { label: "분석", to: "/analytics" },
            { label: "최적화", to: "/optimization" },
            { label: "백테스트", to: "/backtest" },
            { label: "설정", to: "/settings" },
          ].map(({ label, to }) => (
            <Link key={to} to={to}
              className="px-3 py-1.5 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors">
              {label}
            </Link>
          ))}
        </div>
      </header>

      <div className="px-6 py-6 flex-1 space-y-6">
        <div>
          <h1 className="text-xl font-semibold">LSTM 가격 예측</h1>
          <p className="text-sm text-gray-500 mt-1">
            PyTorch LSTM + MC Dropout으로 미래 가격과 95% 신뢰 구간을 예측합니다.
          </p>
        </div>

        {/* ── Train + Model list ── */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Train form */}
          <div className="lg:col-span-2 card p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
              모델 학습
            </h2>

            {trainError && (
              <div className="px-3 py-2 rounded bg-bear/10 border border-bear/30 text-bear text-sm">
                {trainError}
              </div>
            )}
            {trainStatus === "completed" && (
              <div className="px-3 py-2 rounded bg-bull/10 border border-bull/30 text-bull text-sm">
                학습 완료! 아래 모델 목록에서 선택하세요.
              </div>
            )}

            <form onSubmit={handleTrain} className="space-y-3">
              {/* Symbol + Interval */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">심볼</label>
                  <select value={form.symbol}
                    onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand">
                    {["BTCUSDT", "ETHUSDT", "SOLUSDT"].map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">인터벌</label>
                  <select value={form.interval}
                    onChange={(e) => setForm((f) => ({ ...f, interval: e.target.value }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand">
                    {["15m", "1h", "4h", "1d"].map((i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Dates */}
              <div className="grid grid-cols-2 gap-3">
                {(["start_date", "end_date"] as const).map((key) => (
                  <div key={key}>
                    <label className="block text-xs text-gray-400 mb-1">
                      {key === "start_date" ? "시작일" : "종료일"}
                    </label>
                    <input type="date" value={form[key]}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                      className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                                 text-sm text-white focus:outline-none focus:border-brand" />
                  </div>
                ))}
              </div>

              {/* Hyperparameters */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Seq Len</label>
                  <input type="number" min={20} max={200} value={form.seq_len}
                    onChange={(e) => setForm((f) => ({ ...f, seq_len: Number(e.target.value) }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Epochs</label>
                  <input type="number" min={10} max={500} value={form.epochs}
                    onChange={(e) => setForm((f) => ({ ...f, epochs: Number(e.target.value) }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Hidden Size</label>
                  <select value={form.hidden_size}
                    onChange={(e) => setForm((f) => ({ ...f, hidden_size: Number(e.target.value) }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand">
                    {[16, 32, 64, 128, 256].map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Layers</label>
                  <select value={form.num_layers}
                    onChange={(e) => setForm((f) => ({ ...f, num_layers: Number(e.target.value) }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand">
                    {[1, 2, 3, 4].map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>

              <button type="submit" disabled={trainStatus === "running"}
                className="w-full bg-brand hover:bg-brand/90 disabled:opacity-50
                           text-white text-sm font-medium py-2 rounded-lg transition-colors">
                {trainStatus === "running" ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-white/40 animate-pulse" />
                    학습 중…
                  </span>
                ) : "학습 시작"}
              </button>
            </form>

            <div className="text-xs text-gray-600 space-y-0.5">
              <div>아키텍처: LSTM({form.hidden_size}×{form.num_layers}) → Linear(1)</div>
              <div>피처: close_norm, vol_norm, return%, RSI/100</div>
              <div>불확실성: MC Dropout × 30 samples → 95% CI</div>
            </div>
          </div>

          {/* Model list */}
          <div className="lg:col-span-3 card p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              학습된 모델
            </h2>
            {(!models || models.length === 0) ? (
              <div className="text-sm text-gray-600 py-8 text-center">
                아직 학습된 모델이 없습니다.
              </div>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {models.map((m) => (
                  <ModelRow
                    key={m.task_id}
                    model={m}
                    selected={selectedModel?.task_id === m.task_id}
                    onSelect={() => {
                      setSelectedModel(m);
                      setPredictions([]);
                      setPredError(null);
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Prediction controls ── */}
        {selectedModel && selectedModel.status === "completed" && (
          <div className="card p-5">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <span className="text-sm text-gray-300 font-medium">
                  {selectedModel.symbol} · {selectedModel.interval} · val_loss{" "}
                  <span className="text-brand">{fmt(selectedModel.val_loss)}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-400">예측 스텝:</label>
                <select value={horizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                  className="bg-surface-100 border border-gray-700 rounded-lg px-3 py-1.5
                             text-sm text-white focus:outline-none focus:border-brand">
                  {[6, 12, 24, 48, 72, 168].map((v) => (
                    <option key={v} value={v}>{v} candles</option>
                  ))}
                </select>
              </div>
              <button onClick={handlePredict} disabled={predLoading}
                className="px-4 py-1.5 bg-brand hover:bg-brand/90 disabled:opacity-50
                           text-white text-sm font-medium rounded-lg transition-colors">
                {predLoading ? "예측 중…" : "예측 실행"}
              </button>
              {predError && (
                <span className="text-bear text-sm">{predError}</span>
              )}
            </div>
          </div>
        )}

        {/* ── Prediction chart ── */}
        {predictions.length > 0 && (
          <div className="card p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                가격 예측 — {selectedModel?.symbol} 다음 {horizon} candles
              </h2>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <span className="w-6 h-0.5 bg-brand inline-block" />예측 (평균)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-6 h-0.5 bg-brand/40 inline-block border-dashed border-t" />
                  95% CI
                </span>
              </div>
            </div>

            <PredictionChart
              predictions={predictions}
              symbol={selectedModel?.symbol ?? ""}
            />

            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              {(() => {
                const first = predictions[0];
                const last = predictions[predictions.length - 1];
                const chg = ((last.price - first.price) / first.price) * 100;
                const avgSpread = predictions.reduce(
                  (s, p) => s + (p.price_high - p.price_low), 0
                ) / predictions.length;
                return [
                  { label: "예측 시작가", value: `$${first.price.toLocaleString()}` },
                  { label: "예측 종가", value: `$${last.price.toLocaleString()}` },
                  {
                    label: "예측 변화",
                    value: `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`,
                    cls: chg >= 0 ? "text-bull" : "text-bear",
                  },
                  { label: "평균 불확실성 ($)", value: `±${(avgSpread / 2).toFixed(0)}` },
                ];
              })().map(({ label, value, cls }) => (
                <div key={label} className="bg-surface-100 rounded-lg px-3 py-3">
                  <div className="text-xs text-gray-500 mb-1 uppercase tracking-wider">{label}</div>
                  <div className={clsx("font-mono text-base font-semibold", cls ?? "text-white")}>
                    {value}
                  </div>
                </div>
              ))}
            </div>

            {/* Prediction table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800">
                    {["Step", "예측가", "하한 (95%)", "상한 (95%)", "불확실성"].map((h) => (
                      <th key={h} className="text-left py-2 px-2 text-gray-500 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {predictions.map((p) => (
                    <tr key={p.step} className="border-b border-gray-800/50 hover:bg-surface-50">
                      <td className="py-1.5 px-2 text-gray-500 font-mono">+{p.step}</td>
                      <td className="py-1.5 px-2 text-white font-mono">
                        ${p.price.toLocaleString()}
                      </td>
                      <td className="py-1.5 px-2 text-bear font-mono">
                        ${p.price_low.toLocaleString()}
                      </td>
                      <td className="py-1.5 px-2 text-bull font-mono">
                        ${p.price_high.toLocaleString()}
                      </td>
                      <td className="py-1.5 px-2 text-gray-400 font-mono">
                        ±${((p.price_high - p.price_low) / 2).toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <footer className="border-t border-gray-800 px-6 py-3 text-xs text-gray-600 flex justify-between">
        <span>Phase 8 · LSTM Price Prediction · MC Dropout Uncertainty</span>
        <span>{new Date().toLocaleDateString()}</span>
      </footer>
    </div>
  );
}


// ── Sub-components ────────────────────────────────────────────────────────────

function ModelRow({
  model, selected, onSelect,
}: { model: ModelInfo; selected: boolean; onSelect: () => void }) {
  const statusCls = {
    completed: "text-bull",
    running: "text-brand animate-pulse",
    failed: "text-bear",
    pending: "text-gray-500",
  }[model.status] ?? "text-gray-500";

  return (
    <button
      onClick={onSelect}
      disabled={model.status !== "completed"}
      className={clsx(
        "w-full text-left px-3 py-2.5 rounded-lg border transition-colors",
        selected
          ? "border-brand bg-brand/10"
          : "border-gray-700 hover:border-gray-600 hover:bg-surface-50",
        model.status !== "completed" && "opacity-60 cursor-default"
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-white">
          {model.symbol} · {model.interval}
        </span>
        <span className={clsx("text-xs font-medium", statusCls)}>
          {model.status}
        </span>
      </div>
      <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-3">
        <span>hidden={model.hidden_size} layers={model.num_layers} seq={model.seq_len}</span>
        {model.val_loss != null && (
          <span>val_loss=<span className="text-gray-400">{model.val_loss.toFixed(4)}</span></span>
        )}
        {model.epochs_trained != null && (
          <span>epochs=<span className="text-gray-400">{model.epochs_trained}</span></span>
        )}
      </div>
    </button>
  );
}
