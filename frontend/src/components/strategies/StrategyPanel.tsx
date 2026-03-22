import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchStrategies,
  addStrategy,
  removeStrategy,
  resumeTrading,
  type StrategyInfo,
} from "../../api/strategies";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

export function StrategyPanel() {
  const qc = useQueryClient();
  const [selectedName, setSelectedName] = useState("RSI");
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");

  const { data } = useQuery({
    queryKey: ["strategies"],
    queryFn: fetchStrategies,
    refetchInterval: 5000,
  });

  const addMutation = useMutation({
    mutationFn: () => addStrategy(selectedName, selectedSymbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });

  const removeMutation = useMutation({
    mutationFn: ({ name, symbol }: { name: string; symbol: string }) =>
      removeStrategy(name, symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });

  const resumeMutation = useMutation({
    mutationFn: resumeTrading,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });

  const strategies = data?.strategies ?? [];
  const available = data?.available ?? ["RSI", "MACD"];
  const riskHalted = (data?.status as any)?.risk_halted ?? false;

  return (
    <div className="bg-surface-2 rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          Strategies
        </h2>
        {riskHalted && (
          <button
            onClick={() => resumeMutation.mutate()}
            className="text-xs bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 px-3 py-1 rounded-full transition-colors"
          >
            Resume Trading
          </button>
        )}
      </div>

      {/* Active strategies */}
      {strategies.length === 0 ? (
        <p className="text-gray-500 text-sm">No active strategies</p>
      ) : (
        <div className="space-y-2">
          {strategies.map((s) => (
            <StrategyRow
              key={`${s.name}-${s.symbol}`}
              strategy={s}
              onRemove={() => removeMutation.mutate({ name: s.name, symbol: s.symbol })}
            />
          ))}
        </div>
      )}

      {/* Add strategy form */}
      <div className="border-t border-white/5 pt-4 flex gap-2 flex-wrap">
        <select
          value={selectedName}
          onChange={(e) => setSelectedName(e.target.value)}
          className="bg-surface-3 text-white text-sm rounded-lg px-3 py-1.5 border border-white/10 focus:outline-none focus:border-brand"
        >
          {available.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>

        <select
          value={selectedSymbol}
          onChange={(e) => setSelectedSymbol(e.target.value)}
          className="bg-surface-3 text-white text-sm rounded-lg px-3 py-1.5 border border-white/10 focus:outline-none focus:border-brand"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <button
          onClick={() => addMutation.mutate()}
          disabled={addMutation.isPending}
          className="bg-brand hover:bg-brand/80 text-white text-sm font-medium px-4 py-1.5 rounded-lg transition-colors disabled:opacity-50"
        >
          {addMutation.isPending ? "Adding..." : "+ Add"}
        </button>

        {addMutation.isError && (
          <p className="text-red-400 text-xs self-center">
            {(addMutation.error as Error).message}
          </p>
        )}
      </div>
    </div>
  );
}

function StrategyRow({
  strategy,
  onRemove,
}: {
  strategy: StrategyInfo;
  onRemove: () => void;
}) {
  const warmupPct = Math.min(
    100,
    Math.round((strategy.candles_loaded / strategy.min_candles) * 100)
  );

  return (
    <div className="flex items-center justify-between bg-surface-3 rounded-lg px-3 py-2">
      <div className="flex items-center gap-3">
        <div
          className={`w-2 h-2 rounded-full ${
            strategy.ready ? "bg-bull" : "bg-yellow-400"
          }`}
        />
        <div>
          <p className="text-sm font-medium">
            {strategy.name}
            <span className="text-gray-500 ml-1 text-xs">/ {strategy.symbol}</span>
          </p>
          {!strategy.ready && (
            <div className="flex items-center gap-2 mt-0.5">
              <div className="w-20 h-1 bg-white/10 rounded-full overflow-hidden">
                <div
                  className="h-full bg-yellow-400 rounded-full transition-all"
                  style={{ width: `${warmupPct}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {strategy.candles_loaded}/{strategy.min_candles}
              </span>
            </div>
          )}
        </div>
      </div>

      <button
        onClick={onRemove}
        className="text-gray-600 hover:text-red-400 text-xs transition-colors"
      >
        Remove
      </button>
    </div>
  );
}
