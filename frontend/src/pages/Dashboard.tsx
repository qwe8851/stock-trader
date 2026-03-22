/**
 * Dashboard - Main trading dashboard page.
 *
 * Layout:
 *  ┌─────────────────────────────────────────────┐
 *  │  Header: Logo + Symbol selector            │
 *  ├──────────────┬──────────────────────────────┤
 *  │  Price hero  │  Connection status           │
 *  ├──────────────┴──────────────────────────────┤
 *  │  Candlestick chart (full width)             │
 *  ├─────────────────────────────────────────────┤
 *  │  Stats row: Vol, Change, High, Low          │
 *  └─────────────────────────────────────────────┘
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import CandlestickChart from "../components/charts/CandlestickChart";
import { PortfolioCard } from "../components/portfolio/PortfolioCard";
import { OrdersTable } from "../components/orders/OrdersTable";
import { StrategyPanel } from "../components/strategies/StrategyPanel";
import { SentimentPanel } from "../components/sentiment/SentimentPanel";
import { usePriceFeed } from "../hooks/usePriceFeed";
import { clsx } from "clsx";

// Supported symbols for Phase 1
const SYMBOLS = [
  { value: "BTCUSDT", label: "BTC / USDT" },
  { value: "ETHUSDT", label: "ETH / USDT" },
  { value: "SOLUSDT", label: "SOL / USDT" },
];

function formatPrice(price: number | null): string {
  if (price === null) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

function formatVolume(volume: number): string {
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(2)}M`;
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(2)}K`;
  return volume.toFixed(2);
}

export default function Dashboard() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const { price, candles, isConnected, change } = usePriceFeed(symbol);

  const latestCandle = candles[candles.length - 1];
  const prevCandle = candles[candles.length - 2];

  const periodHigh = candles.length > 0
    ? Math.max(...candles.map((c) => c.high))
    : null;
  const periodLow = candles.length > 0
    ? Math.min(...candles.map((c) => c.low))
    : null;

  const isUp = change ? change.direction === "up" : null;
  const priceColour =
    isUp === true
      ? "text-bull"
      : isUp === false
      ? "text-bear"
      : "text-gray-300";

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="w-5 h-5 text-white"
            >
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

        {/* Symbol selector + nav links */}
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            {SYMBOLS.map((s) => (
              <button
                key={s.value}
                onClick={() => setSymbol(s.value)}
                className={clsx(
                  "px-4 py-1.5 text-sm font-medium transition-colors",
                  symbol === s.value
                    ? "bg-brand text-white"
                    : "bg-surface-100 text-gray-400 hover:text-white hover:bg-surface-50"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
          <Link
            to="/analytics"
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
          >
            분석
          </Link>
          <Link
            to="/backtest"
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
          >
            백테스트
          </Link>
          <Link
            to="/settings"
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
          >
            설정
          </Link>
        </div>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Price Hero + Connection Status                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-6 py-5 flex flex-wrap items-start gap-6 border-b border-gray-800">
        {/* Current price */}
        <div className="flex-1 min-w-[200px]">
          <div className="text-xs uppercase tracking-widest text-gray-500 mb-1">
            {symbol.replace("USDT", " / USDT")}
          </div>
          <div
            className={clsx(
              "font-mono text-5xl font-bold tabular-nums transition-colors duration-300",
              priceColour
            )}
          >
            ${formatPrice(price)}
          </div>

          {change && (
            <div className="mt-2 flex items-center gap-2">
              <span
                className={clsx(
                  "text-sm font-mono font-medium",
                  change.direction === "up" ? "text-bull" : change.direction === "down" ? "text-bear" : "text-gray-400"
                )}
              >
                {change.direction === "up" ? "▲" : change.direction === "down" ? "▼" : "—"}
                &nbsp;{Math.abs(change.value).toFixed(2)}&nbsp;
                ({change.percent >= 0 ? "+" : ""}{change.percent.toFixed(2)}%)
              </span>
              <span className="text-xs text-gray-600">last {candles.length} candles</span>
            </div>
          )}
        </div>

        {/* Connection status */}
        <div className="flex flex-col items-end gap-1">
          <div
            className={clsx(
              "flex items-center gap-2 text-sm font-medium",
              isConnected ? "text-bull" : "text-gray-500"
            )}
          >
            <span
              className={clsx(
                "w-2 h-2 rounded-full",
                isConnected
                  ? "bg-bull animate-pulse"
                  : "bg-gray-600"
              )}
            />
            {isConnected ? "Live" : "Connecting…"}
          </div>
          <div className="text-xs text-gray-600">
            WebSocket · Binance
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Chart                                                                */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-4 pt-4 pb-2 flex-1">
        <div className="card p-0 overflow-hidden">
          {candles.length === 0 ? (
            <div
              className="flex items-center justify-center text-gray-600 text-sm"
              style={{ height: 480 }}
            >
              <div className="text-center">
                <div className="text-3xl mb-3 opacity-30">📈</div>
                <div>Loading chart data…</div>
              </div>
            </div>
          ) : (
            <CandlestickChart candles={candles} height={480} />
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Stats Row                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-6 py-4 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-gray-800">
        <StatCard
          label="Period High"
          value={periodHigh !== null ? `$${formatPrice(periodHigh)}` : "—"}
          valueClass="text-bull"
        />
        <StatCard
          label="Period Low"
          value={periodLow !== null ? `$${formatPrice(periodLow)}` : "—"}
          valueClass="text-bear"
        />
        <StatCard
          label="Last Volume"
          value={latestCandle ? formatVolume(latestCandle.volume) : "—"}
        />
        <StatCard
          label="Prev Close"
          value={prevCandle ? `$${formatPrice(prevCandle.close)}` : "—"}
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Phase 2 panels                                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-6 pb-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-3">
          <PortfolioCard />
        </div>
        <div className="lg:col-span-1 space-y-4">
          <StrategyPanel />
          <SentimentPanel symbol={symbol} />
        </div>
        <div className="lg:col-span-2">
          <OrdersTable />
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                               */}
      {/* ------------------------------------------------------------------ */}
      <footer className="border-t border-gray-800 px-6 py-3 flex justify-between items-center text-xs text-gray-600">
        <span>Phase 5 · Live Trading + Multi-Exchange · Binance / Upbit</span>
        <span>{new Date().toLocaleDateString()}</span>
      </footer>
    </div>
  );
}

// ── Stat card sub-component ───────────────────────────────────────────────────

function StatCard({
  label,
  value,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">
        {label}
      </div>
      <div className={clsx("font-mono text-base font-semibold tabular-nums", valueClass)}>
        {value}
      </div>
    </div>
  );
}
