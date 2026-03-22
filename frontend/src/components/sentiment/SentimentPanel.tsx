import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchSentiment, triggerSentimentRefresh, type NewsItem } from "../../api/sentiment";

interface Props {
  symbol: string;
}

export function SentimentPanel({ symbol }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sentiment", symbol],
    queryFn: () => fetchSentiment(symbol),
    refetchInterval: 5 * 60 * 1000, // refetch every 5 min
    retry: 1,
  });

  const refreshMutation = useMutation({
    mutationFn: () => triggerSentimentRefresh(symbol),
    onSuccess: () => {
      // Invalidate after short delay so Celery task has time to complete
      setTimeout(() => qc.invalidateQueries({ queryKey: ["sentiment", symbol] }), 5000);
    },
  });

  if (isLoading) {
    return <div className="bg-surface-2 rounded-xl p-5 animate-pulse h-48" />;
  }

  if (isError || !data) {
    return (
      <div className="bg-surface-2 rounded-xl p-5">
        <p className="text-gray-500 text-sm text-center py-4">
          Sentiment data unavailable — FinBERT loading...
        </p>
      </div>
    );
  }

  return (
    <div className="bg-surface-2 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          AI Sentiment · {symbol}
        </h2>
        <div className="flex items-center gap-2">
          {data.cached && (
            <span className="text-xs text-gray-600">cached</span>
          )}
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="text-xs text-gray-500 hover:text-white transition-colors disabled:opacity-40"
          >
            {refreshMutation.isPending ? "Refreshing..." : "↻ Refresh"}
          </button>
        </div>
      </div>

      {/* Score gauge */}
      <SentimentGauge score={data.score} label={data.label} />

      {/* Updated at */}
      <p className="text-xs text-gray-600">
        Updated {new Date(data.updated_at).toLocaleTimeString()}
      </p>

      {/* News feed */}
      {data.items.length > 0 && (
        <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
          {data.items.map((item, i) => (
            <NewsFeedItem key={i} item={item} />
          ))}
        </div>
      )}

      {data.items.length === 0 && (
        <p className="text-gray-600 text-xs text-center py-2">No recent news</p>
      )}
    </div>
  );
}

// ── Sentiment Gauge ───────────────────────────────────────────────────────────

function SentimentGauge({
  score,
  label,
}: {
  score: number;
  label: string;
}) {
  // Map score [-1, +1] → position [0%, 100%] on the bar
  const pct = Math.round(((score + 1) / 2) * 100);

  const labelColor =
    label === "positive"
      ? "text-bull"
      : label === "negative"
      ? "text-bear"
      : "text-gray-400";

  const barColor =
    label === "positive"
      ? "bg-bull"
      : label === "negative"
      ? "bg-bear"
      : "bg-gray-500";

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className={`text-2xl font-bold font-mono ${labelColor}`}>
          {score >= 0 ? "+" : ""}
          {score.toFixed(3)}
        </span>
        <span className={`text-sm font-semibold capitalize ${labelColor}`}>
          {label}
        </span>
      </div>

      {/* Gradient bar: red ← center → green */}
      <div className="relative h-3 rounded-full overflow-hidden bg-gradient-to-r from-bear via-gray-700 to-bull">
        {/* Pointer */}
        <div
          className={`absolute top-0 w-3 h-3 rounded-full border-2 border-white shadow ${barColor} transition-all duration-500`}
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-600">
        <span>Bearish -1</span>
        <span>Neutral 0</span>
        <span>Bullish +1</span>
      </div>
    </div>
  );
}

// ── News Feed Item ────────────────────────────────────────────────────────────

function NewsFeedItem({ item }: { item: NewsItem }) {
  const score = item.sentiment_score;
  const scoreColor =
    score === null
      ? "text-gray-600"
      : score >= 0.1
      ? "text-bull"
      : score <= -0.1
      ? "text-bear"
      : "text-gray-400";

  return (
    <div className="flex items-start gap-2 text-xs group">
      {/* Sentiment score pill */}
      <span className={`shrink-0 font-mono w-12 text-right ${scoreColor}`}>
        {score !== null ? (score >= 0 ? "+" : "") + score.toFixed(2) : "—"}
      </span>

      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-gray-300 hover:text-white line-clamp-2 transition-colors leading-snug"
        title={item.title}
      >
        {item.title}
      </a>
    </div>
  );
}
