/**
 * Portfolio — Multi-Asset Portfolio Management
 *
 * Layout:
 *  ┌────────────────────────────────────────────────┐
 *  │  Header (shared nav)                           │
 *  ├──────────────────┬─────────────────────────────┤
 *  │  Portfolio Stats │  Allocation Editor (targets) │
 *  ├──────────────────┴─────────────────────────────┤
 *  │  Rebalance Panel                               │
 *  ├────────────────────────────────────────────────┤
 *  │  Correlation Heatmap                           │
 *  └────────────────────────────────────────────────┘
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import { useAuthStore } from "../store/authStore";
import {
  fetchPortfolio,
  fetchAllocation,
  setAllocation,
  fetchWeights,
  fetchRebalancePreview,
  executeRebalance,
  fetchCorrelation,
  type AllocationTarget,
  type Portfolio,
  type RebalanceTrade,
  type CorrelationResponse,
} from "../api/portfolio";

// ── NAV ──────────────────────────────────────────────────────────────────────

const NAV = [
  { label: "대시보드", to: "/dashboard" },
  { label: "분석", to: "/analytics" },
  { label: "최적화", to: "/optimization" },
  { label: "예측", to: "/prediction" },
  { label: "리스크", to: "/risk" },
  { label: "백테스트", to: "/backtest" },
  { label: "설정", to: "/settings" },
];

const SYMBOL_OPTIONS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

function formatUsd(v: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(v);
}

// ── COLOUR helpers ─────────────────────────────────────────────────────────

function corrColour(v: number): string {
  if (v >= 0.7) return "bg-red-500/70";
  if (v >= 0.4) return "bg-orange-400/60";
  if (v >= 0.1) return "bg-yellow-300/50";
  if (v >= -0.1) return "bg-gray-600/60";
  if (v >= -0.4) return "bg-sky-400/50";
  return "bg-blue-500/70";
}

function pctBar(current: number, target: number) {
  const diff = target - current;
  if (diff > 2) return "text-bull";
  if (diff < -2) return "text-bear";
  return "text-gray-400";
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function Portfolio() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  // Portfolio snapshot
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});

  // Allocation editor
  const [targets, setTargets] = useState<AllocationTarget[]>([
    { symbol: "BTCUSDT", target_pct: 50 },
    { symbol: "ETHUSDT", target_pct: 30 },
    { symbol: "SOLUSDT", target_pct: 20 },
  ]);
  const [savingAlloc, setSavingAlloc] = useState(false);
  const [allocSaved, setAllocSaved] = useState(false);

  // Rebalance
  const [rebalanceTrades, setRebalanceTrades] = useState<RebalanceTrade[]>([]);
  const [rebalanceMsg, setRebalanceMsg] = useState("");
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<string | null>(null);

  // Correlation
  const [corrData, setCorrData] = useState<CorrelationResponse | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrError, setCorrError] = useState("");

  // ── Load on mount ────────────────────────────────────────────────────────

  useEffect(() => {
    fetchPortfolio().then(setPortfolio).catch(console.error);
    fetchWeights().then(setWeights).catch(console.error);
    fetchAllocation()
      .then((r) => { if (r.targets.length) setTargets(r.targets); })
      .catch(console.error);
    loadRebalancePreview();
    loadCorrelation();
  }, []);

  async function loadRebalancePreview() {
    try {
      const preview = await fetchRebalancePreview();
      setRebalanceTrades(preview.trades);
      setRebalanceMsg(preview.message ?? "");
    } catch {
      // no-op
    }
  }

  async function loadCorrelation() {
    setCorrLoading(true);
    setCorrError("");
    try {
      const data = await fetchCorrelation();
      setCorrData(data);
    } catch (err: unknown) {
      setCorrError(err instanceof Error ? err.message : "Correlation fetch failed");
    } finally {
      setCorrLoading(false);
    }
  }

  // ── Allocation editor actions ────────────────────────────────────────────

  function addSymbol() {
    const used = new Set(targets.map((t) => t.symbol));
    const next = SYMBOL_OPTIONS.find((s) => !used.has(s));
    if (next) setTargets([...targets, { symbol: next, target_pct: 0 }]);
  }

  function removeTarget(i: number) {
    setTargets(targets.filter((_, idx) => idx !== i));
  }

  function updatePct(i: number, val: string) {
    const num = parseFloat(val) || 0;
    setTargets(targets.map((t, idx) => (idx === i ? { ...t, target_pct: num } : t)));
  }

  function updateSymbol(i: number, sym: string) {
    setTargets(targets.map((t, idx) => (idx === i ? { ...t, symbol: sym } : t)));
  }

  const totalPct = targets.reduce((s, t) => s + t.target_pct, 0);
  const pctValid = totalPct <= 100.01;

  async function saveAllocation() {
    setSavingAlloc(true);
    try {
      await setAllocation(targets);
      setAllocSaved(true);
      setTimeout(() => setAllocSaved(false), 2000);
      await loadRebalancePreview();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingAlloc(false);
    }
  }

  // ── Rebalance execution ──────────────────────────────────────────────────

  async function runRebalance() {
    setExecuting(true);
    setExecResult(null);
    try {
      const result = await executeRebalance();
      setExecResult(`${result.executed}개 주문 실행 완료`);
      await fetchPortfolio().then(setPortfolio);
      await fetchWeights().then(setWeights);
      await loadRebalancePreview();
    } catch (err: unknown) {
      setExecResult(`오류: ${err instanceof Error ? err.message : "Unknown"}`);
    } finally {
      setExecuting(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* ---- Header ---- */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white">
              <path
                d="M3 17l4-8 4 5 3-3 4 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span className="font-semibold text-lg tracking-tight">
            Stock<span className="text-brand">Trader</span>
          </span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="px-3 py-1.5 text-sm text-white border border-brand rounded-lg">
            포트폴리오
          </span>
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className="px-3 py-1.5 text-sm text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
            >
              {n.label}
            </Link>
          ))}
          <div className="flex items-center gap-2 border-l border-gray-700 pl-3">
            <span className="text-xs text-gray-400 max-w-[140px] truncate">{user?.email}</span>
            <button
              onClick={() => { logout(); navigate("/login", { replace: true }); }}
              className="px-2 py-1 text-xs text-gray-500 hover:text-bear border border-gray-700 rounded transition-colors"
            >
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <div className="px-6 py-6 flex flex-col gap-6">

        {/* ---- Row 1: Portfolio stats + Allocation editor ---- */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Portfolio Stats */}
          <section className="card p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              포트폴리오 현황
            </h2>
            {portfolio ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <StatTile label="총 자산" value={formatUsd(portfolio.total_value_usd)} />
                  <StatTile label="가용 USDT" value={formatUsd(portfolio.available_usd)} />
                  <StatTile
                    label="손익 (USD)"
                    value={formatUsd(portfolio.pnl_usd)}
                    valueClass={portfolio.pnl_usd >= 0 ? "text-bull" : "text-bear"}
                  />
                  <StatTile
                    label="손익 (%)"
                    value={`${portfolio.pnl_pct >= 0 ? "+" : ""}${portfolio.pnl_pct.toFixed(2)}%`}
                    valueClass={portfolio.pnl_pct >= 0 ? "text-bull" : "text-bear"}
                  />
                </div>

                {/* Holdings */}
                {Object.keys(portfolio.holdings).length > 0 && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">보유 자산</div>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-600 text-xs">
                          <th className="text-left pb-1">자산</th>
                          <th className="text-right pb-1">수량</th>
                          <th className="text-right pb-1">현재 비중</th>
                          {targets.map((t) =>
                            t.symbol.replace("USDT", "") ===
                            Object.keys(portfolio.holdings)[0]
                              ? null
                              : null
                          )}
                          <th className="text-right pb-1">목표 비중</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(portfolio.holdings).map(([asset, qty]) => {
                          const sym = asset + "USDT";
                          const cw = weights[sym] ?? 0;
                          const tw = targets.find((t) => t.symbol === sym)?.target_pct ?? 0;
                          return (
                            <tr key={asset} className="border-t border-gray-800">
                              <td className="py-1.5 font-mono text-gray-200">{asset}</td>
                              <td className="py-1.5 text-right font-mono text-gray-300">
                                {(qty as number).toFixed(6)}
                              </td>
                              <td className={clsx("py-1.5 text-right font-mono", pctBar(cw, tw))}>
                                {cw.toFixed(1)}%
                              </td>
                              <td className="py-1.5 text-right font-mono text-gray-400">
                                {tw.toFixed(1)}%
                              </td>
                            </tr>
                          );
                        })}
                        <tr className="border-t border-gray-800">
                          <td className="py-1.5 font-mono text-gray-400">CASH</td>
                          <td className="py-1.5 text-right font-mono text-gray-300" colSpan={1}>
                            {formatUsd(portfolio.available_usd)}
                          </td>
                          <td className="py-1.5 text-right font-mono text-gray-400">
                            {(weights["CASH"] ?? 0).toFixed(1)}%
                          </td>
                          <td className="py-1.5 text-right font-mono text-gray-400">—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <div className="text-gray-600 text-sm">로딩 중…</div>
            )}
          </section>

          {/* Allocation Editor */}
          <section className="card p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              목표 배분 설정
            </h2>

            <div className="space-y-2">
              {targets.map((t, i) => (
                <div key={i} className="flex items-center gap-2">
                  <select
                    value={t.symbol}
                    onChange={(e) => updateSymbol(i, e.target.value)}
                    className="bg-surface-100 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 flex-1"
                  >
                    {SYMBOL_OPTIONS.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <div className="relative w-28">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={t.target_pct}
                      onChange={(e) => updatePct(i, e.target.value)}
                      className="w-full bg-surface-100 border border-gray-700 rounded px-2 py-1 text-sm font-mono text-right text-gray-200"
                    />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 pointer-events-none">
                      %
                    </span>
                  </div>
                  <button
                    onClick={() => removeTarget(i)}
                    className="text-gray-600 hover:text-bear text-sm px-1"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>

            {/* Sum indicator */}
            <div className="flex items-center gap-2">
              <div
                className={clsx(
                  "text-sm font-mono font-medium",
                  pctValid ? "text-gray-400" : "text-bear"
                )}
              >
                합계: {totalPct.toFixed(1)}%
              </div>
              <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={clsx(
                    "h-full rounded-full transition-all",
                    totalPct > 100 ? "bg-bear" : "bg-brand"
                  )}
                  style={{ width: `${Math.min(totalPct, 100)}%` }}
                />
              </div>
              <div className="text-xs text-gray-600">{(100 - totalPct).toFixed(1)}% 잔여</div>
            </div>

            <div className="flex gap-2">
              {targets.length < SYMBOL_OPTIONS.length && (
                <button
                  onClick={addSymbol}
                  className="px-3 py-1.5 text-xs border border-gray-700 rounded text-gray-400 hover:text-white transition-colors"
                >
                  + 심볼 추가
                </button>
              )}
              <button
                onClick={saveAllocation}
                disabled={savingAlloc || !pctValid}
                className={clsx(
                  "px-4 py-1.5 text-xs rounded font-medium transition-colors",
                  allocSaved
                    ? "bg-bull/20 text-bull border border-bull/30"
                    : "bg-brand hover:bg-brand/80 text-white disabled:opacity-40"
                )}
              >
                {allocSaved ? "저장됨 ✓" : savingAlloc ? "저장 중…" : "저장"}
              </button>
            </div>
          </section>
        </div>

        {/* ---- Row 2: Rebalance Panel ---- */}
        <section className="card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              리밸런싱
            </h2>
            <button
              onClick={loadRebalancePreview}
              className="text-xs text-gray-500 hover:text-white border border-gray-700 rounded px-2 py-1 transition-colors"
            >
              새로고침
            </button>
          </div>

          {rebalanceTrades.length === 0 ? (
            <div className="text-sm text-gray-600">
              {rebalanceMsg || "리밸런싱 불필요 — 포트폴리오가 목표 비중에 부합합니다."}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-600 text-xs border-b border-gray-800">
                      <th className="text-left pb-2">심볼</th>
                      <th className="text-center pb-2">방향</th>
                      <th className="text-right pb-2">거래 금액</th>
                      <th className="text-right pb-2">현재 비중</th>
                      <th className="text-right pb-2">목표 비중</th>
                      <th className="text-right pb-2">현재 가치</th>
                      <th className="text-right pb-2">목표 가치</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rebalanceTrades.map((t) => (
                      <tr
                        key={t.symbol}
                        className="border-t border-gray-800 hover:bg-gray-800/30 transition-colors"
                      >
                        <td className="py-2 font-mono text-gray-200">{t.symbol}</td>
                        <td className="py-2 text-center">
                          <span
                            className={clsx(
                              "px-2 py-0.5 rounded text-xs font-medium",
                              t.side === "BUY"
                                ? "bg-bull/20 text-bull"
                                : "bg-bear/20 text-bear"
                            )}
                          >
                            {t.side}
                          </span>
                        </td>
                        <td className="py-2 text-right font-mono text-gray-200">
                          {formatUsd(t.amount_usd)}
                        </td>
                        <td className="py-2 text-right font-mono text-gray-400">
                          {t.current_pct.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right font-mono text-brand">
                          {t.target_pct.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right font-mono text-gray-400">
                          {formatUsd(t.current_value_usd)}
                        </td>
                        <td className="py-2 text-right font-mono text-gray-400">
                          {formatUsd(t.target_value_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={runRebalance}
                  disabled={executing}
                  className="px-4 py-2 bg-brand hover:bg-brand/80 disabled:opacity-40 text-white text-sm rounded font-medium transition-colors"
                >
                  {executing ? "실행 중…" : "리밸런싱 실행"}
                </button>
                {execResult && (
                  <span
                    className={clsx(
                      "text-sm",
                      execResult.startsWith("오류") ? "text-bear" : "text-bull"
                    )}
                  >
                    {execResult}
                  </span>
                )}
              </div>
            </>
          )}
        </section>

        {/* ---- Row 3: Correlation Heatmap ---- */}
        <section className="card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              자산 상관관계
            </h2>
            <button
              onClick={loadCorrelation}
              disabled={corrLoading}
              className="text-xs text-gray-500 hover:text-white border border-gray-700 rounded px-2 py-1 transition-colors disabled:opacity-40"
            >
              {corrLoading ? "분석 중…" : "새로고침"}
            </button>
          </div>

          {corrError && <div className="text-sm text-bear">{corrError}</div>}

          {corrData && (
            <>
              <div className="overflow-x-auto">
                <table className="text-sm">
                  <thead>
                    <tr>
                      <th className="pr-3 pb-2 text-gray-600 text-xs font-normal" />
                      {corrData.symbols.map((sym) => (
                        <th
                          key={sym}
                          className="pb-2 px-2 text-xs text-gray-500 font-normal min-w-[80px]"
                        >
                          {sym.replace("USDT", "")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {corrData.symbols.map((s1) => (
                      <tr key={s1}>
                        <td className="pr-3 text-xs text-gray-500 whitespace-nowrap">
                          {s1.replace("USDT", "")}
                        </td>
                        {corrData.symbols.map((s2) => {
                          const v = corrData.matrix[s1]?.[s2] ?? 0;
                          return (
                            <td key={s2} className="px-1 py-1">
                              <div
                                className={clsx(
                                  "w-full h-10 flex items-center justify-center rounded text-xs font-mono font-medium",
                                  corrColour(v)
                                )}
                              >
                                {v.toFixed(3)}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center gap-4 text-xs text-gray-600">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-red-500/70 inline-block" />강한 양의 상관 (≥0.7)
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-yellow-300/50 inline-block" />약한 양의 상관
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-gray-600/60 inline-block" />무상관
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-blue-500/70 inline-block" />음의 상관
                </div>
                <span className="text-gray-700">
                  데이터: {Object.values(corrData.data_points)[0]}개 캔들 ({corrData.interval})
                </span>
              </div>
            </>
          )}

          {corrLoading && !corrData && (
            <div className="text-sm text-gray-600">상관관계 분석 중…</div>
          )}
        </section>

      </div>

      <footer className="border-t border-gray-800 px-6 py-3 flex justify-between items-center text-xs text-gray-600 mt-auto">
        <span>Phase 11 · Multi-Asset Portfolio</span>
        <span>{new Date().toLocaleDateString()}</span>
      </footer>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="bg-surface-100 rounded-lg px-3 py-2">
      <div className="text-xs uppercase tracking-wider text-gray-600 mb-0.5">{label}</div>
      <div className={clsx("font-mono text-sm font-semibold tabular-nums", valueClass)}>
        {value}
      </div>
    </div>
  );
}
