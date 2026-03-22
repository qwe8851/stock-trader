/**
 * Analytics page — strategy performance + P&L history chart.
 *
 * Layout:
 *  ┌────────────────────────────────────────────────────┐
 *  │  Header + back link                                │
 *  ├──────────┬──────────┬──────────┬───────────────────┤
 *  │ P&L      │ Win Rate │ Sharpe   │ Max DD            │
 *  ├────────────────────────────────────────────────────┤
 *  │  P&L History Chart (TradingView line)              │
 *  ├────────────────────────────────────────────────────┤
 *  │  Strategy Performance Table                        │
 *  └────────────────────────────────────────────────────┘
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { createChart, ColorType, LineStyle } from "lightweight-charts";
import {
  fetchSummary,
  fetchPerformance,
  fetchPnlHistory,
  type StrategyPerformance,
} from "../api/analytics";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(v: number, decimals = 2) {
  return v.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function pnlColor(v: number) {
  return v > 0 ? "text-bull" : v < 0 ? "text-bear" : "text-gray-300";
}

// ── P&L History Chart ────────────────────────────────────────────────────────

function PnlChart() {
  const chartRef = useRef<HTMLDivElement>(null);
  const { data = [] } = useQuery({
    queryKey: ["pnl-history"],
    queryFn: () => fetchPnlHistory(168),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 260,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      rightPriceScale: { borderColor: "#374151" },
      timeScale: { borderColor: "#374151", timeVisible: true },
    });

    const series = chart.addLineSeries({
      color: "#6366f1",
      lineWidth: 2,
      crosshairMarkerVisible: true,
    });

    // 기준선 (초기 잔고)
    const initialValue = data[0]?.total_value_usd ?? 10000;
    series.createPriceLine({
      price: initialValue,
      color: "#4b5563",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Start",
    });

    const points = data.map((p) => ({
      time: Math.floor(new Date(p.time).getTime() / 1000) as any,
      value: p.total_value_usd,
    }));
    series.setData(points);
    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    });
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [data]);

  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wider text-gray-500 mb-3">
        포트폴리오 가치 이력
      </div>
      {data.length === 0 ? (
        <div
          className="flex items-center justify-center text-gray-600 text-sm"
          style={{ height: 260 }}
        >
          <div className="text-center">
            <div className="text-2xl mb-2 opacity-30">📉</div>
            <div>Celery Beat가 매 1시간마다 스냅샷을 저장합니다.</div>
          </div>
        </div>
      ) : (
        <div ref={chartRef} />
      )}
    </div>
  );
}

// ── Strategy Table ────────────────────────────────────────────────────────────

function StrategyTable({ rows }: { rows: StrategyPerformance[] }) {
  if (rows.length === 0) {
    return (
      <div className="card p-6 text-center text-gray-600 text-sm">
        아직 주문 데이터가 없습니다. 전략을 추가하고 잠시 기다려주세요.
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
        전략별 성과
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-800">
              {[
                "전략",
                "거래 수",
                "승률",
                "총 P&L",
                "수익률",
                "평균 수익",
                "평균 손실",
                "Profit Factor",
                "Sharpe",
                "Max DD",
              ].map((h) => (
                <th key={h} className="text-left px-4 py-2 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {rows.map((r) => (
              <tr
                key={r.strategy}
                className="hover:bg-surface-50 transition-colors"
              >
                <td className="px-4 py-3 font-mono text-xs text-brand">
                  {r.strategy}
                </td>
                <td className="px-4 py-3 tabular-nums">{r.total_trades}</td>
                <td
                  className={clsx(
                    "px-4 py-3 tabular-nums",
                    r.win_rate >= 0.5 ? "text-bull" : "text-bear"
                  )}
                >
                  {(r.win_rate * 100).toFixed(1)}%
                </td>
                <td
                  className={clsx("px-4 py-3 tabular-nums", pnlColor(r.total_pnl_usd))}
                >
                  {r.total_pnl_usd >= 0 ? "+" : ""}${fmt(r.total_pnl_usd)}
                </td>
                <td
                  className={clsx("px-4 py-3 tabular-nums", pnlColor(r.total_pnl_pct))}
                >
                  {r.total_pnl_pct >= 0 ? "+" : ""}
                  {fmt(r.total_pnl_pct)}%
                </td>
                <td className="px-4 py-3 tabular-nums text-bull">
                  +${fmt(r.avg_win_usd)}
                </td>
                <td className="px-4 py-3 tabular-nums text-bear">
                  ${fmt(r.avg_loss_usd)}
                </td>
                <td className="px-4 py-3 tabular-nums">
                  {r.profit_factor !== null ? fmt(r.profit_factor) : "∞"}
                </td>
                <td
                  className={clsx(
                    "px-4 py-3 tabular-nums",
                    r.sharpe_ratio >= 1
                      ? "text-bull"
                      : r.sharpe_ratio >= 0
                      ? "text-gray-300"
                      : "text-bear"
                  )}
                >
                  {fmt(r.sharpe_ratio, 3)}
                </td>
                <td className="px-4 py-3 tabular-nums text-bear">
                  {fmt(r.max_drawdown_pct)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Analytics() {
  const { data: summary, isLoading: sumLoading } = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: fetchSummary,
    refetchInterval: 10_000,
  });

  const { data: performance = [], isLoading: perfLoading } = useQuery({
    queryKey: ["analytics-performance"],
    queryFn: fetchPerformance,
    refetchInterval: 10_000,
  });

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <Link
          to="/dashboard"
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          ← 대시보드
        </Link>
        <span className="font-semibold text-lg">성과 분석</span>
        {summary && (
          <span
            className={clsx(
              "ml-auto text-xs px-2 py-1 rounded",
              summary.paper_mode
                ? "bg-yellow-900/30 text-yellow-400"
                : "bg-red-900/30 text-red-400"
            )}
          >
            {summary.paper_mode ? "PAPER" : "LIVE"} · {summary.exchange}
          </span>
        )}
      </header>

      <div className="px-6 py-6 space-y-6">
        {/* ── Summary Cards ─────────────────────────────────────────────── */}
        {sumLoading || !summary ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="card px-4 py-3 h-20 animate-pulse bg-gray-800/50" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetricCard
              label="총 P&L"
              value={`${summary.total_pnl_usd >= 0 ? "+" : ""}$${fmt(summary.total_pnl_usd)}`}
              sub={`${summary.total_pnl_pct >= 0 ? "+" : ""}${fmt(summary.total_pnl_pct)}%`}
              valueClass={pnlColor(summary.total_pnl_usd)}
            />
            <MetricCard
              label="승률"
              value={`${(summary.win_rate * 100).toFixed(1)}%`}
              sub={`${summary.completed_trades}/${summary.total_trades} 거래 완결`}
              valueClass={summary.win_rate >= 0.5 ? "text-bull" : "text-bear"}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={fmt(summary.sharpe_ratio, 3)}
              sub={">1 양호 / >2 우수"}
              valueClass={
                summary.sharpe_ratio >= 2
                  ? "text-bull"
                  : summary.sharpe_ratio >= 1
                  ? "text-yellow-400"
                  : "text-bear"
              }
            />
            <MetricCard
              label="Max Drawdown"
              value={`${fmt(summary.max_drawdown_pct)}%`}
              sub={`총 거래: ${summary.total_trades}회`}
              valueClass={
                summary.max_drawdown_pct < 5
                  ? "text-bull"
                  : summary.max_drawdown_pct < 15
                  ? "text-yellow-400"
                  : "text-bear"
              }
            />
          </div>
        )}

        {/* ── P&L History Chart ──────────────────────────────────────────── */}
        <PnlChart />

        {/* ── Strategy Table ─────────────────────────────────────────────── */}
        {perfLoading ? (
          <div className="card p-6 h-40 animate-pulse bg-gray-800/50" />
        ) : (
          <StrategyTable rows={performance} />
        )}
      </div>
    </div>
  );
}

// ── Metric Card ───────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  sub: string;
  valueClass?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">
        {label}
      </div>
      <div className={clsx("font-mono text-xl font-bold tabular-nums", valueClass)}>
        {value}
      </div>
      <div className="text-xs text-gray-600 mt-1">{sub}</div>
    </div>
  );
}
