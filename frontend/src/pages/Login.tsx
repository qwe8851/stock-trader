import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, fetchMe } from "../api/auth";
import { useAuthStore } from "../store/authStore";

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { access_token } = await login(email, password);
      // Temporarily store token so fetchMe can use it
      useAuthStore.setState({ token: access_token });
      const user = await fetchMe();
      setAuth(access_token, user);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
      useAuthStore.setState({ token: null });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-9 h-9 rounded-lg bg-brand flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white">
              <path d="M3 17l4-8 4 5 3-3 4 6" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="font-semibold text-xl tracking-tight text-white">
            Stock<span className="text-brand">Trader</span>
          </span>
        </div>

        <div className="card p-6">
          <h1 className="text-lg font-semibold text-white mb-6">로그인</h1>

          {error && (
            <div className="mb-4 px-3 py-2 rounded bg-bear/10 border border-bear/30 text-bear text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1">이메일</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                           text-sm text-white placeholder-gray-600 focus:outline-none
                           focus:border-brand transition-colors"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1">비밀번호</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-surface-100 border border-gray-700 rounded-lg px-3 py-2
                           text-sm text-white placeholder-gray-600 focus:outline-none
                           focus:border-brand transition-colors"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-brand hover:bg-brand/90 disabled:opacity-50
                         text-white text-sm font-medium py-2 rounded-lg transition-colors"
            >
              {loading ? "로그인 중…" : "로그인"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs text-gray-500">
            계정이 없으신가요?{" "}
            <Link to="/register" className="text-brand hover:underline">
              회원가입
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
