import { useState, useRef, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../api";
import Avatar from "../components/Avatar";

const POSITIONS = [
  { value: "", label: "선택 안 함" },
  { value: "PG", label: "PG — 포인트가드" },
  { value: "SG", label: "SG — 슈팅가드" },
  { value: "SF", label: "SF — 스몰포워드" },
  { value: "PF", label: "PF — 파워포워드" },
  { value: "C",  label: "C — 센터" },
];

const CURRENT_YEAR = new Date().getFullYear();

export default function MyProfilePage() {
  const { user, updateUser } = useAuth();

  const [name,      setName]      = useState(user?.name      ?? "");
  const [birthYear, setBirthYear] = useState(user?.birth_year ? String(user.birth_year) : "");
  const [position,  setPosition]  = useState(user?.position  ?? "");

  const [saving,   setSaving]   = useState(false);
  const [saveMsg,  setSaveMsg]  = useState("");
  const [saveErr,  setSaveErr]  = useState("");

  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarPreview,   setAvatarPreview]   = useState(user?.avatar_url ?? null);
  const [avatarErr,       setAvatarErr]       = useState("");
  const avatarInputRef = useRef(null);

  // 페이지 진입 시 최신 프로필 로드
  useEffect(() => {
    api.get("/api/auth/me").then(({ data }) => {
      updateUser(data);
      setName(data.name ?? "");
      setBirthYear(data.birth_year ? String(data.birth_year) : "");
      setPosition(data.position ?? "");
      setAvatarPreview(data.avatar_url ?? null);
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAvatarChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarErr("");
    setAvatarUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/api/users/${user.emp_id}/avatar`, form);
      const url = data.avatar_url + "&bust=" + Date.now();
      setAvatarPreview(url);
      updateUser({ avatar_url: data.avatar_url });
    } catch (err) {
      setAvatarErr(err?.response?.data?.detail || "사진 업로드에 실패했습니다.");
    } finally {
      setAvatarUploading(false);
      if (avatarInputRef.current) avatarInputRef.current.value = "";
    }
  }

  async function handleAvatarDelete() {
    setAvatarErr("");
    setAvatarUploading(true);
    try {
      await api.delete(`/api/users/${user.emp_id}/avatar`);
      setAvatarPreview(null);
      updateUser({ avatar_url: null });
    } catch (err) {
      setAvatarErr(err?.response?.data?.detail || "사진 삭제에 실패했습니다.");
    } finally {
      setAvatarUploading(false);
    }
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaveMsg("");
    setSaveErr("");

    const trimmedName = name.trim();
    if (!trimmedName) { setSaveErr("이름을 입력해주세요."); return; }

    const byYear = birthYear ? parseInt(birthYear, 10) : null;
    if (birthYear && (isNaN(byYear) || byYear < 1940 || byYear > CURRENT_YEAR - 5)) {
      setSaveErr("출생연도가 올바르지 않습니다.");
      return;
    }

    setSaving(true);
    try {
      const body = { name: trimmedName, birth_year: byYear, position: position || null };
      const { data } = await api.patch("/api/users/me", body);
      updateUser({ name: data.name, birth_year: data.birth_year, position: data.position });
      setSaveMsg("저장되었습니다.");
    } catch (err) {
      setSaveErr(err?.response?.data?.detail || "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  const age = birthYear && !isNaN(parseInt(birthYear, 10))
    ? CURRENT_YEAR - parseInt(birthYear, 10)
    : null;

  return (
    <div className="page-container space-y-5 max-w-lg mx-auto">

      {/* Avatar section */}
      <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5 flex flex-col items-center gap-3">
        <div className="relative">
          <Avatar
            name={user?.name}
            avatarUrl={avatarPreview}
            size="xl"
          />
          {avatarUploading && (
            <div className="absolute inset-0 rounded-full bg-black/30 flex items-center justify-center">
              <span className="text-white text-xs font-semibold">...</span>
            </div>
          )}
        </div>

        <input
          ref={avatarInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={handleAvatarChange}
        />

        <div className="flex gap-2">
          <button
            type="button"
            disabled={avatarUploading}
            onClick={() => avatarInputRef.current?.click()}
            className="px-4 py-2 rounded-xl bg-blue-500 text-white text-sm font-semibold hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            사진 변경
          </button>
          {avatarPreview && (
            <button
              type="button"
              disabled={avatarUploading}
              onClick={handleAvatarDelete}
              className="px-4 py-2 rounded-xl bg-slate-100 text-slate-600 text-sm font-semibold hover:bg-red-50 hover:text-red-500 disabled:opacity-50 transition-colors"
            >
              삭제
            </button>
          )}
        </div>

        {avatarErr && (
          <p className="text-xs text-red-500 text-center">{avatarErr}</p>
        )}
        <p className="text-[11px] text-slate-400">JPG · PNG · WEBP · 최대 5MB</p>
      </div>

      {/* Profile form */}
      <form onSubmit={handleSave} className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5 space-y-4">

        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1.5">이름</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="이름을 입력하세요"
            maxLength={30}
          />
        </div>

        {/* Birth year */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1.5">
            출생연도
            {age !== null && (
              <span className="ml-2 font-normal text-blue-500">{age}세</span>
            )}
          </label>
          <input
            type="number"
            value={birthYear}
            onChange={e => setBirthYear(e.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="예: 1990"
            min={1940}
            max={CURRENT_YEAR - 5}
          />
        </div>

        {/* Position */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1.5">포지션</label>
          <select
            value={position}
            onChange={e => setPosition(e.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            {POSITIONS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        {saveErr && (
          <div className="rounded-xl bg-red-50 border border-red-200 px-3 py-2.5 text-sm text-red-600">
            {saveErr}
          </div>
        )}
        {saveMsg && (
          <div className="rounded-xl bg-green-50 border border-green-200 px-3 py-2.5 text-sm text-green-600">
            {saveMsg}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full py-3 rounded-xl bg-blue-500 text-white font-bold text-sm hover:bg-blue-600 disabled:opacity-50 transition-colors"
        >
          {saving ? "저장 중..." : "저장하기"}
        </button>
      </form>
    </div>
  );
}
