import { useState, useEffect } from "react";
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
const DRAFT_KEY = "profileSetupDraft";

function loadDraft() {
  try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}"); }
  catch { return {}; }
}

export default function GoogleProfileSetupPage() {
  const { user, updateUser } = useAuth();

  const draft = loadDraft();

  const [name, setName]           = useState(draft.name ?? (user?.name || ""));
  const [phone, setPhone]         = useState(draft.phone ?? "");
  const [birthYear, setBirthYear] = useState(draft.birthYear ?? "");
  const [positions, setPositions] = useState(draft.positions ?? []);
  const [month, setMonth]         = useState(draft.month ?? "");
  const [day, setDay]             = useState(draft.day ?? "");

  function togglePosition(val) {
    setPositions(prev =>
      prev.includes(val) ? prev.filter(p => p !== val) : [...prev, val]
    );
  }
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(user?.avatar_url || "");

  const [err, setErr]     = useState("");
  const [loading, setLoading] = useState(false);

  // 입력 내용을 localStorage에 자동 저장 (토큰 만료 후 재로그인해도 유지)
  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ name, phone, birthYear, positions, month, day }));
  }, [name, phone, birthYear, positions, month, day]);

  function handleAvatarChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { setErr("사진은 2MB 이하만 가능합니다."); return; }
    setAvatarFile(file);
    setAvatarPreview(URL.createObjectURL(file));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setErr("");

    if (!name.trim())             { setErr("이름을 입력해주세요."); return; }
    if (name.trim().length < 2)   { setErr("이름은 2자 이상이어야 합니다."); return; }
    const year = parseInt(birthYear, 10);
    if (!birthYear || isNaN(year) || year < 1930 || year > CURRENT_YEAR - 5) {
      setErr("올바른 출생연도를 입력해주세요."); return;
    }
    if (positions.length === 0) { setErr("포지션을 선택해주세요."); return; }
    if ((month && !day) || (!month && day)) {
      setErr("생일은 월과 일을 모두 입력하거나 둘 다 비워두세요."); return;
    }

    setLoading(true);
    try {
      let avatarUrl = avatarPreview || null;

      // 사진 업로드 (선택)
      if (avatarFile) {
        const form = new FormData();
        form.append("file", avatarFile);
        const { data: uploaded } = await api.post("/api/users/me/avatar", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        avatarUrl = uploaded.avatar_url;
      }

      const birthday = month && day ? `${month}-${day}` : null;
      const phoneDigits = phone ? phone.replace(/[^0-9]/g, "") : undefined;
      const { data } = await api.post("/api/auth/complete-profile", {
        name: name.trim(),
        birth_year: year,
        position: positions.join(","),
        birthday,
        phone: phoneDigits || undefined,
        avatar_url: avatarUrl,
      });

      // 가입 완료 시 draft 삭제
      localStorage.removeItem(DRAFT_KEY);

      // 토큰 & 유저 상태 갱신
      localStorage.setItem("token", data.access_token);
      if (data.expires_in) {
        localStorage.setItem("tokenExpiresAt", String(Date.now() + data.expires_in * 1000));
      }
      updateUser({ ...data, is_profile_complete: true });

      const redirect = sessionStorage.getItem("loginRedirect");
      sessionStorage.removeItem("loginRedirect");
      window.location.replace(redirect || "/");
    } catch (e) {
      const status = e.response?.status;
      if (status === 401) {
        // 토큰 만료 — draft는 유지하고 인증 정보만 지워서 재로그인 유도
        localStorage.removeItem("token");
        localStorage.removeItem("tokenExpiresAt");
        localStorage.removeItem("user");
        sessionStorage.clear();
        window.location.href = "/";
        return;
      }
      setErr(e.response?.data?.detail || "저장 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const initials = (name || "?").charAt(0).toUpperCase();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center
                    bg-gradient-to-br from-blue-50 via-white to-slate-100 px-4">
      <div className="bg-white px-8 py-8 rounded-2xl shadow-card w-full max-w-sm">

        {/* 헤더 */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center mx-auto mb-3 shadow">
            <span className="text-white font-bold text-lg">DB</span>
          </div>
          <h1 className="text-lg font-bold text-gray-800">프로필 설정</h1>
          <p className="text-sm text-gray-400 mt-1">
            Draw Basketball 가입을 완료해주세요.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">

          {/* 프로필 사진 (선택) */}
          <div className="flex flex-col items-center gap-2">
            <label className="cursor-pointer group relative">
              <div className="w-20 h-20 rounded-full overflow-hidden bg-blue-500 flex items-center justify-center ring-4 ring-blue-100 group-hover:ring-blue-300 transition-all">
                {avatarPreview
                  ? <img src={avatarPreview} alt="프로필" className="w-full h-full object-cover" />
                  : <span className="text-white font-bold text-2xl">{initials}</span>
                }
              </div>
              <div className="absolute bottom-0 right-0 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center ring-2 ring-white">
                <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <input type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
            </label>
            <p className="text-xs text-gray-400">사진 선택 (선택사항)</p>
          </div>

          {/* 이름 (필수) */}
          <div>
            <label className="field-label">이름 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="text"
              placeholder="실명을 입력하세요"
              value={name}
              onChange={e => setName(e.target.value)}
              maxLength={20}
            />
          </div>

          {/* 핸드폰 번호 (선택) */}
          <div>
            <label className="field-label">핸드폰 번호 <span className="text-xs text-gray-400">(선택사항)</span></label>
            <input
              className="field-input"
              type="tel"
              placeholder="010-0000-0000"
              value={phone}
              onChange={e => {
                const digits = e.target.value.replace(/[^0-9]/g, "").slice(0, 11);
                let formatted = digits;
                if (digits.length > 7) formatted = `${digits.slice(0,3)}-${digits.slice(3,7)}-${digits.slice(7)}`;
                else if (digits.length > 3) formatted = `${digits.slice(0,3)}-${digits.slice(3)}`;
                setPhone(formatted);
              }}
              maxLength={13}
            />
          </div>

          {/* 출생연도 (필수) */}
          <div>
            <label className="field-label">출생연도 <span className="text-red-400">*</span></label>
            <input
              className="field-input"
              type="number"
              placeholder={`예: 1990`}
              value={birthYear}
              onChange={e => setBirthYear(e.target.value)}
              min={1930}
              max={CURRENT_YEAR - 5}
            />
          </div>

          {/* 포지션 (필수, 복수 선택) */}
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
                  onClick={() => togglePosition(p.value)}
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
            {loading ? "저장 중..." : "가입 완료"}
          </button>
        </form>
      </div>
    </div>
  );
}
