import { useState } from "react";
import { GoogleLogin } from "@react-oauth/google";
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

export default function LoginPage() {
  const { login, loginWithGoogle, user, updateUser } = useAuth();

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

  async function handleGoogleSuccess(credentialResponse) {
    setErr("");
    setLoading(true);
    try {
      await loginWithGoogle(credentialResponse.credential);
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
            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={() => setErr("Google 로그인에 실패했습니다. 다시 시도해주세요.")}
                locale="ko"
                text="signin_with"
                shape="rectangular"
                size="large"
                width="100%"
              />
            </div>
          </>
        )}
      </div>

      <p className="mt-8 text-xs text-gray-300">© Your Company. All rights reserved.</p>
    </div>
  );
}
