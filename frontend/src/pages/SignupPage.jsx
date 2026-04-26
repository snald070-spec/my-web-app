import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../api";

const POSITIONS = [
  { value: "PG", label: "PG - 포인트가드" },
  { value: "SG", label: "SG - 슈팅가드" },
  { value: "SF", label: "SF - 스몰포워드" },
  { value: "PF", label: "PF - 파워포워드" },
  { value: "C",  label: "C - 센터" },
  { value: "F",  label: "F - 포워드" },
  { value: "G",  label: "G - 가드" },
];

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  value: String(i + 1).padStart(2, "0"),
  label: `${i + 1}월`,
}));
const DAYS = Array.from({ length: 31 }, (_, i) => ({
  value: String(i + 1).padStart(2, "0"),
  label: `${i + 1}일`,
}));

const CURRENT_YEAR = new Date().getFullYear();

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
    <div>
      <div className="flex gap-1 mb-1">
        {bars.map((cls, i) => <div key={i} className={`h-1 flex-1 rounded ${cls}`} />)}
      </div>
      <p className={`text-xs ${label.cls}`}>{label.text}</p>
    </div>
  );
}

export default function SignupPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [name, setName]           = useState("");
  const [phone, setPhone]         = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [positions, setPositions] = useState([]);
  const [password, setPassword]   = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [showPw, setShowPw]       = useState(false);
  const [month, setMonth]         = useState("");
  const [day, setDay]             = useState("");
  const [err, setErr]             = useState("");
  const [loading, setLoading]     = useState(false);

  function togglePosition(val) {
    setPositions(prev =>
      prev.includes(val) ? prev.filter(p => p !== val) : [...prev, val]
    );
  }

  function formatPhone(raw) {
    const digits = raw.replace(/[^0-9]/g, "").slice(0, 11);
    if (digits.length <= 3) return digits;
    if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
    return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setErr("");

    if (!name.trim()) { setErr("이름을 입력해주세요."); return; }
    if (name.trim().length < 2) { setErr("이름은 2자 이상이어야 합니다."); return; }
    if (!phone) { setErr("핸드폰 번호를 입력해주세요."); return; }
    const phoneDigits = phone.replace(/[^0-9]/g, "");
    if (!/^01[016789]\d{7,8}$/.test(phoneDigits)) { setErr("올바른 핸드폰 번호를 입력해주세요. (010-XXXX-XXXX)"); return; }
    const year = parseInt(birthYear, 10);
    if (!birthYear || isNaN(year) || year < 1930 || year > CURRENT_YEAR - 5) {
      setErr("올바른 출생연도를 입력해주세요."); return;
    }
    if (positions.length === 0) { setErr("포지션을 선택해주세요."); return; }
    if (!password) { setErr("비밀번호를 입력해주세요."); return; }
    if (password.length < 10) { setErr("비밀번호는 10자 이상이어야 합니다."); return; }
    if (!/[A-Z]/.test(password)) { setErr("비밀번호에 대문자를 1개 이상 포함해주세요."); return; }
    if (!/[a-z]/.test(password)) { setErr("비밀번호에 소문자를 1개 이상 포함해주세요."); return; }
    if (!/[0-9]/.test(password)) { setErr("비밀번호에 숫자를 1개 이상 포함해주세요."); return; }
    if (!/[^A-Za-z0-9]/.test(password)) { setErr("비밀번호에 특수문자를 1개 이상 포함해주세요."); return; }
    if (password !== pwConfirm) { setErr("비밀번호가 일치하지 않습니다."); return; }
    if ((month && !day) || (!month && day)) {
      setErr("생일은 월과 일을 모두 입력하거나 둘 다 비워두세요."); return;
    }

    setLoading(true);
    try {
      const birthday = month && day ? `${month}-${day}` : null;
      const { data } = await api.post("/api/auth/register", {
        name: name.trim(),
        phone,
        birth_year: year,
        position: positions.join(","),
        password,
        birthday,
      });

      // 토큰 저장 후 로그인 상태로 전환 (is_approved=false → PendingApprovalPage)
      localStorage.setItem("token", data.access_token);
      if (data.expires_in) {
        localStorage.setItem("tokenExpiresAt", String(Date.now() + data.expires_in * 1000));
      }
      localStorage.setItem("user", JSON.stringify(data));
      window.location.replace("/");
    } catch (e) {
      const status = e.response?.status;
      if (status === 409) {
        setErr("이미 가입된 핸드폰 번호입니다.");
      } else {
        setErr(e.response?.data?.detail || "가입 중 오류가 발생했습니다. 다시 시도해주세요.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center
                    bg-gradient-to-br from-blue-50 via-white to-slate-100 px-4 py-8">

      {/* Brand */}
      <div className="mb-6 flex flex-col items-center gap-2">
        <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg">
          <span className="text-white font-bold text-xl">DB</span>
        </div>
        <p className="text-sm font-medium text-gray-400 tracking-wide">Draw Basketball Team</p>
      </div>

      <div className="bg-white px-8 py-8 rounded-2xl shadow-card w-full max-w-sm">
        <h1 className="text-xl font-bold text-gray-800 mb-1">회원가입</h1>
        <p className="text-sm text-gray-400 mb-6">
          정보를 입력하시면 관리자 승인 후 이용 가능합니다.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">

          {/* 이름 */}
          <div>
            <label className="field-label">이름 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="text"
              placeholder="실명을 입력하세요"
              value={name}
              onChange={e => { setName(e.target.value); setErr(""); }}
              maxLength={20}
            />
          </div>

          {/* 핸드폰 번호 */}
          <div>
            <label className="field-label">핸드폰 번호 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="tel"
              placeholder="010-0000-0000"
              value={phone}
              onChange={e => { setPhone(formatPhone(e.target.value)); setErr(""); }}
              maxLength={13}
            />
          </div>

          {/* 출생연도 */}
          <div>
            <label className="field-label">출생연도 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="number"
              placeholder={`예: 1990`}
              value={birthYear}
              onChange={e => { setBirthYear(e.target.value); setErr(""); }}
              min={1930}
              max={CURRENT_YEAR - 5}
            />
          </div>

          {/* 포지션 */}
          <div>
            <label className="field-label">
              포지션 <span className="text-red-400">*</span>
              <span className="ml-1 text-xs font-normal text-gray-400">(복수 선택 가능)</span>
            </label>
            <div className="flex flex-wrap gap-2 mt-1">
              {POSITIONS.map(p => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => { togglePosition(p.value); setErr(""); }}
                  className={`px-3 py-1.5 rounded-lg text-sm font-semibold border transition-colors ${
                    positions.includes(p.value)
                      ? "bg-blue-500 text-white border-blue-500"
                      : "bg-white text-slate-600 border-slate-200 hover:border-blue-300"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* 비밀번호 */}
          <div>
            <label className="field-label">비밀번호 <span className="text-red-400">*</span></label>
            <div className="relative">
              <input
                className="field-input pr-10"
                type={showPw ? "text" : "password"}
                placeholder="10자 이상 · 대/소문자 · 숫자 · 특수문자"
                value={password}
                onChange={e => { setPassword(e.target.value); setErr(""); }}
              />
              <button type="button" tabIndex={-1}
                onClick={() => setShowPw(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPw ? "🙈" : "👁️"}
              </button>
            </div>
            <div className="mt-1.5">
              <PwStrength pw={password} />
            </div>
          </div>

          {/* 비밀번호 확인 */}
          <div>
            <label className="field-label">비밀번호 확인 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="password"
              placeholder="비밀번호를 다시 입력하세요"
              value={pwConfirm}
              onChange={e => { setPwConfirm(e.target.value); setErr(""); }}
            />
            {pwConfirm && password !== pwConfirm && (
              <p className="text-xs text-red-500 mt-1">비밀번호가 일치하지 않습니다.</p>
            )}
            {pwConfirm && password === pwConfirm && (
              <p className="text-xs text-green-600 mt-1">✅ 비밀번호가 일치합니다.</p>
            )}
          </div>

          {/* 생일 (선택) */}
          <div>
            <label className="field-label">생일 <span className="text-xs text-gray-400">(선택사항)</span></label>
            <div className="flex gap-2">
              <select
                className="field-input flex-1"
                value={month}
                onChange={e => setMonth(e.target.value)}
              >
                <option value="">월</option>
                {MONTHS.map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
              <select
                className="field-input flex-1"
                value={day}
                onChange={e => setDay(e.target.value)}
              >
                <option value="">일</option>
                {DAYS.map(d => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>
          </div>

          {err && <p className="text-red-500 text-sm">{err}</p>}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary btn w-full py-2.5 rounded-xl mt-2 disabled:opacity-60"
          >
            {loading ? "가입 중..." : "가입 신청"}
          </button>
        </form>

        <button
          type="button"
          onClick={() => navigate("/")}
          className="mt-4 w-full text-sm text-gray-400 hover:text-gray-600 text-center"
        >
          ← 로그인으로 돌아가기
        </button>
      </div>
    </div>
  );
}
