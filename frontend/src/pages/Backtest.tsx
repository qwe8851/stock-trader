import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { createChart, type IChartApi, type ISeriesApi, LineStyle } from "lightweight-charts";
import {
  submitBacktest,
  getBacktestStatus,
  listBacktests,
  type BacktestMetrics,
  type BacktestSummary,
} from "../api/backtest";

const STRATEGIES = ["RSI", "MACD"];
const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const INTERVALS = ["1h", "4h", "1d"];

export default function Backtest() {
  const [form, setForm] = useState({
    strategy: "RSI",
    symbol: "BTCUSDT",
    interval: "1h",
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    initial_capital: 10000,
  });
  const [taskId, setTaskId] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [result, setResult] = useState<BacktestMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll task status
  useEffect(() => {
    if (!polling || !taskId) return;
    const interval = setInterval(async () => {
      try {
        const status = await getBacktestStatus(taskId);
        if (status.status === "completed" && status.result) {
          setResult(status.result);
          setPolling(false);
        } else if (status.status === "failed") {
          setError(status.error ?? "Backtest failed");
          setPolling(false);
        }
      } catch {
        // Keep polling on transient errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [polling, taskId]);

  const { data: history = [] } = useQuery({
    queryKey: ["backtest-list"],
    queryFn: listBacktests,
    refetchInterval: 10_000,
  });

  const submitMutation = useMutation({
    mutationFn: () => submitBacktest({ ...form }),
    onSuccess: (data) => {
      setTaskId(data.task_id);
      setResult(null);
      setError(null);
      setPolling(true);
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <div className="min-h-screen bg-surface text-white">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center text-white font-bold text-sm">B</div>
        <span className="font-semibold text-lg tracking-tight">
          Stock<span className="text-brand">Trader</span>
        </span>
        <nav className="ml-6 flex gap-4 text-sm text-gray-400">
          <a href="/dashboard" className="hover:text-white transition-colors">Dashboard</a>
          <a href="/backtest" className="text-white font-medium">Backtest</a>
        </nav>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <h1 className="text-2xl font-bold">Strategy Backtester</h1>

        {/* ── Form ─────────────────────────────────────────────── */}
        <div className="bg-surface-2 rounded-xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Configuration
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <Field label="Strategy">
              <select value={form.strategy} onChange={e => setForm(f => ({ ...f, strategy: e.target.value }))}
                className="input-field">
                {STRATEGIES.map(s => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Symbol">
              <select value={form.symbol} onChange={e => setForm(f => ({ ...f, symbol: e.target.value }))}
                className="input-field">
                {SYMBOLS.map(s => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Interval">
              <select value={form.interval} onChange={e => setForm(f => ({ ...f, interval: e.target.value }))}
                className="input-field">
                {INTERVALS.map(s => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Start Date">
              <input type="date" value={form.start_date}
                onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                className="input-field" />
            </Field>
            <Field label="End Date">
              <input type="date" value={form.end_date}
                onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                className="input-field" />
            </Field>
            <Field label="Capital ($)">
              <input type="number" value={form.initial_capital} min={100}
                onChange={e => setForm(f => ({ ...f, initial_capital: Number(e.target.value) }))}
                className="input-field" />
            </Field>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => submitMutation.mutate()}
              disabled={submitMutation.isPending || polling}
              className="bg-brand hover:bg-brand/80 disabled:opacity-50 text-white font-semibold px-6 py-2 rounded-lg transition-colors"
            >
              {polling ? "Running..." : submitMutation.isPending ? "Submitting..." : "Run Backtest"}
            </button>
            {polling && (
              <div className="flex items-center gap-2 text-yellow-400 text-sm">
                <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
                Fetching data & simulating strategy...
              </div>
            )}
            {error && <p className="text-red-400 text-sm">{error}</p>}
          </div>
        </div>

        {/* ── Results ──────────────────────────────────────────── */}
        {result && (
          <>
            <MetricsGrid result={result} />
            <EquityCurveChart result={result} />
          </>
        )}

        {/* ── History ──────────────────────────────────────────── */}
        <BacktestHistory history={history} onSelect={setResult} />
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-500">{label}</label>
      {children}
    </div>
  );
}

function MetricsGrid({ result }: { result: BacktestMetrics }) {
  const positive = result.total_return_pct >= 0;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
      <MetricCard label="Total Return" value={`${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct.toFixed(2)}%`}
        valueClass={positive ? "text-bull" : "text-bear"} />
      <MetricCard label="Final Capital" value={`$${result.final_capital.toLocaleString()}`} />
      <MetricCard label="Sharpe Ratio" value={result.sharpe_ratio.toFixed(3)}
        valueClass={result.sharpe_ratio >= 1 ? "text-bull" : result.sharpe_ratio >= 0 ? "text-white" : "text-bear"} />
      <MetricCard label="Max Drawdown" value={`-${result.max_drawdown_pct.toFixed(2)}%`} valueClass="text-bear" />
      <MetricCard label="Win Rate" value={`${result.win_rate_pct.toFixed(1)}%`}
        valueClass={result.win_rate_pct >= 50 ? "text-bull" : "text-bear"} />
      <MetricCard label="Total Trades" value={String(result.total_trades)} />
      <MetricCard label="W / L" value={`${result.winning_trades} / ${result.losing_trades}`} />
    </div>
  );
}

function MetricCard({ label, value, valueClass = "text-white" }: {
  label: string; value: string; valueClass?: string;
}) {
  return (
    <div className="bg-surface-2 rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold font-mono ${valueClass}`}>{value}</p>
    </div>
  );
}

function EquityCurveChart({ result }: { result: BacktestMetrics }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#12121a" }, textColor: "#9ca3af" },
      grid: { vertLines: { color: "#1f2937" }, horzLines: { color: "#1f2937" } },
      width: containerRef.current.clientWidth,
      height: 320,
      timeScale: { timeVisible: true },
    });
    chartRef.current = chart;

    const series = chart.addAreaSeries({
      lineColor: "#6366f1",
      topColor: "rgba(99,102,241,0.3)",
      bottomColor: "rgba(99,102,241,0.0)",
      lineWidth: 2,
    });
    seriesRef.current = series;

    if (result.equity_curve.length > 0) {
      series.setData(result.equity_curve as any);
      chart.timeScale().fitContent();
    }

    // Draw initial capital baseline
    const baseline = chart.addLineSeries({
      color: "#6b7280",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
    });
    baseline.setData(
      result.equity_curve.map(pt => ({ time: pt.time, value: result.initial_capital })) as any
    );

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [result]);

  return (
    <div className="bg-surface-2 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
        Equity Curve — {result.strategy} / {result.symbol} / {result.interval}
      </h2>
      <div ref={containerRef} />
    </div>
  );
}

function BacktestHistory({
  history,
}: {
  history: BacktestSummary[];
  onSelect?: (r: BacktestMetrics) => void;
}) {
  if (history.length === 0) return null;

  return (
    <div className="bg-surface-2 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
        History
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-left border-b border-white/5">
              <th className="pb-2 pr-4">Date</th>
              <th className="pb-2 pr-4">Strategy</th>
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4">Period</th>
              <th className="pb-2 pr-4">Return</th>
              <th className="pb-2 pr-4">Sharpe</th>
              <th className="pb-2 pr-4">MDD</th>
              <th className="pb-2">Trades</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {history.map((h) => (
              <tr key={h.task_id} className="hover:bg-white/5 transition-colors">
                <td className="py-2 pr-4 text-xs text-gray-500">
                  {new Date(h.created_at).toLocaleDateString()}
                </td>
                <td className="py-2 pr-4 font-medium">{h.strategy}</td>
                <td className="py-2 pr-4 text-gray-300">{h.symbol}</td>
                <td className="py-2 pr-4 text-gray-500 text-xs">
                  {h.start_date?.slice(0, 10)} ~ {h.end_date?.slice(0, 10)}
                </td>
                <td className={`py-2 pr-4 font-mono font-medium ${
                  (h.total_return_pct ?? 0) >= 0 ? "text-bull" : "text-bear"
                }`}>
                  {h.total_return_pct != null
                    ? `${h.total_return_pct >= 0 ? "+" : ""}${h.total_return_pct.toFixed(2)}%`
                    : "—"}
                </td>
                <td className="py-2 pr-4 text-gray-300 font-mono">
                  {h.sharpe_ratio?.toFixed(3) ?? "—"}
                </td>
                <td className="py-2 pr-4 text-bear font-mono">
                  {h.max_drawdown_pct != null ? `-${h.max_drawdown_pct.toFixed(2)}%` : "—"}
                </td>
                <td className="py-2 text-gray-400">{h.total_trades ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
