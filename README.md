# stock-trader

자동 암호화폐 거래 봇 — Binance 실시간 데이터 수집, AI 감성분석, 자동 매매, 백테스팅을 포함한 풀스택 트레이딩 시스템.

---

## 시작하기

```bash
cp .env.example .env
cd infra && docker compose up --build -d
```

| 서비스 | URL |
|--------|-----|
| 대시보드 (React) | http://localhost:3000 |
| API (FastAPI) | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |

---

## 기술 스택

### Backend (Python)

| 역할 | 기술 |
|------|------|
| API 프레임워크 | FastAPI |
| 작업 큐 | Celery + Redis |
| 거래소 SDK | python-binance, pyupbit |
| AI / 감성분석 | FinBERT (로컬) + GPT-4o (선택) |
| 백테스팅 | vectorbt |

### Frontend (React)

| 역할 | 기술 |
|------|------|
| 빌드 툴 | Vite + TypeScript |
| 상태 관리 | Zustand + React Query |
| 차트 | TradingView Lightweight Charts |
| UI | shadcn/ui + Tailwind CSS |

### 인프라

| 역할 | 기술 |
|------|------|
| DB | PostgreSQL + TimescaleDB |
| 캐시 / 실시간 | Redis |
| 컨테이너 | Docker Compose |
| 모니터링 | Prometheus + Grafana |

---

## 개발 로드맵

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 | 기반 구축 + 실시간 캔들차트 | ✅ 완료 |
| Phase 2 | 트레이딩 엔진 + 페이퍼 트레이딩 | 진행 예정 |
| Phase 3 | 백테스팅 시스템 | 진행 예정 |
| Phase 4 | AI 감성분석 연동 | 진행 예정 |
| Phase 5 | 실제 거래 + Upbit 연동 | 진행 예정 |
| Phase 6 | 프로덕션 배포 + 모니터링 | 진행 예정 |

---

## 프로젝트 구조

```
stock-trader/
├── backend/
│   ├── adapters/        # 거래소 어댑터 (Binance, Upbit)
│   ├── api/             # FastAPI 라우터
│   ├── core/            # 설정, 로깅
│   ├── db/              # DB 모델, 세션, Redis
│   ├── engine/          # 트레이딩 엔진, 전략
│   ├── services/        # 감성분석, 백테스팅, 포트폴리오
│   ├── tasks/           # Celery 태스크
│   └── alembic/         # DB 마이그레이션
├── frontend/
│   └── src/
│       ├── components/  # 차트, UI 컴포넌트
│       ├── hooks/       # usePriceFeed 등
│       ├── pages/       # Dashboard, Portfolio 등
│       └── store/       # Zustand 상태
└── infra/
    └── docker-compose.yml
```

---

## 핵심 설계 원칙

**거래소 추상화**
- `BaseExchangeAdapter` 인터페이스로 Binance / Upbit 분리
- 거래소 추가 시 엔진 코드 변경 없음

**페이퍼 트레이딩 기본**
- 기본값은 시뮬레이션 모드
- `.env`에서 `LIVE_TRADING_ENABLED=true` 설정 시에만 실제 거래 활성화

**실시간 데이터 흐름**
```
Binance WebSocket → Redis pub/sub → FastAPI WS → 브라우저 차트
```
