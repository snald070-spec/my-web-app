import { useEffect, useState } from "react";
import api from "../api";
import Avatar from "./Avatar";

const TEAM_COLOR = {
  A: "bg-blue-100 text-blue-700",
  B: "bg-red-100 text-red-700",
  C: "bg-green-100 text-green-700",
};

function TeamBadge({ code }) {
  if (!code) return null;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${TEAM_COLOR[code] ?? "bg-gray-100 text-gray-600"}`}>
      {code}팀
    </span>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="mt-0.5 text-lg font-bold text-slate-800">{value ?? "-"}</p>
      {sub && <p className="text-[10px] text-slate-400">{sub}</p>}
    </div>
  );
}

function PctBar({ value }) {
  if (value == null) return <span className="text-slate-400">-</span>;
  return (
    <span className={value >= 50 ? "text-blue-600 font-semibold" : "text-slate-700"}>
      {value}%
    </span>
  );
}

export default function PlayerCareerModal({ empId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!empId) return;
    setLoading(true);
    setError("");
    api.get(`/api/league/public/players/${empId}/stats`)
      .then(r => setData(r.data))
      .catch(() => setError("데이터를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [empId]);

  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [onClose]);

  const c = data?.career;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center px-0 sm:px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-t-2xl sm:rounded-2xl bg-slate-50 shadow-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-200 bg-white rounded-t-2xl sm:rounded-t-2xl shrink-0">
          <div className="flex items-center gap-3">
            <Avatar name={data?.name ?? empId} avatarUrl={data?.avatar_url} size="lg" />
            <div>
              <p className="text-xs text-slate-400 font-medium">선수 프로필</p>
              <h2 className="text-lg font-bold text-slate-900">
                {loading ? "로딩 중..." : (data?.name ?? empId)}
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full w-8 h-8 flex items-center justify-center text-slate-500 hover:bg-slate-100 text-lg"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-4 py-4 space-y-4">
          {error && (
            <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          )}

          {loading && !error && (
            <div className="py-10 text-center text-sm text-slate-400">불러오는 중...</div>
          )}

          {!loading && !error && data && (
            <>
              {/* Career summary */}
              {c ? (
                <div className="space-y-3">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider px-1">
                    커리어 통산 ({c.games}경기)
                  </p>

                  {/* Avg stat grid */}
                  <div className="grid grid-cols-4 gap-2">
                    <StatCard label="평균득점" value={c.avg_points} sub="PTS" />
                    <StatCard label="평균리바" value={c.avg_rebound} sub="REB" />
                    <StatCard label="평균어시" value={c.avg_assist} sub="AST" />
                    <StatCard label="평균스틸" value={c.avg_steal} sub="STL" />
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <StatCard label="평균블락" value={c.avg_block} sub="BLK" />
                    <StatCard label="평균턴오버" value={c.avg_turnover} sub="TOV" />
                    <StatCard label="총득점" value={c.total_points} sub="합계" />
                    <StatCard label="총경기" value={c.games} sub="G" />
                  </div>

                  {/* Shooting pct row */}
                  <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">슈팅 성공률</p>
                    <div className="grid grid-cols-3 gap-3 text-center">
                      <div>
                        <p className="text-[11px] text-slate-500">2점</p>
                        <p className="text-sm font-bold"><PctBar value={c.fg2_pct} /></p>
                        <p className="text-[10px] text-slate-400">{c.fg2_made}/{c.fg2_attempted}</p>
                      </div>
                      <div>
                        <p className="text-[11px] text-slate-500">3점</p>
                        <p className="text-sm font-bold"><PctBar value={c.fg3_pct} /></p>
                        <p className="text-[10px] text-slate-400">{c.fg3_made}/{c.fg3_attempted}</p>
                      </div>
                      <div>
                        <p className="text-[11px] text-slate-500">자유투</p>
                        <p className="text-sm font-bold"><PctBar value={c.ft_pct} /></p>
                        <p className="text-[10px] text-slate-400">{c.ft_made}/{c.ft_attempted}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-sm text-slate-400">기록된 경기 스탯이 없습니다.</div>
              )}

              {/* Season breakdown */}
              {data.seasons.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider px-1">시즌별 기록</p>
                  <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs" style={{ minWidth: 540 }}>
                        <thead>
                          <tr className="bg-slate-50 border-b border-slate-200">
                            <th className="text-left px-3 py-2 font-semibold text-slate-500">시즌</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">팀</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">G</th>
                            <th className="px-2 py-2 font-semibold text-blue-600">PTS</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">평균</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">REB</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">AST</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">STL</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">BLK</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">2P%</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">3P%</th>
                            <th className="px-2 py-2 font-semibold text-slate-500">FT%</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.seasons.map((s) => (
                            <tr key={s.season_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                              <td className="px-3 py-2 font-medium text-slate-700 whitespace-nowrap">{s.season_title}</td>
                              <td className="px-2 py-2 text-center"><TeamBadge code={s.team_code} /></td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-600">{s.games}</td>
                              <td className="px-2 py-2 text-center tabular-nums font-bold text-blue-600">{s.total_points}</td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-500">{s.avg_points}</td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-600">{s.avg_rebound}</td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-600">{s.avg_assist}</td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-600">{s.avg_steal}</td>
                              <td className="px-2 py-2 text-center tabular-nums text-slate-600">{s.avg_block}</td>
                              <td className="px-2 py-2 text-center tabular-nums"><PctBar value={s.fg2_pct} /></td>
                              <td className="px-2 py-2 text-center tabular-nums"><PctBar value={s.fg3_pct} /></td>
                              <td className="px-2 py-2 text-center tabular-nums"><PctBar value={s.ft_pct} /></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
