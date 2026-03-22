# 📊 stock-trader

Automated Trading System

## 🧩 Tech Stack

### Backend (Python)

| 역할           | 기술                        |
| -------------- | --------------------------- |
| API 프레임워크 | FastAPI                     |
| 작업 큐        | Celery + Redis              |
| 거래소 SDK     | python-binance, pyupbit     |
| AI/감성분석    | FinBERT (로컬) + ~~GPT-4o~~ |
| 백테스팅       | vectorbt                    |

---

### Frontend (React)

| 역할      | 기술                           |
| --------- | ------------------------------ |
| 빌드 툴   | Vite + TypeScript              |
| 상태 관리 | Zustand + React Query          |
| 차트      | TradingView Lightweight Charts |
| UI        | shadcn/ui + Tailwind CSS       |

---

### Infra

| 역할          | 기술                                     |
| ------------- | ---------------------------------------- |
| DB            | PostgreSQL + TimescaleDB (시계열 최적화) |
| 캐시 / 실시간 | Redis                                    |
| 컨테이너      | Docker Compose                           |
| 모니터링      | Prometheus + Grafana                     |

---

## 🚀 Development Phases

| Phase   | 기간    | 내용                            |
| ------- | ------- | ------------------------------- |
| Phase 1 | 1–3주   | 기반 구축 + 실시간 차트 표시    |
| Phase 2 | 4–6주   | 트레이딩 엔진 + 페이퍼 트레이딩 |
| Phase 3 | 7–8주   | 백테스팅 시스템                 |
| Phase 4 | 9–11주  | AI 감성분석 연동                |
| Phase 5 | 12–14주 | 실제 거래 + Upbit 연동          |
| Phase 6 | 15–17주 | 프로덕션 배포 + 모니터링        |

---

## 🧠 Core Design Principles

- **거래소 추상화**
  - Binance / Upbit 인터페이스 분리
  - 향후 거래소 확장 가능

- **페이퍼 트레이딩 기본**
  - `LIVE_TRADING_ENABLED=true` 환경 변수로만 실제 거래 활성화

- **AI 비용 최적화**
  - 뉴스 전체 → FinBERT (로컬) 처리
  - 극단적 신호만 GPT 호출 → 비용 절감
