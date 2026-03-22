/**
 * Optimization page — Strategy Parameter Optimization via Optuna
 *
 * Layout:
 *  ┌──────────────────────────────────────────┐
 *  │  Header + nav                            │
 *  ├──────────────────────────────────────────┤
 *  │  Submit form (left) │ Best result (right)│
 *  ├──────────────────────────────────────────┤
 *  │  Trial table (top-20 sorted by metric)   │
 *  ├──────────────────────────────────────────┤
 *  │  History list                            │
 *  └──────────────────────────────────────────┘
 */
import { useState, useEffect, useRef, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  submitOptimization,
  getOptimizationStatus,
  listOptimizations,
  type OptimizationResult,
  type OptimizationSummary,
  type TrialSummary,
} from "../api/optimization";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 2): string {
  if (n == null) return "—";
  return n.toFixed(dec);
}

function pct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

// ── form state ───────────────────────────────────────────────────────────────

const DEFAULT_FORM = {
  strategy: "RSI",
  symbol: "BTCUSDT",
  interval: "1h",
  start_date: "2024-01-01",
  end_date: "2024-12-31",
  n_trials: 50,
  objective_metric: "sharpe" as "sharpe" | "return" | "calmar",
  initial_capital: 10000,
};

// ── component ─────────────────────────────────────────────────────────────────

export default function Optimization() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // History list
  const { data: history, refetch: refetchHistory } = useQuery({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    refetchInterval: 30_000,
  });

  // Stop polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setStatus("running");

    try {
      const res = await submitOptimization({
        ...form,
        n_trials: Number(form.n_trials),
        initial_capital: Number(form.initial_capital),
      });
      startPolling(res.task_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setStatus("failed");
    }
  }

  function startPolling(id: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await getOptimizationStatus(id);
        if (s.status === "completed" && s.result) {
          setResult(s.result);
          setStatus("completed");
          clearInterval(pollRef.current!);
          refetchHistory();
        } else if (s.status === "failed") {
          setError(s.error ?? "Optimization failed");
          setStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch {
        // keep polling
      }
    }, 3000);
  }

  function loadResult(s: OptimizationSummary) {
    if (s.status !== "completed" || !s.best_params) return;
    // Synthesize a partial result for display
    setResult({
      task_id: s.task_id,
      strategy: s.strategy,
      symbol: s.symbol,
      interval: s.interval,
      n_trials: s.n_trials,
      objective_metric: s.objective_metric,
      best_params: s.best_params ?? {},
      best_value: s.best_value ?? 0,
      best_return_pct: s.best_return_pct ?? 0,
      best_sharpe: s.best_sharpe ?? 0,
      best_drawdown_pct: 0,
      best_win_rate_pct: 0,
      best_trades: 0,
      trials_summary: [],
    });
    setStatus("completed");
    setError(null);
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
          <h1 className="text-xl font-semibold">파라미터 최적화</h1>
          <p className="text-sm text-gray-500 mt-1">
            Optuna TPE sampler로 전략 파라미터를 자동 탐색합니다.
          </p>
        </div>

        {/* ── Main grid ── */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Submit form */}
          <div className="lg:col-span-2">
            <div className="card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                최적화 설정
              </h2>

              {error && (
                <div className="px-3 py-2 rounded bg-bear/10 border border-bear/30 text-bear text-sm">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-3">
                {/* Strategy */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">전략</label>
                  <div className="flex rounded-lg overflow-hidden border border-gray-700">
                    {["RSI", "MACD"].map((s) => (
                      <button key={s} type="button"
                        onClick={() => setForm((f) => ({ ...f, strategy: s }))}
                        className={clsx(
                          "flex-1 py-1.5 text-sm font-medium transition-colors",
                          form.strategy === s
                            ? "bg-brand text-white"
                            : "bg-surface-100 text-gray-400 hover:text-white"
                        )}
                      >{s}</button>
                    ))}
                  </div>
                </div>

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

                {/* n_trials + objective */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      시도 횟수 (n_trials)
                    </label>
                    <input type="number" min={10} max={300} value={form.n_trials}
                      onChange={(e) => setForm((f) => ({ ...f, n_trials: Number(e.target.value) }))}
                      className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                                 text-sm text-white focus:outline-none focus:border-brand" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">최적화 목표</label>
                    <select value={form.objective_metric}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, objective_metric: e.target.value as typeof form.objective_metric }))
                      }
                      className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                                 text-sm text-white focus:outline-none focus:border-brand">
                      <option value="sharpe">Sharpe Ratio</option>
                      <option value="return">Total Return</option>
                      <option value="calmar">Calmar Ratio</option>
                    </select>
                  </div>
                </div>

                {/* Initial capital */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">초기 자본 (USD)</label>
                  <input type="number" min={100} value={form.initial_capital}
                    onChange={(e) => setForm((f) => ({ ...f, initial_capital: Number(e.target.value) }))}
                    className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-white focus:outline-none focus:border-brand" />
                </div>

                <button type="submit" disabled={status === "running"}
                  className="w-full bg-brand hover:bg-brand/90 disabled:opacity-50
                             text-white text-sm font-medium py-2 rounded-lg transition-colors">
                  {status === "running" ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-3 h-3 rounded-full bg-white/40 animate-pulse" />
                      최적화 중… ({form.n_trials} trials)
                    </span>
                  ) : "최적화 시작"}
                </button>
              </form>

              {/* Search space hint */}
              <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                {form.strategy === "RSI" ? (
                  <>
                    <div>period: 5–30 · oversold: 20–45 · overbought: 55–80</div>
                  </>
                ) : (
                  <>
                    <div>fast: 5–20 · slow: fast+5–fast+30 · signal: 3–15</div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Best result panel */}
          <div className="lg:col-span-3">
            {status === "idle" && (
              <div className="card p-8 flex items-center justify-center h-full text-gray-600 text-sm">
                최적화를 시작하면 결과가 여기에 표시됩니다.
              </div>
            )}

            {status === "running" && (
              <div className="card p-8 flex flex-col items-center justify-center h-full gap-4">
                <div className="w-12 h-12 rounded-full border-4 border-brand/30 border-t-brand animate-spin" />
                <div className="text-gray-400 text-sm text-center">
                  Optuna TPE sampler 실행 중…<br />
                  <span className="text-gray-600 text-xs">완료까지 약 1–3분 소요</span>
                </div>
              </div>
            )}

            {(status === "completed" || status === "failed") && result && (
              <BestResultPanel result={result} />
            )}
          </div>
        </div>

        {/* Trial table */}
        {result && result.trials_summary && result.trials_summary.length > 0 && (
          <TrialTable trials={result.trials_summary as TrialSummary[]} metric={result.objective_metric} />
        )}

        {/* History */}
        {history && history.length > 0 && (
          <HistoryTable history={history} onSelect={loadResult} />
        )}
      </div>

      <footer className="border-t border-gray-800 px-6 py-3 text-xs text-gray-600 flex justify-between">
        <span>Phase 9 · Strategy Parameter Optimization · Optuna TPE</span>
        <span>{new Date().toLocaleDateString()}</span>
      </footer>
    </div>
  );
}


