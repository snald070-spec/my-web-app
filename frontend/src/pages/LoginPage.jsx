import { useState } from "react";
import { useGoogleLogin } from "@react-oauth/google";
import { useAuth } from "../context/AuthContext";
import api from "../api";

/** Password strength indicator */
function PwStrength({ pw }) {
  if (!pw) return null;
  const len = pw.length;
  const hasUpper = /[A-Z]/.test(pw);
  const hasLower = /[a-z]/.test(pw);
  const hasDigit = /[0-9]/.test(pw);
  const hasSpecial = /[^A-Za-z0-9]/.test(pw);
  const strong = len >= 10 && hasUpper && hasLower && hasDigit && hasSpecial;
  const bars = [
    len >= 1 ? (strong ? "bg-green-500" : "bg-yellow-400") : "bg-gray-200",
    len >= 8 ? (strong ? "bg-green-500" : "bg-yellow-400") : "bg-gray-200",
    len >= 10 ? (strong ? "bg-green-500" : "bg-yellow-400") : "bg-gray-200",
  ];
  const label = strong
    ? { text: "✅ 정책 충족", cls: "text-green-600" }
    : { text: "⚠️ 10자 이상 + 대/소문자 + 숫자 + 특수문자", cls: "text-yellow-700" };
  return (
    <div className="mb-3">
      <div className="flex gap-1 mb-1">
        {bars.map((cls, i) => <div key={i} className={`h-1 flex-1 rounded ${cls}`} />)}
      </div>
      <p className={`text-xs ${label.cls}`}>{label.text}</p>
    </div>
  );
}

const GOOGLE_ENABLED = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);

