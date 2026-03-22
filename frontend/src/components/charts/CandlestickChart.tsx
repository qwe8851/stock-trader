/**
 * CandlestickChart - TradingView Lightweight Charts wrapper.
 *
 * Renders a dark-themed candlestick chart that:
 *  - Fills its container responsively via ResizeObserver
 *  - Applies the candles data on initial render
 *  - Updates the last candle (or appends a new one) on every data change
 *    without re-creating the entire chart
 *  - Shows a volume histogram below the price pane
 */
import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
  type HistogramSeriesOptions,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { Candle } from "../../hooks/usePriceFeed";

interface CandlestickChartProps {
  candles: Candle[];
  /** Height in pixels. Defaults to 480. */
  height?: number;
}

// Chart colour palette
const PALETTE = {
  background: "#0f0f14",
  surface: "#16161f",
  grid: "#1e1e2a",
  text: "#94a3b8",
  border: "#1e1e2a",
  bull: "#26a69a",
  bear: "#ef5350",
  bullWick: "#26a69a",
  bearWick: "#ef5350",
  volume: {
    bull: "rgba(38, 166, 154, 0.4)",
    bear: "rgba(239, 83, 80, 0.4)",
  },
} as const;

export default function CandlestickChart({
  candles,
  height = 480,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  // Track the last candle time we rendered to decide update vs. append
  const lastCandleTimeRef = useRef<number | null>(null);

  // ---------------------------------------------------------------------------
  // Create chart on mount; destroy on unmount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: PALETTE.background },
        textColor: PALETTE.text,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: PALETTE.grid },
        horzLines: { color: PALETTE.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#4b5563",
          labelBackgroundColor: "#374151",
        },
        horzLine: {
          color: "#4b5563",
          labelBackgroundColor: "#374151",
        },
      },
      rightPriceScale: {
        borderColor: PALETTE.border,
        textColor: PALETTE.text,
      },
      timeScale: {
        borderColor: PALETTE.border,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: PALETTE.bull,
      downColor: PALETTE.bear,
      borderUpColor: PALETTE.bull,
      borderDownColor: PALETTE.bear,
      wickUpColor: PALETTE.bullWick,
      wickDownColor: PALETTE.bearWick,
    } as Partial<CandlestickSeriesOptions>);

    // Volume histogram series (scaled to 15% of chart height)
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    } as Partial<HistogramSeriesOptions>);

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.88, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // ResizeObserver to fill container width
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry && chartRef.current) {
        chartRef.current.applyOptions({
          width: entry.contentRect.width,
        });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      lastCandleTimeRef.current = null;
    };
  }, [height]);

  // ---------------------------------------------------------------------------
  // Update chart data when candles change
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const chart = chartRef.current;

    if (!candleSeries || !volumeSeries || !chart || candles.length === 0) return;

    const latestCandle = candles[candles.length - 1];

    if (lastCandleTimeRef.current === null) {
      // First render: set all data at once
      candleSeries.setData(
        candles.map(({ time, open, high, low, close }) => ({
          time: time as unknown as import("lightweight-charts").Time,
          open,
          high,
          low,
          close,
        }))
      );

      volumeSeries.setData(
        candles.map(({ time, open, close, volume }) => ({
          time: time as unknown as import("lightweight-charts").Time,
          value: volume,
          color: close >= open ? PALETTE.volume.bull : PALETTE.volume.bear,
        }))
      );

      // Scroll to the right so latest candle is visible
      chart.timeScale().scrollToRealTime();
    } else {
      // Subsequent renders: update only the last candle (or append new one)
      const { time, open, high, low, close, volume } = latestCandle;
      candleSeries.update({
        time: time as unknown as import("lightweight-charts").Time,
        open,
        high,
        low,
        close,
      });
      volumeSeries.update({
        time: time as unknown as import("lightweight-charts").Time,
        value: volume,
        color: close >= open ? PALETTE.volume.bull : PALETTE.volume.bear,
      });
    }

    lastCandleTimeRef.current = latestCandle.time;
  }, [candles]);

  return (
    <div
      ref={containerRef}
      className="w-full rounded-lg overflow-hidden"
      style={{ height }}
    />
  );
}
