/**
 * Settings page — exchange selector + live trading toggle.
 *
 * Layout:
 *  ┌─────────────────────────────────────────┐
 *  │  Header + back link                     │
 *  ├─────────────────────────────────────────┤
 *  │  Exchange Card  (Binance / Upbit)        │
 *  ├─────────────────────────────────────────┤
 *  │  Trading Mode Card  (Paper / Live)       │
 *  ├─────────────────────────────────────────┤
 *  │  Credential Status Card                 │
 *  └─────────────────────────────────────────┘
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  fetchSettings,
  fetchFeeInfo,
  switchExchange,
  toggleLiveTrading,
  testCredentials,
  fetchLiveBalance,
} from "../api/settings";

export default function Settings() {
  const qc = useQueryClient();
  const [confirmLive, setConfirmLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testingCreds, setTestingCreds] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [liveBalance, setLiveBalance] = useState<Record<string, { free: string; locked: string }> | null>(null);
  const [loadingBalance, setLoadingBalance] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
    refetchInterval: 10_000,
  });

  const { data: feeData } = useQuery({
    queryKey: ["fee-info"],
    queryFn: fetchFeeInfo,
  });

  async function handleTestCredentials() {
    setTestingCreds(true);
    setTestResult(null);
    try {
      const result = await testCredentials();
      setTestResult(`✓ 유효한 자격증명 — ${result.assets_with_balance}개 자산 잔고 확인`);
    } catch (err: unknown) {
      setTestResult(`✗ ${err instanceof Error ? err.message : "검증 실패"}`);
    } finally {
      setTestingCreds(false);
    }
  }

  async function handleFetchLiveBalance() {
    setLoadingBalance(true);
    setLiveBalance(null);
    try {
      const result = await fetchLiveBalance();
      setLiveBalance(result.balance);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "잔고 조회 실패");
    } finally {
      setLoadingBalance(false);
    }
  }

  const exchangeMutation = useMutation({
    mutationFn: (exchange: "binance" | "upbit") => switchExchange(exchange),
    onSuccess: (_, exchange) => {
      setError(null);
      setSuccess(`거래소를 ${exchange === "upbit" ? "Upbit (KRW)" : "Binance (USDT)"}으로 전환했습니다.`);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => {
      setError(e.message);
      setSuccess(null);
    },
  });

  const liveMutation = useMutation({
    mutationFn: ({ enabled, confirm }: { enabled: boolean; confirm: boolean }) =>
      toggleLiveTrading(enabled, confirm),
    onSuccess: (_, { enabled }) => {
      setError(null);
      setConfirmLive(false);
      setSuccess(enabled ? "실거래 모드가 활성화되었습니다. ⚠️ 실제 자산이 사용됩니다." : "페이퍼 트레이딩 모드로 전환되었습니다.");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => {
      setError(e.message);
      setSuccess(null);
    },
  });

  if (isLoading || !data) {
    return (
      <div className="min-h-screen bg-surface text-white flex items-center justify-center">
        <span className="text-gray-500 text-sm">Loading settings…</span>
      </div>
    );
  }

  const isLive = !data.paper_mode;

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <Link
          to="/dashboard"
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          ← 대시보드
        </Link>
        <span className="font-semibold text-lg">설정</span>
      </header>

      <div className="px-6 py-6 max-w-2xl mx-auto w-full space-y-6">
        {/* Feedback messages */}
        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-900/40 border border-green-700 text-green-300 text-sm rounded-lg px-4 py-3">
            {success}
          </div>
        )}

        {/* ── Exchange Card ─────────────────────────────────────────────── */}
        <section className="card p-5 space-y-4">
          <h2 className="font-semibold text-base">거래소 선택</h2>
          <p className="text-xs text-gray-500">
            거래소를 전환하면 가격 스트림과 주문 엔진이 즉시 재연결됩니다.
            재시작 후에도 유지하려면 <code className="text-gray-300">.env</code>의{" "}
            <code className="text-gray-300">ACTIVE_EXCHANGE</code>를 수정하세요.
          </p>

          <div className="grid grid-cols-2 gap-3">
            {(["binance", "upbit"] as const).map((ex) => {
              const active = data.exchange === ex;
              const hasCreds =
                ex === "binance"
                  ? data.credentials.binance.has_credentials
                  : data.credentials.upbit.has_credentials;

              return (
                <button
                  key={ex}
                  onClick={() => exchangeMutation.mutate(ex)}
                  disabled={active || exchangeMutation.isPending}
                  className={clsx(
                    "rounded-lg border p-4 text-left transition-colors",
                    active
                      ? "border-brand bg-brand/10 cursor-default"
                      : "border-gray-700 hover:border-gray-500 hover:bg-surface-50 cursor-pointer"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-sm capitalize">{ex}</span>
                    {active && (
                      <span className="text-xs bg-brand text-white px-2 py-0.5 rounded-full">
                        활성
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 space-y-1">
                    <div>{ex === "binance" ? "USDT 마켓" : "KRW 원화 마켓"}</div>
                    <div>
                      API 키:{" "}
                      <span className={hasCreds ? "text-bull" : "text-gray-600"}>
                        {hasCreds ? "설정됨" : "없음"}
                      </span>
                    </div>
                    {ex === "binance" && data.credentials.binance.testnet && (
                      <div className="text-yellow-500">테스트넷 모드</div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* ── Trading Mode Card ─────────────────────────────────────────── */}
        <section className="card p-5 space-y-4">
          <h2 className="font-semibold text-base">거래 모드</h2>

          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">
                현재 모드:{" "}
                <span className={isLive ? "text-bear" : "text-bull"}>
                  {isLive ? "실거래 (LIVE)" : "페이퍼 트레이딩"}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {isLive
                  ? "⚠️ 실제 자산으로 거래 중입니다."
                  : "가상 자금으로 시뮬레이션합니다. 실제 주문은 발생하지 않습니다."}
              </div>
            </div>

            {isLive ? (
              <button
                onClick={() =>
                  liveMutation.mutate({ enabled: false, confirm: true })
                }
                disabled={liveMutation.isPending}
                className="px-4 py-2 rounded-lg bg-surface-100 border border-gray-700 text-sm text-gray-300 hover:text-white hover:border-gray-500 transition-colors"
              >
                페이퍼 모드로 전환
              </button>
            ) : (
              <button
                onClick={() => setConfirmLive(true)}
                disabled={liveMutation.isPending || !data.live_trading_enabled}
                title={
                  !data.live_trading_enabled
                    ? "LIVE_TRADING_ENABLED=true를 .env에 설정해야 합니다"
                    : undefined
                }
                className={clsx(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                  data.live_trading_enabled
                    ? "bg-bear/20 border border-bear/50 text-bear hover:bg-bear/30"
                    : "bg-surface-100 border border-gray-700 text-gray-600 cursor-not-allowed"
                )}
              >
                실거래 활성화
              </button>
            )}
          </div>

          {!data.live_trading_enabled && (
            <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-lg p-3 text-xs text-yellow-500">
              실거래를 활성화하려면 환경 변수{" "}
              <code className="text-yellow-300">LIVE_TRADING_ENABLED=true</code>를
              설정해야 합니다. 이 값은 실수로 실거래가 발생하는 것을 막는 안전장치입니다.
            </div>
          )}

          {data.risk_halted && (
            <div className="bg-red-900/30 border border-red-800/50 rounded-lg p-3 text-xs text-red-400">
              ⛔ RiskManager가 일일 손실 한도 초과로 거래를 일시 중지했습니다.
            </div>
          )}
        </section>

        {/* ── Credential Status ─────────────────────────────────────────── */}
        <section className="card p-5 space-y-3">
          <h2 className="font-semibold text-base">API 키 상태</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 border-b border-gray-800">
                <th className="text-left pb-2">거래소</th>
                <th className="text-left pb-2">마켓</th>
                <th className="text-left pb-2">API 키</th>
                <th className="text-left pb-2">주문 가능</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              <tr>
                <td className="py-2">Binance</td>
                <td className="py-2 text-gray-400">USDT</td>
                <td className="py-2">
                  <StatusDot ok={data.credentials.binance.has_credentials} />
                </td>
                <td className="py-2">
                  <StatusDot ok={data.credentials.binance.has_credentials} />
                </td>
              </tr>
              <tr>
                <td className="py-2">Upbit</td>
                <td className="py-2 text-gray-400">KRW</td>
                <td className="py-2">
                  <StatusDot ok={data.credentials.upbit.has_credentials} />
                </td>
                <td className="py-2">
                  <StatusDot ok={data.credentials.upbit.has_credentials} />
                </td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs text-gray-600">
            API 키는 <code>.env</code> 파일에서 설정합니다. 시장 데이터 조회는 키 없이도 가능합니다.
          </p>

          {/* Credential test */}
          <div className="pt-1 flex items-center gap-3">
            <button
              onClick={handleTestCredentials}
              disabled={testingCreds}
              className="px-3 py-1.5 text-xs border border-gray-700 rounded text-gray-400 hover:text-white hover:border-gray-500 transition-colors disabled:opacity-40"
            >
              {testingCreds ? "검증 중…" : "자격증명 테스트"}
            </button>
            {testResult && (
              <span
                className={clsx(
                  "text-xs",
                  testResult.startsWith("✓") ? "text-bull" : "text-bear"
                )}
              >
                {testResult}
              </span>
            )}
          </div>
        </section>

        {/* ── Fee Information ────────────────────────────────────────────── */}
        {feeData && (
          <section className="card p-5 space-y-3">
            <h2 className="font-semibold text-base">수수료 & 최소 주문</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-800">
                  <th className="text-left pb-2">모드</th>
                  <th className="text-right pb-2">Maker</th>
                  <th className="text-right pb-2">Taker</th>
                  <th className="text-right pb-2">최소 주문</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-sm">
                <tr>
                  <td className="py-2">Binance (Live)</td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {(feeData.binance.maker_pct * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {(feeData.binance.taker_pct * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right font-mono text-gray-400">
                    ${feeData.binance.min_order_usd}
                  </td>
                </tr>
                <tr>
                  <td className="py-2">Upbit (Live)</td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {(feeData.upbit.maker_pct * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {(feeData.upbit.taker_pct * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right font-mono text-gray-400">
                    ₩{feeData.upbit.min_order_krw.toLocaleString()}
                  </td>
                </tr>
                <tr>
                  <td className="py-2">페이퍼 트레이딩</td>
                  <td className="py-2 text-right font-mono text-gray-300" colSpan={2}>
                    {(feeData.paper.fee_pct * 100).toFixed(2)}% (시뮬레이션)
                  </td>
                  <td className="py-2 text-right font-mono text-gray-400">
                    ${feeData.paper.min_order_usd}
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="text-xs text-gray-600">
              페이퍼 트레이딩에서도 수수료가 자동 차감됩니다. 실제 거래 결과와 유사한 성과 측정이 가능합니다.
            </p>
          </section>
        )}

        {/* ── Live Balance ───────────────────────────────────────────────── */}
        <section className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-base">실거래 잔고</h2>
            <button
              onClick={handleFetchLiveBalance}
              disabled={loadingBalance}
              className="px-3 py-1.5 text-xs border border-gray-700 rounded text-gray-400 hover:text-white hover:border-gray-500 transition-colors disabled:opacity-40"
            >
              {loadingBalance ? "조회 중…" : "잔고 조회"}
            </button>
          </div>
          <p className="text-xs text-gray-600">
            거래소 API 키가 설정된 경우 실제 잔고를 조회할 수 있습니다. 주문은 발생하지 않습니다.
          </p>
          {liveBalance && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-800">
                  <th className="text-left pb-2">자산</th>
                  <th className="text-right pb-2">가용</th>
                  <th className="text-right pb-2">잠금</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {Object.entries(liveBalance).map(([asset, bal]) => (
                  <tr key={asset}>
                    <td className="py-2 font-mono text-gray-200">{asset}</td>
                    <td className="py-2 text-right font-mono text-gray-300">{bal.free}</td>
                    <td className="py-2 text-right font-mono text-gray-500">{bal.locked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {/* ── Live Trading Confirmation Modal ─────────────────────────────── */}
      {confirmLive && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="card max-w-sm w-full p-6 space-y-4">
            <h3 className="font-semibold text-lg text-bear">⚠️ 실거래 활성화 확인</h3>
            <p className="text-sm text-gray-300">
              실거래 모드를 활성화하면 <strong>실제 자산</strong>으로 주문이 실행됩니다.
              페이퍼 트레이딩과 달리 손실이 발생할 수 있습니다.
            </p>
            <ul className="text-xs text-gray-500 list-disc list-inside space-y-1">
              <li>최대 포지션: 포트폴리오의 2%</li>
              <li>일일 손실 한도: 5% 초과 시 자동 중단</li>
              <li>최대 동시 포지션: 3개</li>
            </ul>
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setConfirmLive(false)}
                className="flex-1 px-4 py-2 rounded-lg border border-gray-700 text-sm text-gray-300 hover:text-white transition-colors"
              >
                취소
              </button>
              <button
                onClick={() =>
                  liveMutation.mutate({ enabled: true, confirm: true })
                }
                disabled={liveMutation.isPending}
                className="flex-1 px-4 py-2 rounded-lg bg-bear text-white text-sm font-medium hover:bg-bear/80 transition-colors"
              >
                {liveMutation.isPending ? "처리 중…" : "확인, 실거래 시작"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={clsx("text-xs font-medium", ok ? "text-bull" : "text-gray-600")}>
      {ok ? "● 있음" : "○ 없음"}
    </span>
  );
}
