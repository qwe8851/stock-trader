"""
Order Manager — translates signals into orders.

In PAPER trading mode (default) all orders are simulated at the current
close price. No real exchange calls are made.

In LIVE mode the adapter's place_order() is called. LIVE mode is only
available when LIVE_TRADING_ENABLED=true in the environment.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from core.config import settings
from core.logging import get_logger
from engine.strategies.base import Signal, SignalAction

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderManager:
    """
    Manages the full order lifecycle.

    Paper orders are stored in-memory and exposed via the REST API.
    A future Phase 5 PR will persist them to PostgreSQL.
    """

    def __init__(self) -> None:
        # In-memory store: order_id -> order dict
        self._orders: dict[str, dict[str, Any]] = {}
        # Simulated portfolio: asset -> quantity
        self._holdings: dict[str, float] = {}
        # Starting paper balance in USDT
        self._paper_balance_usd: float = settings.PAPER_INITIAL_BALANCE
        self._available_usd: float = settings.PAPER_INITIAL_BALANCE
        self._open_positions: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available_usd(self) -> float:
        return self._available_usd

    @property
    def open_positions(self) -> int:
        return self._open_positions

    def portfolio_value_usd(self, current_prices: dict[str, float]) -> float:
        """Approximate total portfolio value using current prices."""
        holdings_value = sum(
            qty * current_prices.get(asset + "USDT", 0)
            for asset, qty in self._holdings.items()
        )
        return self._available_usd + holdings_value

    def get_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        orders = list(self._orders.values())
        orders.sort(key=lambda o: o["created_at"], reverse=True)
        return orders[:limit]

    def get_holdings(self) -> dict[str, float]:
        return dict(self._holdings)

    async def execute(
        self,
        signal: Signal,
        size_usd: float,
        current_price: float,
        adapter: Any | None = None,
    ) -> dict[str, Any] | None:
        """
        Execute a signal as an order.
        Returns the created order dict, or None if execution was skipped.
        """
        if settings.LIVE_TRADING_ENABLED and not settings.PAPER_TRADING_MODE:
            return await self._live_order(signal, size_usd, current_price, adapter)
        return self._paper_order(signal, size_usd, current_price)

    # ------------------------------------------------------------------
    # Paper trading
    # ------------------------------------------------------------------

    def _paper_order(
        self,
        signal: Signal,
        size_usd: float,
        current_price: float,
    ) -> dict[str, Any] | None:
        symbol = signal.symbol          # e.g. "BTCUSDT"
        base_asset = symbol.replace("USDT", "")   # e.g. "BTC"

        if signal.action == SignalAction.BUY:
            if self._available_usd < size_usd:
                logger.warning("Paper order skipped: insufficient balance",
                               extra={"available": self._available_usd, "needed": size_usd})
                return None

            qty = size_usd / current_price
            self._available_usd -= size_usd
            self._holdings[base_asset] = self._holdings.get(base_asset, 0.0) + qty
            self._open_positions += 1
            status = "FILLED"

        elif signal.action == SignalAction.SELL:
            held = self._holdings.get(base_asset, 0.0)
            if held <= 0:
                logger.warning("Paper order skipped: no holdings to sell",
                               extra={"asset": base_asset})
                return None

            qty = min(held, size_usd / current_price)
            proceeds = qty * current_price
            self._holdings[base_asset] = held - qty
            if self._holdings[base_asset] <= 0:
                del self._holdings[base_asset]
                self._open_positions = max(0, self._open_positions - 1)
            self._available_usd += proceeds
            status = "FILLED"
        else:
            return None

        order = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": signal.action.value,
            "quantity": round(qty, 8),
            "price": current_price,
            "size_usd": round(qty * current_price, 2),
            "status": status,
            "mode": "PAPER",
            "strategy": signal.metadata.get("strategy", ""),
            "reason": signal.reason,
            "created_at": _now_iso(),
        }
        self._orders[order["id"]] = order
        logger.info("Paper order executed", extra={
            "id": order["id"], "side": order["side"],
            "symbol": symbol, "qty": order["quantity"],
            "price": current_price, "size_usd": order["size_usd"],
        })
        return order

    # ------------------------------------------------------------------
    # Live trading (Phase 5)
    # ------------------------------------------------------------------

    async def _live_order(
        self,
        signal: Signal,
        size_usd: float,
        current_price: float,
        adapter: Any,
    ) -> dict[str, Any] | None:
        if adapter is None:
            logger.error("Live order requested but no adapter provided")
            return None

        qty = round(size_usd / current_price, 6)
        try:
            result = await adapter.place_order(
                symbol=signal.symbol,
                side=signal.action.value,
                quantity=qty,
            )
            order = {
                "id": result.get("orderId", str(uuid.uuid4())),
                "symbol": signal.symbol,
                "side": signal.action.value,
                "quantity": qty,
                "price": current_price,
                "size_usd": size_usd,
                "status": result.get("status", "UNKNOWN"),
                "mode": "LIVE",
                "strategy": signal.metadata.get("strategy", ""),
                "reason": signal.reason,
                "created_at": _now_iso(),
                "raw": result,
            }
            self._orders[str(order["id"])] = order
            return order
        except Exception as exc:
            logger.error("Live order failed", extra={"error": str(exc)})
            return None
