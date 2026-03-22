/**
 * usePriceFeed - Real-time WebSocket price feed hook.
 *
 * Connects to /ws/prices/{symbol}, handles reconnection automatically,
 * and seeds the chart with historical data from the REST API on mount.
 *
 * Returns:
 *   price      - Latest close price (number | null)
 *   candles    - Full OHLCV history for charting
 *   isConnected - Whether the WebSocket is currently open
 *   change24h  - Price change object (populated from candles)
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface Candle {
  time: number;   // Unix seconds (lightweight-charts expects seconds)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface RawCandle {
  time: number;   // Unix milliseconds from backend
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed?: boolean;
  symbol?: string;
  interval?: string;
}

interface PriceFeedState {
  price: number | null;
  candles: Candle[];
  isConnected: boolean;
  change: {
    value: number;
    percent: number;
    direction: "up" | "down" | "flat";
  } | null;
}

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const RECONNECT_INITIAL_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
const HISTORY_LIMIT = 200;

function msToSec(ms: number): number {
  return Math.floor(ms / 1000);
}

export function usePriceFeed(symbol: string): PriceFeedState {
  const [state, setState] = useState<PriceFeedState>({
    price: null,
    candles: [],
    isConnected: false,
    change: null,
  });

  // Ref to the candles array so the WS handler can read without stale closure
  const candlesRef = useRef<Candle[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(RECONNECT_INITIAL_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // ---------------------------------------------------------------------------
  // Fetch historical candles once on mount (or symbol change)
  // ---------------------------------------------------------------------------
  const loadHistory = useCallback(async () => {
    try {
      const url = `${API_BASE}/api/ohlcv/${symbol}?interval=1m&limit=${HISTORY_LIMIT}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();

      const candles: Candle[] = (json.data as RawCandle[]).map((c) => ({
        time: msToSec(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }));

      // Sort ascending by time (chart requires this)
      candles.sort((a, b) => a.time - b.time);
      candlesRef.current = candles;

      const latest = candles[candles.length - 1];
      const first = candles[0];
      const changeValue = latest ? latest.close - first.close : 0;
      const changePct = first ? (changeValue / first.close) * 100 : 0;

      if (mountedRef.current) {
        setState((prev) => ({
          ...prev,
          candles,
          price: latest?.close ?? prev.price,
          change: {
            value: changeValue,
            percent: changePct,
            direction:
              changeValue > 0 ? "up" : changeValue < 0 ? "down" : "flat",
          },
        }));
      }
    } catch (err) {
      console.warn("[usePriceFeed] Failed to load history:", err);
    }
  }, [symbol]);

  // ---------------------------------------------------------------------------
  // WebSocket connection with auto-reconnect
  // ---------------------------------------------------------------------------
  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current) {
      wsRef.current.close();
    }

    const wsUrl = `${WS_BASE}/ws/prices/${symbol}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      reconnectDelayRef.current = RECONNECT_INITIAL_MS;
      setState((prev) => ({ ...prev, isConnected: true }));
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(event.data as string) as RawCandle & {
          type?: string;
        };

        // Ignore meta messages (subscribed acknowledgement, errors)
        if (msg.type === "subscribed" || msg.type === "error") return;

        const incomingTime = msToSec(msg.time);
        const newCandle: Candle = {
          time: incomingTime,
          open: msg.open,
          high: msg.high,
          low: msg.low,
          close: msg.close,
          volume: msg.volume,
        };

        // Merge into candles: update last candle if same time, else append
        const prev = candlesRef.current;
        let updated: Candle[];
        if (prev.length > 0 && prev[prev.length - 1].time === incomingTime) {
          updated = [...prev.slice(0, -1), newCandle];
        } else {
          // Keep last 500 candles to avoid unbounded memory growth
          updated = [...prev, newCandle].slice(-500);
        }
        candlesRef.current = updated;

        const first = updated[0];
        const changeValue = newCandle.close - first.close;
        const changePct = first ? (changeValue / first.close) * 100 : 0;

        setState({
          price: newCandle.close,
          candles: updated,
          isConnected: true,
          change: {
            value: changeValue,
            percent: changePct,
            direction:
              changeValue > 0 ? "up" : changeValue < 0 ? "down" : "flat",
          },
        });
      } catch (err) {
        console.warn("[usePriceFeed] Failed to parse message:", err);
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose; handle reconnect there
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setState((prev) => ({ ...prev, isConnected: false }));

      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, RECONNECT_MAX_MS);

      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    };
  }, [symbol]);

  // ---------------------------------------------------------------------------
  // Effect: connect on mount / symbol change, cleanup on unmount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    mountedRef.current = true;
    candlesRef.current = [];
    setState({ price: null, candles: [], isConnected: false, change: null });

    loadHistory();
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [symbol, loadHistory, connect]);

  return state;
}