// 브라우저 환경 분류
// 'webview'  : 카카오/네이버 인앱, Android WebView — Google이 정책으로 OAuth 차단
// 'mobile'   : 모바일 실제 브라우저(Chrome, Samsung Internet 등) — 리디렉션 플로우 사용
// 'desktop'  : 데스크톱 — 팝업 플로우 사용
function getBrowserType() {
  const ua = navigator.userAgent;
  if (/KAKAOTALK/i.test(ua))          return "webview"; // 카카오톡 인앱
  if (/NAVER\(inapp/i.test(ua))       return "webview"; // 네이버 앱 인앱
  if (/\bwv\b/.test(ua) && /Android/i.test(ua)) return "webview"; // Android WebView
  if (/FBAN|FBAV|Instagram|Line\//i.test(ua))    return "webview"; // 기타 인앱
  if (/Android|iPhone|iPad|iPod/i.test(ua))      return "mobile";
  return "desktop";
}

// 모바일 실제 브라우저 전용: 전체 페이지 리디렉션 OAuth
function startGoogleRedirectLogin() {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  if (!clientId) return;
  const state = Math.random().toString(36).slice(2) + Date.now();
  sessionStorage.setItem("google_oauth_state", state);
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: window.location.origin,
    response_type: "token",
    scope: "openid email profile",
    state,
  });
  window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

// Android: intent URL로 외부 브라우저 열기 시도
function openInExternalBrowser() {
  const url = `${window.location.origin}${window.location.pathname}`;
  // Android Chrome intent
  window.location.href =
    `intent://${window.location.hostname}${window.location.pathname}` +
    `#Intent;scheme=https;action=android.intent.action.VIEW;` +
    `category=android.intent.category.BROWSABLE;end`;
  // intent가 실패하면(iOS 등) 클립보드 복사 안내
  setTimeout(() => {
    try { navigator.clipboard.writeText(url); } catch {}
  }, 1000);
}

export default function LoginPage() {
  const { login, loginWithGoogle, user, updateUser } = useAuth();
  const browserType = getBrowserType();

  // 데스크톱 전용: 팝업 방식 (FedCM/패스키 우회)
  const googleLogin = useGoogleLogin({
    onSuccess: (tokenResponse) => handleGoogleSuccess(tokenResponse.access_token),
    onError: () => setErr("Google 로그인에 실패했습니다. 다시 시도해주세요."),
    flow: "implicit",
  });

  const [nameId, setNameId]           = useState("");
  const [pw, setPw]                   = useState("");
  const [showPw, setShowPw]           = useState(false);
  const [err, setErr]                 = useState("");
  const [loading, setLoading]         = useState(false);

  // Forced password change modal (first login)
  const [currentPw, setCurrentPw]       = useState("");
  const [newPw, setNewPw]               = useState("");
  const [newPwConfirm, setNewPwConfirm] = useState("");
  const [changeErr, setChangeErr]       = useState("");
  const [changeMsg, setChangeMsg]       = useState("");
  const showChangePwModal = !!(user?.is_first_login);

  async function handleLogin() {
    if (loading) return;
    setErr("");
    const normalizedId = nameId.trim();
    if (!normalizedId || !pw) {
      setErr("이름과 비밀번호를 입력해주세요.");
      return;
    }
    setLoading(true);
    try {
      const data = await login(normalizedId, pw);
      if (data.is_first_login) {
        setCurrentPw("");
      } else {
        const redirect = sessionStorage.getItem("loginRedirect");
        sessionStorage.removeItem("loginRedirect");
        window.location.replace(redirect || "/");
      }
    } catch (e) {
      const status = e.response?.status;
      if (status === 429) {
        setErr("로그인 시도 횟수를 초과했습니다. 잠시 후 다시 시도해주세요.");
      } else if (status === 403) {
        setErr("비활성화된 계정입니다. 관리자에게 문의하세요.");
      } else if (status === 401) {
        setErr("아이디 또는 비밀번호가 올바르지 않습니다.");
      } else if (!e.response) {
        setErr("서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.");
      } else {
        setErr("로그인에 실패했습니다. 다시 시도해주세요.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSuccess(accessToken) {
    setErr("");
    setLoading(true);
    try {
      await loginWithGoogle(accessToken);
      const redirect = sessionStorage.getItem("loginRedirect");
      sessionStorage.removeItem("loginRedirect");
      window.location.replace(redirect || "/");
    } catch (e) {
      const status = e.response?.status;
      if (status === 403) {
        setErr("비활성화된 계정입니다. 관리자에게 문의하세요.");
      } else if (status === 503) {
        setErr("Google 로그인이 서버에 설정되지 않았습니다. 관리자에게 문의하세요.");
      } else {
        setErr(e.response?.data?.detail || "Google 로그인에 실패했습니다. 다시 시도해주세요.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleChangePassword() {
    setChangeErr(""); setChangeMsg("");
    if (newPw.length < 10) { setChangeErr("새 비밀번호는 10자 이상이어야 합니다."); return; }
    if (!/[A-Z]/.test(newPw)) { setChangeErr("대문자를 1개 이상 포함해주세요."); return; }
    if (!/[a-z]/.test(newPw)) { setChangeErr("소문자를 1개 이상 포함해주세요."); return; }
    if (!/[0-9]/.test(newPw)) { setChangeErr("숫자를 1개 이상 포함해주세요."); return; }
    if (!/[^A-Za-z0-9]/.test(newPw)) { setChangeErr("특수문자를 1개 이상 포함해주세요."); return; }
    if (newPw !== newPwConfirm) { setChangeErr("비밀번호가 일치하지 않습니다."); return; }
    if (newPw === currentPw) { setChangeErr("현재 비밀번호와 다른 값을 입력해주세요."); return; }
    try {
      await api.post(`/api/auth/change-password`, {
        current_password: currentPw,
        new_password: newPw
      });
      setChangeMsg("✅ 비밀번호가 변경되었습니다.");
      setTimeout(() => {
        updateUser({ is_first_login: false });
        window.location.replace("/");
      }, 1200);
    } catch (e) {
      setChangeErr(e.response?.data?.detail || "비밀번호 변경에 실패했습니다.");
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center
                    bg-gradient-to-br from-blue-50 via-white to-slate-100 px-4">

      {/* ── Forced password change modal ─────────────────────────── */}
      {showChangePwModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
          <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-800">새 비밀번호 설정</h2>
            </div>
            <div className="alert-warning rounded-xl px-4 py-3 mb-5 text-sm">
              첫 로그인입니다. <b>10자 이상 + 대/소문자 + 숫자 + 특수문자</b>를 포함해 설정해주세요.
            </div>

            {[
              { label: "현재(임시) 비밀번호", val: currentPw, set: setCurrentPw, placeholder: "현재 비밀번호" },
              { label: "새 비밀번호(10자 이상)", val: newPw, set: setNewPw, placeholder: "새 비밀번호" },
              { label: "새 비밀번호 확인", val: newPwConfirm, set: setNewPwConfirm, placeholder: "비밀번호 확인" },
            ].map(({ label, val, set, placeholder }) => (
              <div key={label} className="mb-3">
                <label className="field-label">{label}</label>
                <input className="field-input" type="password" placeholder={placeholder}
                  value={val} onChange={e => set(e.target.value)} />
              </div>
            ))}

            <PwStrength pw={newPw} />
            {changeErr && <p className="text-red-500 text-xs mb-2">{changeErr}</p>}
            {changeMsg && <p className="text-green-600 text-xs mb-2">{changeMsg}</p>}

            <button className="btn-primary btn w-full py-2.5 rounded-xl"
              onClick={handleChangePassword}>
              비밀번호 저장
            </button>
          </div>
        </div>
      )}

      {/* ── Brand mark ───────────────────────────────────────────── */}
      <div className="mb-8 flex flex-col items-center gap-2">
        <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg">
          <span className="text-white font-bold text-xl">DB</span>
        </div>
        <p className="text-sm font-medium text-gray-400 tracking-wide">Draw Basketball Team</p>
      </div>

      {/* ── Login card ───────────────────────────────────────────── */}
      <div className="bg-white px-8 py-8 rounded-2xl shadow-card w-full max-w-sm">
        <h1 className="text-xl font-bold text-gray-800 mb-1">로그인</h1>
        <p className="text-sm text-gray-400 mb-6">관리자가 전달한 이름과 비밀번호를 입력하세요.</p>

        <input
          className="field-input mb-3"
          placeholder="이름"
          type="text"
          value={nameId}
          onChange={e => { setNameId(e.target.value); setErr(""); }}
          onKeyDown={e => e.key === "Enter" && handleLogin()}
          autoFocus
        />

        <div className="relative mb-1">
          <input
            className="field-input pr-10"
            type={showPw ? "text" : "password"}
            placeholder="비밀번호"
            value={pw}
            onChange={e => { setPw(e.target.value); setErr(""); }}
            onKeyDown={e => e.key === "Enter" && handleLogin()}
          />
          <button type="button" tabIndex={-1}
            onClick={() => setShowPw(v => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
            {showPw ? "🙈" : "👁️"}
          </button>
        </div>

        {err && <p className="text-red-500 text-sm mb-2">{err}</p>}
        <button
          className="btn-primary btn w-full py-2.5 rounded-xl mt-2 disabled:opacity-60"
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? "로그인 중..." : "로그인"}
        </button>

        <button
          type="button"
          onClick={() => { window.location.href = "/signup"; }}
          className="mt-2 w-full py-2.5 rounded-xl border-2 border-blue-500 text-blue-600 font-semibold text-sm hover:bg-blue-50 active:bg-blue-100 transition-colors"
        >
          회원가입
        </button>

        <p className="mt-3 text-xs text-gray-400">
          비밀번호 분실 시 관리자에게 임시 비밀번호 발급을 요청하세요.
        </p>

        {GOOGLE_ENABLED && (
          <>
            <div className="flex items-center gap-3 my-5">
              <span className="flex-1 border-t border-gray-200" />
              <span className="text-xs text-gray-400 shrink-0">또는</span>
              <span className="flex-1 border-t border-gray-200" />
            </div>

            {browserType === "webview" ? (
              /* 인앱 브라우저: Google 정책상 OAuth 불가 → 외부 브라우저 유도 */
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 space-y-2">
                <p className="text-xs font-semibold text-amber-800">
                  ⚠️ 인앱 브라우저에서는 Google 로그인을 사용할 수 없습니다.
                </p>
                <p className="text-xs text-amber-700">
                  Chrome 또는 기본 브라우저에서 접속해주세요.
                </p>
                <button
                  type="button"
                  onClick={openInExternalBrowser}
                  className="w-full mt-1 py-2 rounded-lg bg-amber-500 text-white text-xs font-semibold hover:bg-amber-600 active:bg-amber-700 transition-colors"
                >
                  외부 브라우저에서 열기
                </button>
              </div>
            ) : (
              /* 일반 브라우저: Google 로그인 버튼 */
              <button
                type="button"
                onClick={() => browserType === "mobile" ? startGoogleRedirectLogin() : googleLogin()}
                disabled={loading}
                className="w-full flex items-center justify-center gap-3 border border-gray-300 rounded-xl py-2.5 px-4 hover:bg-gray-50 active:bg-gray-100 transition-colors disabled:opacity-60"
              >
                <svg width="18" height="18" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                <span className="text-sm font-medium text-gray-700">Google로 로그인</span>
              </button>
            )}
          </>
        )}
      </div>

      <p className="mt-8 text-xs text-gray-300">© Your Company. All rights reserved.</p>
    </div>
  );
}
