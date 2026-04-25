import { useState, useEffect, useMemo } from "react";
import api from "../api";
import PlayerCareerModal from "../components/PlayerCareerModal";
import Avatar from "../components/Avatar";

const POSITION_LABEL = {
  PG: "포인트가드",
  SG: "슈팅가드",
  SF: "스몰포워드",
  PF: "파워포워드",
  C:  "센터",
};

function StatPill({ label, value }) {
  if (value == null) return null;
  return (
    <span className="inline-flex items-center gap-0.5 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] text-blue-700">
      <span className="font-semibold">{value}</span>
      <span className="text-blue-400">{label}</span>
    </span>
  );
}

function MemberCard({ member, onSelect }) {
  const c = member.career_avg;
  const posLabel = member.position
    ? (POSITION_LABEL[member.position] || member.position)
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(member.emp_id)}
      className="w-full text-left rounded-2xl bg-white border border-slate-200 px-4 py-3.5 shadow-sm hover:shadow-md hover:border-blue-300 transition-all active:scale-[0.99]"
    >
      <div className="flex items-start justify-between gap-2">
        {/* Left: avatar + name, meta */}
        <div className="flex items-start gap-3 min-w-0">
          <Avatar name={member.name} avatarUrl={member.avatar_url} size="md" className="mt-0.5 shrink-0" />
          <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-slate-900 text-base">{member.name}</span>
            {posLabel && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500 font-medium">
                {posLabel}
              </span>
            )}
          </div>
          <div className="mt-0.5 text-[12px] text-slate-400 flex items-center gap-2">
            {member.age && <span>{member.age}세</span>}
          </div>
          </div>
        </div>

        {/* Right: career games */}
        {c && (
          <div className="shrink-0 text-right">
            <p className="text-[11px] text-slate-400">{c.games}경기</p>
          </div>
        )}
      </div>

      {/* Career avg stats */}
      {c ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <StatPill label="PTS" value={c.avg_points} />
          <StatPill label="REB" value={c.avg_rebound} />
          <StatPill label="AST" value={c.avg_assist} />
          <StatPill label="STL" value={c.avg_steal} />
          <StatPill label="BLK" value={c.avg_block} />
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-slate-400">경기 기록 없음</p>
      )}
    </button>
  );
}

export default function MembersPage() {
  const [members,   setMembers]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");
  const [query,     setQuery]     = useState("");
  const [profileId, setProfileId] = useState(null);

  useEffect(() => {
    api.get("/api/users/public/members")
      .then(r => setMembers(r.data))
      .catch(() => setError("회원 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return members;
    const q = query.trim().toLowerCase();
    return members.filter(m =>
      (m.name || "").toLowerCase().includes(q)
    );
  }, [members, query]);

  return (
    <div className="page-container space-y-4">
      {profileId && (
        <PlayerCareerModal empId={profileId} onClose={() => setProfileId(null)} />
      )}

      {/* Header */}
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold text-slate-900">회원 검색</h1>
        {!loading && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500 font-medium">
            {members.length}명
          </span>
        )}
      </div>

      {/* Search box */}
      <div className="relative">
        <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm select-none">🔍</span>
        <input
          type="text"
          className="w-full rounded-2xl border border-slate-200 bg-white pl-9 pr-4 py-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="이름으로 검색"
          value={query}
          onChange={e => setQuery(e.target.value)}
          autoComplete="off"
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none"
          >
            ×
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="py-10 text-center text-sm text-slate-400">불러오는 중...</div>
      )}

      {/* Empty state */}
      {!loading && !error && filtered.length === 0 && (
        <div className="py-10 text-center text-sm text-slate-400">
          {query ? `"${query}"에 해당하는 회원이 없습니다.` : "등록된 회원이 없습니다."}
        </div>
      )}

      {/* Member list */}
      {!loading && !error && filtered.length > 0 && (
        <div className="space-y-2.5">
          {filtered.map(m => (
            <MemberCard key={m.emp_id} member={m} onSelect={setProfileId} />
          ))}
        </div>
      )}

      {/* Stats legend */}
      {!loading && members.length > 0 && (
        <p className="text-center text-[11px] text-slate-400 pb-2">
          카드를 누르면 커리어 전체 기록을 볼 수 있습니다 · PTS 득점 REB 리바운드 AST 어시스트
        </p>
      )}
    </div>
  );
}
