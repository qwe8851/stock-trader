"""
Trading Engine — the central async event loop.

Flow:
  1. Subscribe to Redis pub/sub for live price ticks (published by exchange adapter)
  2. Convert each tick to a Candle and feed it to all active strategies
  3. Pass any actionable Signal through RiskManager
  4. If approved, execute via OrderManager (paper or live)

Exchange support:
  - Binance (USDT markets, default)
  - Upbit (KRW markets, optional)
"""
import asyncio
import json
from datetime import date, datetime, timezone
from typing import Any

from adapters.base import BaseExchangeAdapter
from core.config import settings
from core.logging import get_logger
from db.redis import get_redis
from engine.order_manager import OrderManager
from engine.risk_manager import PortfolioSnapshot, RiskConfig, RiskManager
from engine.strategies.base import BaseStrategy, Candle, Signal, SignalAction
from engine.strategies.macd_strategy import MACDStrategy
from engine.strategies.rsi_strategy import RSIStrategy
from engine.strategies.sentiment_strategy import SentimentStrategy

logger = get_logger(__name__)

# Registry of available strategy classes
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "RSI": RSIStrategy,
    "MACD": MACDStrategy,
    "SENTIMENT": SentimentStrategy,
}


class TradingEngine:
    """
    Singleton-style engine instantiated once at application startup.
    Controlled via the REST API (/api/strategies endpoints).
    """

    def __init__(self) -> None:
        self._risk = RiskManager(RiskConfig(
            max_position_pct=settings.RISK_MAX_POSITION_PCT,
            daily_loss_limit_pct=settings.RISK_DAILY_LOSS_LIMIT_PCT,
            max_open_positions=settings.RISK_MAX_OPEN_POSITIONS,
        ))
        self._orders = OrderManager()
        # symbol -> list of active strategy instances
        self._strategies: dict[str, list[BaseStrategy]] = {}
        # Track daily start value for drawdown calculation
        self._daily_start_value: float = settings.PAPER_INITIAL_BALANCE
        self._daily_date: date = datetime.now(timezone.utc).date()
        # Latest price per symbol (for portfolio valuation)
        self._latest_prices: dict[str, float] = {}
        self._running = False
        # Active exchange adapter (injected from api/main.py)
        self._adapter: BaseExchangeAdapter | None = None
        self._exchange_name: str = settings.ACTIVE_EXCHANGE

    # ------------------------------------------------------------------
    # Strategy management (called from REST API)
    # ------------------------------------------------------------------

    def add_strategy(
        self,
        strategy_name: str,
        symbol: str,
        config: dict[str, Any] | None = None,
    ) -> BaseStrategy:
        cls = STRATEGY_REGISTRY.get(strategy_name.upper())
        if cls is None:
            raise ValueError(f"Unknown strategy '{strategy_name}'. "
                             f"Available: {list(STRATEGY_REGISTRY.keys())}")
        strategy = cls(symbol=symbol, config=config or {})
        self._strategies.setdefault(symbol.upper(), []).append(strategy)
        logger.info("Strategy added", extra={
            "strategy": strategy.name, "symbol": symbol,
        })
        return strategy

    def remove_strategy(self, strategy_name: str, symbol: str) -> bool:
        sym = symbol.upper()
        before = len(self._strategies.get(sym, []))
        self._strategies[sym] = [
            s for s in self._strategies.get(sym, [])
            if s.name != strategy_name.upper()
        ]
        removed = before - len(self._strategies.get(sym, []))
        if removed:
            logger.info("Strategy removed", extra={"strategy": strategy_name, "symbol": sym})
        return removed > 0

    def list_strategies(self) -> list[dict[str, Any]]:
        result = []
        for symbol, strategies in self._strategies.items():
            for s in strategies:
                result.append({
                    "name": s.name,
                    "symbol": symbol,
                    "config": s.config,
                    "candles_loaded": len(s._candles),
                    "min_candles": s.min_candles,
                    "ready": len(s._candles) >= s.min_candles,
                })
        return result

    def set_adapter(self, adapter: BaseExchangeAdapter, exchange_name: str) -> None:
        """Inject the active exchange adapter. Called by api/main.py on startup."""
        self._adapter = adapter
        self._exchange_name = exchange_name
        logger.info("Exchange adapter set", extra={"exchange": exchange_name})

    def get_status(self) -> dict[str, Any]:
        portfolio_value = self._orders.portfolio_value_usd(self._latest_prices)
        return {
            "running": self._running,
            "paper_mode": settings.PAPER_TRADING_MODE,
            "live_trading_enabled": settings.LIVE_TRADING_ENABLED,
            "exchange": self._exchange_name,
            "risk_halted": self._risk.is_halted,
            "strategies": self.list_strategies(),
            "portfolio": {
                "total_value_usd": round(portfolio_value, 2),
                "available_usd": round(self._orders.available_usd, 2),
                "holdings": self._orders.get_holdings(),
                "daily_start_value": round(self._daily_start_value, 2),
                "open_positions": self._orders.open_positions,
            },
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Subscribe to all price channels in Redis and process incoming ticks.
        This coroutine runs indefinitely as a background task.
        """
        self._running = True
        logger.info("TradingEngine started")

        # Default strategies on startup
        if not self._strategies:
            self.add_strategy("RSI", "BTCUSDT")
            self.add_strategy("MACD", "BTCUSDT")

        redis = get_redis()
        pubsub = redis.pubsub()

        # Subscribe to all symbols that have active strategies
        channels = [f"prices:{sym}" for sym in self._strategies]
        if not channels:
            logger.warning("No active strategies, engine idle")
            return

        await pubsub.subscribe(*channels)
        logger.info("TradingEngine subscribed to price channels",
                    extra={"channels": channels})

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await self._on_tick(data)
                except Exception as exc:
                    logger.error("Error processing tick",
                                 extra={"error": str(exc)})
        except asyncio.CancelledError:
            logger.info("TradingEngine cancelled")
            self._running = False
            await pubsub.unsubscribe()
            raise
        finally:
            self._running = False

    async def _publish_portfolio_snapshot(self) -> None:
        """최신 포트폴리오 상태를 Redis에 저장 (Celery analytics task가 읽음)."""
        try:
            redis = get_redis()
            snap = {
                "total_value_usd": self._orders.portfolio_value_usd(self._latest_prices),
                "available_usd": self._orders.available_usd,
                "open_positions": self._orders.open_positions,
                "daily_start_value": self._daily_start_value,
                "exchange": self._exchange_name,
            }
            await redis.set("engine:portfolio_snapshot", json.dumps(snap), ex=7200)
        except Exception:
            pass   # 스냅샷 실패는 거래에 영향 없음

    async def _on_tick(self, data: dict[str, Any]) -> None:
        symbol: str = data.get("symbol", "BTCUSDT")
        close: float = float(data.get("close", 0))
        if close <= 0:
            return

        self._latest_prices[symbol] = close
        self._refresh_daily_start()
        # 100번째 틱마다 Redis 스냅샷 갱신
        self._tick_count = getattr(self, "_tick_count", 0) + 1
        if self._tick_count % 100 == 0:
            await self._publish_portfolio_snapshot()

        candle = Candle(
            time=data["time"],
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=close,
            volume=float(data["volume"]),
            symbol=symbol,
            is_closed=data.get("is_closed", False),
        )

        for strategy in self._strategies.get(symbol, []):
            signal = strategy.on_candle(candle)
            if not signal.is_actionable:
                continue

            # Inject strategy name into metadata for order tracking
            signal.metadata["strategy"] = strategy.name

            portfolio = PortfolioSnapshot(
                total_value_usd=self._orders.portfolio_value_usd(self._latest_prices),
                open_positions=self._orders.open_positions,
                daily_start_value=self._daily_start_value,
            )

            approved, reason = self._risk.check(signal, portfolio)
            if not approved:
                logger.debug("Signal rejected by RiskManager",
                             extra={"reason": reason, "signal": signal.action})
                continue

            size_usd = self._risk.position_size_usd(portfolio, signal.confidence)

            await self._orders.execute(
                signal=signal,
                size_usd=size_usd,
                current_price=close,
                adapter=self._adapter,
            )

    def _refresh_daily_start(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_start_value = self._orders.portfolio_value_usd(self._latest_prices)
            logger.info("Daily start value reset",
                        extra={"value": self._daily_start_value})

    # Expose OrderManager for API routers
    @property
    def order_manager(self) -> OrderManager:
        return self._orders

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk


# Global engine instance — initialised at FastAPI startup
engine = TradingEngine()
