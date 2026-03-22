import { useQuery } from "@tanstack/react-query";
import { fetchPortfolio } from "../../api/portfolio";

export function PortfolioCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["portfolio"],
    queryFn: fetchPortfolio,
    refetchInterval: 5000,
  });

  if (isLoading || !data) {
    return (
      <div className="bg-surface-2 rounded-xl p-5 animate-pulse h-40" />
    );
  }

  const pnlPositive = data.pnl_usd >= 0;

  return (
    <div className="bg-surface-2 rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          Portfolio
        </h2>
        <div className="flex gap-2">
          {data.paper_mode && (
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full">
              Paper
            </span>
          )}
          {data.risk_halted && (
            <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
              Halted
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Total Value" value={`$${data.total_value_usd.toLocaleString()}`} />
        <Stat label="Available" value={`$${data.available_usd.toLocaleString()}`} />
        <Stat
          label="P&L"
          value={`${pnlPositive ? "+" : ""}$${data.pnl_usd.toFixed(2)}`}
          valueClass={pnlPositive ? "text-bull" : "text-bear"}
          sub={`${pnlPositive ? "+" : ""}${data.pnl_pct.toFixed(2)}%`}
        />
        <Stat label="Open Positions" value={String(data.open_positions)} />
      </div>

      {Object.keys(data.holdings).length > 0 && (
        <div className="border-t border-white/5 pt-3">
          <p className="text-xs text-gray-500 mb-2">Holdings</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.holdings).map(([asset, qty]) => (
              <span
                key={asset}
                className="text-xs bg-surface-3 px-2 py-1 rounded-lg text-gray-300"
              >
                {asset}: {Number(qty).toFixed(6)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold ${valueClass}`}>{value}</p>
      {sub && <p className={`text-xs ${valueClass} opacity-80`}>{sub}</p>}
    </div>
  );
}