// ── Sub-components ────────────────────────────────────────────────────────────

function BestResultPanel({ result }: { result: OptimizationResult }) {
  const metricLabel = result.objective_metric === "sharpe"
    ? "Sharpe"
    : result.objective_metric === "return"
    ? "Return"
    : "Calmar";

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          최적 파라미터 — {result.strategy} / {result.symbol}
        </h2>
        <span className="text-xs text-gray-500">{result.n_trials} trials</span>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label={`Best ${metricLabel}`}
          value={fmt(result.best_value, 3)}
          accent="text-brand"
        />
        <MetricCard
          label="Total Return"
          value={pct(result.best_return_pct)}
          accent={result.best_return_pct >= 0 ? "text-bull" : "text-bear"}
        />
        <MetricCard
          label="Max Drawdown"
          value={`${fmt(result.best_drawdown_pct)}%`}
          accent="text-bear"
        />
        <MetricCard
          label="Win Rate"
          value={`${fmt(result.best_win_rate_pct)}%`}
        />
      </div>

      {/* Best params */}
      <div>
        <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">최적 파라미터</div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(result.best_params).map(([k, v]) => (
            <div key={k}
              className="px-3 py-1.5 rounded-lg bg-brand/10 border border-brand/30 text-sm">
              <span className="text-gray-400">{k}:</span>{" "}
              <span className="text-white font-mono font-semibold">
                {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(1)) : v}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="text-xs text-gray-600">
        Sharpe: <span className="text-gray-400">{fmt(result.best_sharpe, 3)}</span>
        {" · "}Trades: <span className="text-gray-400">{result.best_trades}</span>
        {" · "}Objective: <span className="text-gray-400">{result.objective_metric}</span>
      </div>
    </div>
  );
}


function MetricCard({
  label, value, accent = "text-white",
}: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-surface-100 rounded-lg px-3 py-3">
      <div className="text-xs text-gray-500 mb-1 uppercase tracking-wider">{label}</div>
      <div className={clsx("font-mono text-base font-semibold", accent)}>{value}</div>
    </div>
  );
}


