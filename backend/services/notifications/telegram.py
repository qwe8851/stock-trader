"""
Telegram notification service.

모든 메시지는 MarkdownV2 형식으로 전송됩니다.

알림 종류:
  - 주문 체결 알림 (매수/매도)
  - 리스크 경보 (일일 손실 한도 초과)
  - 일일 성과 요약

설정:
  TELEGRAM_BOT_TOKEN — @BotFather 에서 발급
  TELEGRAM_CHAT_ID   — 메시지를 받을 채팅/그룹 ID

설정이 없으면 모든 메서드는 no-op로 동작합니다.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _escape(text: str) -> str:
    """Escape special MarkdownV2 characters."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(r"([" + re.escape(special) + r"])", r"\\\1", str(text))


async def _send(text: str) -> None:
    """Low-level send via Telegram Bot API."""
    if not settings.telegram_enabled:
        return
    url = _TELEGRAM_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Telegram send failed",
                               extra={"status": resp.status_code, "body": resp.text[:200]})
    except Exception as exc:
        logger.warning("Telegram send error", extra={"error": str(exc)})


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

async def notify_order(order: dict[str, Any]) -> None:
    """
    주문 체결 알림.

    📈 매수 체결
    Symbol  : BTCUSDT
    수량    : 0.001234 BTC
    가격    : $98,500.00
    금액    : $121.50
    전략    : RSI
    모드    : PAPER
    """
    side = order.get("side", "").upper()
    icon = "📈" if side == "BUY" else "📉"
    mode = order.get("mode", "PAPER")
    mode_badge = "🟡 PAPER" if mode == "PAPER" else "🔴 LIVE"

    symbol = _escape(order.get("symbol", ""))
    qty    = _escape(f"{order.get('quantity', 0):.6f}")
    price  = _escape(f"${order.get('price', 0):,.2f}")
    size   = _escape(f"${order.get('size_usd', 0):,.2f}")
    strat  = _escape(order.get("strategy", "-"))
    reason = _escape(order.get("reason", "-"))

    side_ko = "매수" if side == "BUY" else "매도"
    text = (
        f"{icon} *{_escape(side_ko)} 체결*\n"
        f"Symbol  : `{symbol}`\n"
        f"수량    : `{qty}`\n"
        f"가격    : `{price}`\n"
        f"금액    : `{size}`\n"
        f"전략    : `{strat}`\n"
        f"이유    : {reason}\n"
        f"모드    : {mode_badge}"
    )
    await _send(text)


async def notify_risk_halt(reason: str, portfolio_value: float) -> None:
    """
    리스크 매니저 거래 중단 알림.

    ⛔ 리스크 한도 초과 — 거래 중단
    사유: 일일 손실 한도 초과
    포트폴리오: $9,420.00
    """
    pv = _escape(f"${portfolio_value:,.2f}")
    r  = _escape(reason)
    text = (
        f"⛔ *리스크 한도 초과 \\— 거래 중단*\n"
        f"사유        : {r}\n"
        f"포트폴리오  : `{pv}`"
    )
    await _send(text)


async def notify_daily_summary(summary: dict[str, Any]) -> None:
    """
    일일 성과 요약 알림.

    📊 일일 성과 요약
    포트폴리오  : $10,250.00
    일일 손익   : +$250.00 (+2.50%)
    총 거래     : 12회
    승률        : 66.7%
    거래소      : Binance
    """
    pv     = _escape(f"${summary.get('portfolio_value', 0):,.2f}")
    pnl    = summary.get("daily_pnl", 0)
    pnl_pct= summary.get("daily_pnl_pct", 0)
    sign   = "\\+" if pnl >= 0 else ""
    pnl_str= _escape(f"{sign}${pnl:,.2f} ({sign}{pnl_pct:.2f}%)")
    trades = _escape(str(summary.get("total_trades", 0)))
    win_rt = _escape(f"{summary.get('win_rate', 0) * 100:.1f}%")
    exchange = _escape(summary.get("exchange", "-"))

    pnl_icon = "🟢" if pnl >= 0 else "🔴"

    text = (
        f"📊 *일일 성과 요약*\n"
        f"포트폴리오  : `{pv}`\n"
        f"일일 손익   : {pnl_icon} `{pnl_str}`\n"
        f"총 거래     : `{trades}회`\n"
        f"승률        : `{win_rt}`\n"
        f"거래소      : `{exchange}`"
    )
    await _send(text)
