/**
 * Risk Dashboard — Phase 10
 *
 * Layout:
 *  ┌─────────────────────────────────────────────────────────┐
 *  │  Circuit Breaker status banner (if halted)              │
 *  ├───────────────┬─────────────────┬───────────────────────┤
 *  │  Kelly card   │  VaR card       │  Daily drawdown card  │
 *  ├───────────────┴─────────────────┴───────────────────────┤
 *  │  Per-strategy risk table                                │
 *  ├─────────────────────────────────────────────────────────┤
 *  │  Risk config editor            │  Event log             │
 *  └─────────────────────────────────────────────────────────┘
 */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  fetchRiskMetrics,
  fetchRiskEvents,
  updateRiskConfig,
  resumeTrading,
  resumeStrategy,
  type RiskMetrics,
  type RiskConfig,
} from "../api/risk";

// ── helpers ────────────────────────────────────────────────────────────────

function dollar(n: number) {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ── main ───────────────────────────────────────────────────────────────────

export default function RiskDashboard() {
  const qc = useQueryClient();

  const { data: metrics, isLoading } = useQuery({
    queryKey: ["risk-metrics"],
    queryFn: fetchRiskMetrics,
    refetchInterval: 5_000,
  });

  const { data: events } = useQuery({
    queryKey: ["risk-events"],
    queryFn: () => fetchRiskEvents(30),
    refetchInterval: 10_000,
  });

  const resumeMut = useMutation({
    mutationFn: resumeTrading,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-metrics"] }),
  });

  const resumeStratMut = useMutation({
    mutationFn: (strategy: string) => resumeStrategy(strategy),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-metrics"] }),
  });

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
            { label: "예측", to: "/prediction" },
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

      <div className="px-6 py-6 flex-1 space-y-5">
        <div>
          <h1 className="text-xl font-semibold">리스크 대시보드</h1>
          <p className="text-sm text-gray-500 mt-1">
            Kelly Criterion 포지션 사이징 · VaR · 전략별 드로다운 한도
          </p>
        </div>

        {isLoading && (
          <div className="text-gray-500 text-sm">데이터 로딩 중…</div>
        )}

        {metrics && (
          <>
            {/* ── Circuit breaker banner ── */}
            {metrics.halted && (
              <div className="card border-bear/40 bg-bear/5 p-4 flex items-center justify-between">
                <div>
                  <div className="text-bear font-semibold">⚠ 트레이딩 정지됨</div>
                  <div className="text-sm text-gray-400 mt-0.5">{metrics.halt_reason}</div>
                </div>
                <button
                  onClick={() => resumeMut.mutate()}
                  className="px-4 py-1.5 bg-bear/20 hover:bg-bear/30 text-bear text-sm
                             font-medium rounded-lg border border-bear/40 transition-colors">
                  거래 재개
                </button>
              </div>
            )}

            {/* ── Metric cards row ── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <KellyCard metrics={metrics} />
              <VarCard metrics={metrics} confidence={95} />
              <VarCard metrics={metrics} confidence={99} />
              <DrawdownCard metrics={metrics} />
            </div>

            {/* ── Main content ── */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
              {/* Strategy risk table */}
              <div className="lg:col-span-3">
                <StrategyRiskTable
                  metrics={metrics}
                  onResume={(s) => resumeStratMut.mutate(s)}
                />
              </div>

              {/* Right column: config + events */}
              <div className="lg:col-span-2 space-y-5">
                <RiskConfigEditor
                  config={metrics.config}
                  onSaved={() => qc.invalidateQueries({ queryKey: ["risk-metrics"] })}
                />
              </div>
            </div>

            {/* ── Event log ── */}
            {events && events.length > 0 && (
              <EventLog events={events} />
            )}
          </>
        )}
      </div>

      <footer className="border-t border-gray-800 px-6 py-3 text-xs text-gray-600 flex justify-between">
        <span>Phase 10 · Advanced Risk Management · Kelly · VaR · Strategy Drawdown</span>
        <span>{new Date().toLocaleDateString()}</span>
      </footer>
    </div>
  );
}

// ── Metric cards ──────────────────────────────────────────────────────────────

function KellyCard({ metrics }: { metrics: RiskMetrics }) {
  const pct_val = (metrics.kelly_fraction * 100).toFixed(1);
  const enough = metrics.kelly_lookback_trades >= 5;
  return (
    <div className="card p-4 space-y-2">
      <div className="text-xs text-gray-500 uppercase tracking-wider">Kelly Criterion</div>
      <div className={clsx(
        "font-mono text-2xl font-bold",
        enough ? "text-brand" : "text-gray-600"
      )}>
        {enough ? `${pct_val}%` : "—"}
      </div>
      <div className="text-xs text-gray-600 space-y-0.5">
        <div>권장 포지션: <span className="text-gray-400">
          {enough ? dollar(metrics.kelly_position_usd) : "데이터 부족"}
        </span></div>
        <div>기준 거래수: <span className="text-gray-400">
          {metrics.kelly_lookback_trades} / {metrics.config.kelly_lookback}
        </span></div>
        <div>{metrics.config.half_kelly ? "Half-Kelly 적용" : "Full Kelly"}</div>
      </div>
    </div>
  );
}

function VarCard({ metrics, confidence }: { metrics: RiskMetrics; confidence: 95 | 99 }) {
  const usd = confidence === 95 ? metrics.var_95_usd : metrics.var_99_usd;
  const pct_val = confidence === 95 ? metrics.var_95_pct : metrics.var_99_pct;
  const hasData = metrics.equity_curve_len >= 10;
  return (
    <div className="card p-4 space-y-2">
      <div className="text-xs text-gray-500 uppercase tracking-wider">
        VaR {confidence}% (1-period)
      </div>
      <div className={clsx(
        "font-mono text-2xl font-bold",
        hasData ? "text-bear" : "text-gray-600"
      )}>
        {hasData ? dollar(usd) : "—"}
      </div>
      <div className="text-xs text-gray-600 space-y-0.5">
        <div>손실률: <span className="text-gray-400">
          {hasData ? `${pct_val.toFixed(2)}%` : "데이터 부족"}
        </span></div>
        <div>데이터 포인트: <span className="text-gray-400">
          {metrics.equity_curve_len}
        </span></div>
        <div>히스토리컬 시뮬레이션</div>
      </div>
    </div>
  );
}

function DrawdownCard({ metrics }: { metrics: RiskMetrics }) {
  const current = metrics.daily_drawdown_pct;
  const limit = metrics.daily_loss_limit_pct;
  const pct_used = Math.min(100, (current / limit) * 100);
  const barColor = pct_used > 80 ? "bg-bear" : pct_used > 50 ? "bg-yellow-500" : "bg-bull";

  return (
    <div className="card p-4 space-y-2">
      <div className="text-xs text-gray-500 uppercase tracking-wider">일일 드로다운</div>
      <div className={clsx(
        "font-mono text-2xl font-bold",
        current > limit * 0.8 ? "text-bear" : current > limit * 0.5 ? "text-yellow-400" : "text-bull"
      )}>
        {current.toFixed(2)}%
      </div>
      {/* Progress bar */}
      <div className="w-full bg-gray-700 rounded-full h-1.5">
        <div
          className={clsx("h-1.5 rounded-full transition-all", barColor)}
          style={{ width: `${pct_used}%` }}
        />
      </div>
      <div className="text-xs text-gray-600">
        한도: <span className="text-gray-400">{limit.toFixed(1)}%</span>
        {" · "}{pct_used.toFixed(0)}% 사용
      </div>
    </div>
  );
}

// ── Strategy risk table ───────────────────────────────────────────────────────

function StrategyRiskTable({
  metrics,
  onResume,
}: {
  metrics: RiskMetrics;
  onResume: (s: string) => void;
}) {
  const limit = metrics.config.strategy_drawdown_limit_pct * 100;

  if (!metrics.strategy_risks.length) {
    return (
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
          전략별 리스크
        </h2>
        <div className="text-sm text-gray-600 py-6 text-center">
          아직 실행된 전략이 없습니다.
        </div>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
        전략별 리스크 (드로다운 한도 {limit.toFixed(0)}%)
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {["전략", "누적 P&L", "최고점", "드로다운", "Kelly", "상태", ""].map((h) => (
                <th key={h} className="text-left py-2 px-2 text-xs text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.strategy_risks.map((s) => {
              const ddPct = s.drawdown_pct;
              const ddColor = ddPct > limit * 0.8 ? "text-bear"
                : ddPct > limit * 0.5 ? "text-yellow-400" : "text-gray-400";

              return (
                <tr key={s.strategy}
                  className="border-b border-gray-800/50 hover:bg-surface-50 transition-colors">
                  <td className="py-2 px-2 font-medium text-white">{s.strategy}</td>
                  <td className={clsx(
                    "py-2 px-2 font-mono",
                    s.cumulative_pnl >= 0 ? "text-bull" : "text-bear"
                  )}>
                    {s.cumulative_pnl >= 0 ? "+" : ""}${s.cumulative_pnl.toFixed(2)}
                  </td>
                  <td className="py-2 px-2 font-mono text-gray-400">
                    ${s.peak_pnl.toFixed(2)}
                  </td>
                  <td className={clsx("py-2 px-2 font-mono", ddColor)}>
                    {ddPct.toFixed(2)}%
                    {/* Mini progress bar */}
                    <div className="w-16 bg-gray-700 rounded-full h-1 mt-1">
                      <div
                        className={clsx("h-1 rounded-full", ddColor === "text-bear"
                          ? "bg-bear" : ddColor === "text-yellow-400"
                          ? "bg-yellow-500" : "bg-bull")}
                        style={{ width: `${Math.min(100, (ddPct / limit) * 100)}%` }}
                      />
                    </div>
                  </td>
                  <td className="py-2 px-2 font-mono text-brand">
                    {(s.kelly_fraction * 100).toFixed(1)}%
                  </td>
                  <td className="py-2 px-2">
                    <span className={clsx(
                      "px-2 py-0.5 rounded text-xs border",
                      s.paused
                        ? "bg-bear/10 text-bear border-bear/30"
                        : "bg-bull/10 text-bull border-bull/30"
                    )}>
                      {s.paused ? "일시정지" : "활성"}
                    </span>
                  </td>
                  <td className="py-2 px-2">
                    {s.paused && (
                      <button
                        onClick={() => onResume(s.strategy)}
                        className="text-xs text-brand hover:underline">
                        재개
                      </button>
                    )}
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

// ── Risk config editor ────────────────────────────────────────────────────────

function RiskConfigEditor({
  config,
  onSaved,
}: {
  config: RiskConfig;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<RiskConfig>({ ...config });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    try {
      await updateRiskConfig(form);
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
        리스크 설정 (런타임 변경)
      </h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="최대 포지션 %" type="number" step="0.001"
          value={form.max_position_pct}
          onChange={(v) => setForm((f) => ({ ...f, max_position_pct: v }))} />
        <Field label="일일 손실 한도 %" type="number" step="0.001"
          value={form.daily_loss_limit_pct}
          onChange={(v) => setForm((f) => ({ ...f, daily_loss_limit_pct: v }))} />
        <Field label="최대 오픈 포지션" type="number" step="1"
          value={form.max_open_positions}
          onChange={(v) => setForm((f) => ({ ...f, max_open_positions: Math.round(v) }))} />
        <Field label="전략 드로다운 한도 %" type="number" step="0.01"
          value={form.strategy_drawdown_limit_pct}
          onChange={(v) => setForm((f) => ({ ...f, strategy_drawdown_limit_pct: v }))} />
        <Field label="Kelly 기준 거래수" type="number" step="1"
          value={form.kelly_lookback}
          onChange={(v) => setForm((f) => ({ ...f, kelly_lookback: Math.round(v) }))} />

        {/* Toggles */}
        <div className="flex flex-wrap gap-3 pt-1">
          {(["use_kelly", "half_kelly"] as const).map((key) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer select-none">
              <div
                onClick={() => setForm((f) => ({ ...f, [key]: !f[key] }))}
                className={clsx(
                  "w-9 h-5 rounded-full transition-colors relative cursor-pointer",
                  form[key] ? "bg-brand" : "bg-gray-600"
                )}
              >
                <div className={clsx(
                  "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
                  form[key] ? "translate-x-4" : "translate-x-0.5"
                )} />
              </div>
              <span className="text-xs text-gray-400">
                {key === "use_kelly" ? "Kelly 사용" : "Half-Kelly"}
              </span>
            </label>
          ))}
        </div>

        <button type="submit" disabled={saving}
          className="w-full mt-1 bg-brand/80 hover:bg-brand disabled:opacity-50
                     text-white text-sm font-medium py-1.5 rounded-lg transition-colors">
          {saving ? "저장 중…" : saved ? "✓ 저장됨" : "설정 저장"}
        </button>
      </form>
    </div>
  );
}

function Field({
  label, value, onChange, type = "number", step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  type?: string;
  step?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <label className="text-xs text-gray-400 flex-1">{label}</label>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-24 bg-surface-100 border border-gray-700 rounded px-2 py-1
                   text-xs text-white font-mono focus:outline-none focus:border-brand"
      />
    </div>
  );
}

// ── Event log ─────────────────────────────────────────────────────────────────

function EventLog({ events }: { events: Array<{
  ts: string; type: string; detail: string;
}> }) {
  const typeColor: Record<string, string> = {
    HALT: "text-bear",
    RESUME: "text-bull",
    STRATEGY_PAUSE: "text-yellow-400",
    STRATEGY_RESUME: "text-brand",
  };

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
        리스크 이벤트 로그
      </h2>
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {events.map((e, i) => (
          <div key={i} className="flex items-start gap-3 text-xs">
            <span className="text-gray-600 shrink-0 font-mono">
              {new Date(e.ts).toLocaleTimeString()}
            </span>
            <span className={clsx("font-medium shrink-0 w-28", typeColor[e.type] ?? "text-gray-400")}>
              {e.type}
            </span>
            <span className="text-gray-400">{e.detail}</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-gray-600 text-xs py-2">이벤트 없음</div>
        )}
      </div>
    </div>
  );
}