function TrialTable({
  trials, metric,
}: { trials: TrialSummary[]; metric: string }) {
  const metricLabel = metric === "sharpe" ? "Sharpe" : metric === "return" ? "Return" : "Calmar";

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
        상위 Trial 결과 (top-20, {metricLabel} 기준 정렬)
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left py-2 px-2 text-xs text-gray-500 font-medium">#</th>
              <th className="text-left py-2 px-2 text-xs text-gray-500 font-medium">파라미터</th>
              <th className="text-right py-2 px-2 text-xs text-gray-500 font-medium">{metricLabel}</th>
              <th className="text-right py-2 px-2 text-xs text-gray-500 font-medium">Return</th>
              <th className="text-right py-2 px-2 text-xs text-gray-500 font-medium">Drawdown</th>
              <th className="text-right py-2 px-2 text-xs text-gray-500 font-medium">Win%</th>
              <th className="text-right py-2 px-2 text-xs text-gray-500 font-medium">Trades</th>
            </tr>
          </thead>
          <tbody>
            {trials.map((t, i) => {
              const paramStr = Object.entries(t.params)
                .map(([k, v]) => `${k}=${Number.isInteger(v) ? v : v.toFixed(1)}`)
                .join(", ");
              return (
                <tr key={i} className={clsx(
                  "border-b border-gray-800/50 hover:bg-surface-50 transition-colors",
                  i === 0 && "bg-brand/5"
                )}>
                  <td className="py-2 px-2 text-gray-500 font-mono">{t.trial + 1}</td>
                  <td className="py-2 px-2 text-gray-300 font-mono text-xs">{paramStr}</td>
                  <td className={clsx(
                    "py-2 px-2 text-right font-mono",
                    i === 0 ? "text-brand font-semibold" : "text-gray-300"
                  )}>
                    {fmt(t.value, 3)}
                  </td>
                  <td className={clsx(
                    "py-2 px-2 text-right font-mono",
                    t.return_pct >= 0 ? "text-bull" : "text-bear"
                  )}>
                    {pct(t.return_pct)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-bear">
                    {fmt(t.drawdown_pct)}%
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-gray-300">
                    {fmt(t.win_rate_pct, 1)}%
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-gray-400">
                    {t.total_trades}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function HistoryTable({
  history, onSelect,
}: { history: OptimizationSummary[]; onSelect: (s: OptimizationSummary) => void }) {
  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
        이전 최적화 기록
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {["전략", "심볼", "인터벌", "Trials", "목표", "Best Value", "Return", "상태", "날짜"].map((h) => (
                <th key={h} className="text-left py-2 px-2 text-xs text-gray-500 font-medium">{h}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((r) => (
              <tr key={r.task_id}
                className="border-b border-gray-800/50 hover:bg-surface-50 transition-colors">
                <td className="py-2 px-2 text-gray-300 font-medium">{r.strategy}</td>
                <td className="py-2 px-2 text-gray-400 font-mono text-xs">{r.symbol}</td>
                <td className="py-2 px-2 text-gray-500">{r.interval}</td>
                <td className="py-2 px-2 text-gray-500">{r.n_trials}</td>
                <td className="py-2 px-2 text-gray-500 capitalize">{r.objective_metric}</td>
                <td className="py-2 px-2 font-mono text-brand">{fmt(r.best_value, 3)}</td>
                <td className={clsx(
                  "py-2 px-2 font-mono",
                  (r.best_return_pct ?? 0) >= 0 ? "text-bull" : "text-bear"
                )}>
                  {pct(r.best_return_pct)}
                </td>
                <td className="py-2 px-2">
                  <StatusBadge status={r.status} />
                </td>
                <td className="py-2 px-2 text-gray-600 text-xs">
                  {new Date(r.created_at).toLocaleDateString()}
                </td>
                <td className="py-2 px-2">
                  {r.status === "completed" && (
                    <button onClick={() => onSelect(r)}
                      className="text-xs text-brand hover:underline">
                      결과 보기
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function StatusBadge({ status }: { status: string }) {
  const cls = {
    completed: "bg-bull/10 text-bull border-bull/30",
    running: "bg-brand/10 text-brand border-brand/30",
    failed: "bg-bear/10 text-bear border-bear/30",
    pending: "bg-gray-700/30 text-gray-400 border-gray-600",
  }[status] ?? "bg-gray-700/30 text-gray-400 border-gray-600";

  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs border", cls)}>
      {status}
    </span>
  );
}
