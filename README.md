# StockTrader — 자동화 암호화폐 트레이딩 봇

> **실시간 시세 → AI 감성 분석 → 자동 매매 → 성과 분석 → Telegram 알림**
> Docker Compose 한 줄로 전체 스택 실행

---

## 목차

- [개요](#개요)
- [아키텍처](#아키텍처)
- [기술 스택](#기술-스택)
- [프로젝트 구조](#프로젝트-구조)
- [빠른 시작](#빠른-시작)
- [환경 변수](#환경-변수)
- [주요 기능](#주요-기능)
- [거래 전략](#거래-전략)
- [API 엔드포인트](#api-엔드포인트)
- [개발 가이드](#개발-가이드)
- [Phase 로드맵](#phase-로드맵)

---

## 개요

StockTrader는 Python + React로 만든 자동화 암호화폐 트레이딩 시스템입니다.
Binance와 Upbit 거래소를 지원하며, 기본값은 **페이퍼 트레이딩(가상 자금)** 으로
실수로 실제 자산이 사용되는 일이 없도록 설계되었습니다.

```
실시간 WebSocket 시세
      ↓
 TradingEngine  ←── RSI / MACD / Sentiment 전략
      ↓
 RiskManager   (포지션 2% 한도 / 일일 손실 5% 차단)
      ↓
 OrderManager  ──→ Paper 주문 (기본) | Live 주문 (opt-in)
      ↓
 Telegram 알림 + Analytics DB 저장
```

---

## 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│                    Docker Network                         │
│                                                          │
│  ┌────────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │TimescaleDB │  │  Redis   │  │  FastAPI Backend   │   │
│  │(PostgreSQL │  │ Pub/Sub  │◄─│  + TradingEngine   │   │
│  │+ hypertable│  │ + Cache  │  │  + Alembic         │   │
│  └────────────┘  └──────────┘  └────────────────────┘   │
│        ▲              ▲                  ▲               │
│        │     ┌────────┴──────┐  ┌────────┴──────────┐   │
│        └─────│ Celery Worker │  │   Celery Beat     │   │
│              │ - Backtest    │  │ - Sentiment 15분  │   │
│              │ - Sentiment   │  │ - Snapshot 1시간  │   │
│              │ - Analytics   │  │ - 일일 요약 09시  │   │
│              └───────────────┘  └───────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │          React + Vite Frontend (Nginx)            │    │
│  │  Dashboard / Analytics / Backtest / Settings     │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ WebSocket                    │ REST / WS
    Binance / Upbit              Browser (localhost:3000)
```

### 데이터 흐름

```
Binance WebSocket
  → BinanceAdapter.stream_tickers()
  → Redis Pub/Sub  "prices:BTCUSDT"
  → TradingEngine._on_tick()
  → Strategy.on_candle()  →  Signal
  → RiskManager.check()
  → OrderManager.execute()  →  Paper / Live Order
  → Telegram notify_order()

브라우저 WebSocket
  → /ws/prices/BTCUSDT
  → Redis Subscribe
  → TradingView Lightweight Charts
```

---

## 기술 스택

### Backend

| 항목 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI + uvicorn (async) |
| DB | PostgreSQL 16 + TimescaleDB (시계열 hypertable) |
| ORM | SQLAlchemy 2.0 (async) + Alembic 마이그레이션 |
| 캐시/메시징 | Redis 7 (Pub/Sub + Cache) |
| 태스크 큐 | Celery 5 + Celery Beat |
| 거래소 | python-binance (Binance) / httpx + websockets (Upbit) |
| AI 감성 분석 | 🤗 transformers — ProsusAI/finbert |
| 알림 | Telegram Bot API |
| 설정 관리 | pydantic-settings |

### Frontend

| 항목 | 기술 |
|------|------|
| 빌드 | Vite + React 18 + TypeScript |
| 차트 | TradingView Lightweight Charts v4 |
| 서버 상태 | TanStack Query (React Query) |
| 스타일 | Tailwind CSS |
| 라우팅 | React Router v6 |

### Infrastructure

| 항목 | 기술 |
|------|------|
| 컨테이너 | Docker + Docker Compose |
| 리버스 프록시 | Nginx (SPA routing + API/WS proxy) |
| 이미지 빌드 | 멀티스테이지 (node builder → nginx) |

---

## 프로젝트 구조

```
stock-trader/
├── .env.example                  # 환경 변수 템플릿
├── infra/
│   └── docker-compose.yml        # 6개 서비스 정의
│
├── backend/
│   ├── adapters/
│   │   ├── base.py               # BaseExchangeAdapter (ABC)
│   │   ├── binance.py            # Binance WebSocket + REST
│   │   └── upbit.py              # Upbit KRW 마켓 + JWT 인증
│   │
│   ├── api/
│   │   ├── main.py               # FastAPI 앱 팩토리 + lifespan
│   │   └── routers/
│   │       ├── analytics.py      # GET /api/analytics/*
│   │       ├── backtest.py       # POST /api/backtest
│   │       ├── exchange_settings.py  # GET/POST /api/settings
│   │       ├── ohlcv.py          # GET /api/ohlcv/{symbol}
│   │       ├── orders.py         # GET /api/orders
│   │       ├── portfolio.py      # GET /api/portfolio
│   │       ├── sentiment.py      # GET /api/sentiment/{symbol}
│   │       ├── strategies.py     # GET/POST /api/strategies
│   │       └── websocket.py      # WS /ws/prices/{symbol}
│   │
│   ├── engine/
│   │   ├── trading_engine.py     # 메인 이벤트 루프 (싱글턴)
│   │   ├── order_manager.py      # Paper / Live 주문 실행
│   │   ├── risk_manager.py       # 포지션 한도 + 손실 차단기
│   │   └── strategies/
│   │       ├── base.py           # BaseStrategy (ABC)
│   │       ├── rsi_strategy.py   # RSI 과매수/과매도
│   │       ├── macd_strategy.py  # MACD 히스토그램 크로스
│   │       └── sentiment_strategy.py  # RSI + FinBERT 게이트
│   │
│   ├── services/
│   │   ├── analytics/
│   │   │   └── performance.py    # 전략별 Sharpe·승률·MDD
│   │   ├── backtesting/
│   │   │   └── runner.py         # 과거 데이터 전략 시뮬레이션
│   │   ├── notifications/
│   │   │   └── telegram.py       # 주문·경보·일일 요약 알림
│   │   └── sentiment/
│   │       ├── news_fetcher.py   # RSS 뉴스 수집
│   │       ├── finbert_scorer.py # FinBERT 감성 점수 [-1, +1]
│   │       └── aggregator.py     # 가중 합산 + Redis 캐싱
│   │
│   ├── tasks/
│   │   ├── celery_app.py         # Celery + Beat 스케줄 정의
│   │   ├── backtest_tasks.py     # 백테스트 비동기 실행
│   │   ├── sentiment_tasks.py    # 감성 분석 주기 갱신
│   │   └── analytics_tasks.py   # 스냅샷 저장 + 일일 요약
│   │
│   ├── db/
│   │   ├── session.py            # SQLAlchemy async engine
│   │   ├── redis.py              # Redis 연결 풀
│   │   └── models/               # ORM 모델
│   │
│   ├── alembic/versions/
│   │   ├── 001_initial.py        # users + ohlcv hypertable
│   │   ├── 002_backtest_results.py
│   │   ├── 003_live_orders.py    # 주문 감사 로그
│   │   └── 004_portfolio_snapshots.py  # P&L 이력
│   │
│   ├── Dockerfile
│   └── pyproject.toml
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Dashboard.tsx     # 실시간 차트 + 전체 패널
    │   │   ├── Analytics.tsx     # 성과 분석 + P&L 차트
    │   │   ├── Backtest.tsx      # 백테스트 폼 + 결과
    │   │   └── Settings.tsx      # 거래소 선택 + 실거래 토글
    │   ├── components/
    │   │   ├── charts/CandlestickChart.tsx
    │   │   ├── portfolio/PortfolioCard.tsx
    │   │   ├── orders/OrdersTable.tsx
    │   │   ├── strategies/StrategyPanel.tsx
    │   │   └── sentiment/SentimentPanel.tsx
    │   ├── hooks/
    │   │   └── usePriceFeed.ts   # WebSocket + REST 통합 훅
    │   └── api/                  # 도메인별 fetch 헬퍼
    ├── Dockerfile                # 멀티스테이지 빌드
    └── nginx.conf                # SPA + API/WS 프록시
```

---

## 빠른 시작

### 사전 요구사항

- Docker Desktop 4.x 이상
- Docker Compose v2

### 1. 저장소 클론 및 환경 변수 설정

```bash
git clone https://github.com/yourname/stock-trader.git
cd stock-trader

cp .env.example .env
# .env 파일을 열어 필요한 값 입력
```

### 2. 전체 시스템 실행

```bash
cd infra
docker compose up -d
```

> 최초 실행 시 Docker 이미지 빌드 + FinBERT 모델 다운로드로 약 5~10분 소요됩니다.

### 3. 접속

| 서비스 | URL |
|--------|-----|
| **대시보드** | http://localhost:3000 |
| **API 문서 (Swagger)** | http://localhost:8000/docs |
| **헬스체크** | http://localhost:8000/health |

### 4. 시스템 중지

```bash
docker compose down        # 컨테이너 중지 (데이터 유지)
docker compose down -v     # 컨테이너 + 볼륨 전체 삭제
```

---

## 환경 변수

`.env.example`을 복사해 `.env`로 만든 후 수정합니다.

### 필수

```env
# PostgreSQL
POSTGRES_USER=trader
POSTGRES_PASSWORD=traderpassword
POSTGRES_DB=stocktrader

# Redis
REDIS_URL=redis://redis:6379/0
```

### 거래소 API 키 (선택 — 시세 조회는 키 없이도 가능)

```env
# 활성 거래소: "binance" 또는 "upbit"
ACTIVE_EXCHANGE=binance

# Binance — https://www.binance.com/en/my/settings/api-management
BINANCE_API_KEY=
BINANCE_SECRET_KEY=

# Upbit (KRW 마켓) — https://upbit.com/mypage/open_api_management
UPBIT_ACCESS_KEY=
UPBIT_SECRET_KEY=
```

### 실거래 안전장치

```env
# ⚠️ 기본값 false — 반드시 의도적으로 true로 변경해야 실거래 가능
LIVE_TRADING_ENABLED=false
PAPER_TRADING_MODE=true
PAPER_INITIAL_BALANCE=10000.0
```

### AI / 뉴스 (선택)

```env
# NewsAPI — https://newsapi.org/register (무료: 100 req/day)
# 없어도 CoinDesk / CoinTelegraph / Decrypt RSS로 동작함
NEWSAPI_KEY=
```

### Telegram 알림 (선택)

```env
# 1. @BotFather → /newbot → TOKEN 복사
# 2. 봇에 메시지 전송 후 아래 URL로 chat_id 확인:
#    https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 주요 기능

### 실시간 시세 스트리밍
- Binance / Upbit WebSocket으로 1분봉 캔들 실시간 수신
- Redis Pub/Sub를 통해 브라우저 WebSocket으로 전달
- TradingView Lightweight Charts로 캔들스틱 + 거래량 렌더링

### 자동 매매 엔진
- FastAPI 시작 시 `TradingEngine` 백그라운드 루프 시작
- 매 틱마다 전략 평가 → 신호 생성 → 리스크 검사 → 주문 실행

### 리스크 관리 (3중 보호)

| 규칙 | 기본값 | 환경 변수 |
|------|--------|-----------|
| 트레이드당 최대 포지션 | 포트폴리오의 2% | `RISK_MAX_POSITION_PCT` |
| 일일 손실 차단기 | 5% 초과 시 자동 중단 | `RISK_DAILY_LOSS_LIMIT_PCT` |
| 최대 동시 포지션 | 3개 | `RISK_MAX_OPEN_POSITIONS` |

### AI 감성 분석
- **FinBERT** (ProsusAI/finbert) — 금융 뉴스 특화 BERT 모델
- CoinDesk / CoinTelegraph / Decrypt RSS 실시간 수집
- 최신 기사 가중치 적용 복합 점수 [-1, +1]
- Redis 캐싱 30분, Celery Beat 15분 주기 갱신

### 백테스트
- 과거 OHLCV 데이터로 전략 시뮬레이션
- 결과: 총 수익률, Sharpe Ratio, Max Drawdown, 승률, 자산 곡선 차트
- Celery 비동기 처리 → 폴링으로 진행 상황 확인

### Telegram 알림

| 알림 종류 | 트리거 |
|-----------|--------|
| 📈 매수 체결 | 주문 실행 즉시 |
| 📉 매도 체결 | 주문 실행 즉시 |
| ⛔ 리스크 차단 | 일일 손실 한도 초과 |
| 📊 일일 요약 | 매일 09:00 KST |

---

## 거래 전략

### RSI (Relative Strength Index)

```
매수 조건: RSI < 30 (과매도 구간 진입)
매도 조건: RSI > 70 (과매수 구간 진입)
워밍업:   최소 16개 캔들
```

### MACD (Moving Average Convergence Divergence)

```
매수 조건: 히스토그램 음수 → 양수 전환 (골든 크로스)
매도 조건: 히스토그램 양수 → 음수 전환 (데드 크로스)
워밍업:   최소 37개 캔들 (EMA26 + Signal9)
```

### Sentiment (RSI + AI 게이트)

```
매수 조건: RSI < 30 AND 감성 점수 > 0 (긍정적 뉴스)
매도 조건: RSI > 70 AND 감성 점수 < 0 (부정적 뉴스)
특징:     뉴스 감성이 신호와 반대이면 매매 차단
```

### 새 전략 추가 방법

```python
# backend/engine/strategies/my_strategy.py
from engine.strategies.base import BaseStrategy, Candle, Signal, SignalAction

class MyStrategy(BaseStrategy):
    name = "MY"
    min_candles = 20

    def generate_signal(self, candles: list[Candle]) -> Signal:
        # 로직 구현
        return Signal(action=SignalAction.HOLD, ...)
```

```python
# backend/engine/trading_engine.py 에 등록
STRATEGY_REGISTRY["MY"] = MyStrategy
```

---

## API 엔드포인트

### 시장 데이터
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/ohlcv/{symbol}` | OHLCV 캔들 데이터 |
| `WS` | `/ws/prices/{symbol}` | 실시간 가격 스트림 |
| `GET` | `/health` | DB + Redis 헬스체크 |

### 거래 엔진
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/strategies` | 활성 전략 목록 |
| `POST` | `/api/strategies` | 전략 추가 |
| `DELETE` | `/api/strategies/{name}` | 전략 제거 |
| `GET` | `/api/orders` | 주문 내역 |
| `GET` | `/api/portfolio` | 포트폴리오 현황 |

### 분석
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/analytics/summary` | 전체 성과 요약 |
| `GET` | `/api/analytics/performance` | 전략별 성과 지표 |
| `GET` | `/api/analytics/pnl-history` | P&L 이력 (시계열) |

### 감성 분석
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/sentiment/{symbol}` | 감성 점수 + 뉴스 |
| `POST` | `/api/sentiment/{symbol}/refresh` | 즉시 갱신 |

### 백테스트
| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/backtest` | 백테스트 실행 요청 |
| `GET` | `/api/backtest/{task_id}` | 결과 폴링 |
| `GET` | `/api/backtest` | 이력 목록 |

### 설정
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/settings` | 현재 거래소/모드 설정 |
| `POST` | `/api/settings/exchange` | 거래소 전환 (binance/upbit) |
| `POST` | `/api/settings/live-trading` | 실거래 모드 토글 |

전체 API 문서: http://localhost:8000/docs

---

## 개발 가이드

### 로컬 개발 (Docker 없이)

```bash
# PostgreSQL + Redis만 Docker로 실행
cd infra && docker compose up postgres redis -d

# Backend
cd backend
uv pip install -e ".[dev]"
alembic upgrade head
uvicorn api.main:app --reload        # http://localhost:8000

# Frontend (별도 터미널)
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

### 로그 확인

```bash
docker compose logs -f               # 전체 실시간 로그
docker compose logs -f backend       # 백엔드만
docker compose logs -f celery_worker # Celery 워커만
```

### DB 마이그레이션 관리

```bash
# 새 마이그레이션 생성
docker compose exec backend alembic revision -m "add_new_table"

# 최신 버전으로 적용
docker compose exec backend alembic upgrade head

# 한 단계 롤백
docker compose exec backend alembic downgrade -1
```

### Celery 태스크 수동 실행

```bash
# 감성 분석 즉시 갱신
docker compose exec celery_worker \
  celery -A tasks.celery_app call tasks.refresh_all_sentiment

# 포트폴리오 스냅샷 즉시 저장
docker compose exec celery_worker \
  celery -A tasks.celery_app call tasks.save_portfolio_snapshot
```

---

## Phase 로드맵

| Phase | 내용 | 상태 |
|-------|------|------|
| **1** | 실시간 BTC/USDT 캔들스틱 차트 + WebSocket 스트리밍 | ✅ 완료 |
| **2** | 트레이딩 엔진 + RSI/MACD 전략 + 페이퍼 트레이딩 | ✅ 완료 |
| **3** | 백테스트 엔진 + Celery 비동기 + 자산 곡선 차트 | ✅ 완료 |
| **4** | AI 감성 분석 (FinBERT) + 뉴스 파이프라인 | ✅ 완료 |
| **5** | 실거래 + Upbit 통합 + 멀티 거래소 전환 | ✅ 완료 |
| **6** | 성과 분석 대시보드 + Telegram 실시간 알림 | ✅ 완료 |

---

## 라이선스

MIT License — 자유롭게 사용, 수정, 배포 가능합니다.

> ⚠️ **면책 조항**: 이 소프트웨어는 교육 및 연구 목적으로 제작되었습니다.
> 실제 자산으로 거래 시 발생하는 손실에 대해 제작자는 책임을 지지 않습니다.
> 투자는 본인의 판단과 책임 하에 진행하세요.
