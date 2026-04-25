import { useState, useEffect, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import PlayerCareerModal from "../components/PlayerCareerModal";

const TEAM_LABEL = { A: "A팀", B: "B팀", C: "C팀" };
const TEAM_ABBR  = { A: "A", B: "B", C: "C" };
const RANK_MEDAL = { 1: "🥇", 2: "🥈", 3: "🥉" };

const TABS = [
  { key: "standings", label: "순위표" },
  { key: "results",   label: "경기 결과" },
  { key: "stats",     label: "개인 스탯" },
];

export default function LeagueViewPage() {
  const [seasons,       setSeasons]       = useState([]);
  const [seasonId,      setSeasonId]      = useState(null);
  const [currentSeason, setCurrentSeason] = useState(null);
  const [standingsWeek, setStandingsWeek] = useState(1);
  const [standings,     setStandings]     = useState([]);
  const [schedule,      setSchedule]      = useState([]);   // [{week_no, week_date, matches:[]}]
  const [playerStats,   setPlayerStats]   = useState([]);
  const [tab,           setTab]           = useState("standings");
  const [error,         setError]         = useState("");
  const [profileEmpId,  setProfileEmpId]  = useState(null);
  const openProfile = useCallback((empId) => setProfileEmpId(empId), []);

  // 시즌 목록 로드
  useEffect(() => {
    api.get("/api/league/public/seasons")
      .then(r => {
        setSeasons(r.data);
        if (r.data.length > 0) {
          const latest = r.data[0];
          setSeasonId(Number(latest.id));
          setCurrentSeason(latest);
          setStandingsWeek(Number(latest.total_weeks));
        }
      })
      .catch(() => setError("시즌 정보를 불러올 수 없습니다."));
  }, []);

  // 시즌 변경 시 스케줄 + 스탯 로드
  useEffect(() => {
    if (!seasonId) return;
    const s = seasons.find(x => x.id === seasonId);
    setCurrentSeason(s || null);
    if (s) setStandingsWeek(Number(s.total_weeks));

    Promise.all([
      api.get(`/api/league/public/seasons/${seasonId}/schedule`),
      api.get(`/api/league/public/seasons/${seasonId}/stats/players`),
    ]).then(([schRes, statRes]) => {
      setSchedule(schRes.data.weeks || []);
      setPlayerStats(statRes.data || []);
    }).catch(() => {});
  }, [seasonId]);

  // 주차 변경 시 순위 로드
  useEffect(() => {
    if (!seasonId || !standingsWeek) return;
    api.get(`/api/league/public/seasons/${seasonId}/standings`, {
      params: { week_no: standingsWeek },
    })
      .then(r => setStandings(r.data.rows || []))
      .catch(() => setStandings([]));
  }, [seasonId, standingsWeek]);

  // ── Derived ──────────────────────────────────────────────────────────────
  const totalWeeks = Number(currentSeason?.total_weeks || 1);

  // Finished matches only — grouped by week
  const resultWeeks = useMemo(() =>
    schedule.map(w => ({
      ...w,
      matches: (w.matches || []).filter(m => m.status === "FINAL" || m.status === "FORFEIT"),
    })).filter(w => w.matches.length > 0),
    [schedule]
  );

  // ── Render helpers ────────────────────────────────────────────────────────
  function MatchBadge({ status }) {
    if (status === "FINAL")     return <span className="badge-green">확정</span>;
    if (status === "FORFEIT")   return <span className="badge-red">기권</span>;
    if (status === "SCHEDULED") return <span className="badge-gray">예정</span>;
    return <span className="badge-gray">{status}</span>;
  }

  function TeamTag({ code }) {
    const colours = { A: "bg-blue-100 text-blue-700", B: "bg-red-100 text-red-700", C: "bg-green-100 text-green-700" };
    return (
      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${colours[code] || "bg-gray-100 text-gray-600"}`}>
        {TEAM_ABBR[code] || code}
      </span>
    );
  }

  // ── Tab: 순위표 ────────────────────────────────────────────────────────────
  function TabStandings() {
    return (
      <div className="space-y-3">
        <div className="action-bar">
          <label className="text-sm text-gray-500 font-medium">{standingsWeek}주차 기준</label>
          <input
            type="range"
            min={1}
            max={totalWeeks}
            value={standingsWeek}
            onChange={e => setStandingsWeek(Number(e.target.value))}
            className="w-40 accent-blue-500"
          />
        </div>

        {standings.length === 0 ? (
          <div className="empty-state py-10"><p className="empty-state-text">순위 데이터가 없습니다.</p></div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {standings.map(row => (
              <div key={row.team_code} className="card p-4 flex items-center gap-4">
                <div className="text-2xl w-8 text-center">{RANK_MEDAL[row.rank] || row.rank}</div>
                <div className="shrink-0">
                  <TeamTag code={row.team_code} />
                  <span className="ml-2 font-bold text-gray-800">{TEAM_LABEL[row.team_code]}</span>
                </div>
                <div className="flex-1 grid grid-cols-4 sm:grid-cols-7 gap-2 text-center text-sm">
                  <div><p className="text-[10px] text-gray-400 uppercase">승점</p><p className="font-bold text-blue-600">{row.points}</p></div>
                  <div><p className="text-[10px] text-gray-400 uppercase">경기</p><p className="font-semibold">{row.played}</p></div>
                  <div><p className="text-[10px] text-gray-400 uppercase">승</p><p className="font-semibold text-green-600">{row.wins}</p></div>
                  <div><p className="text-[10px] text-gray-400 uppercase">무</p><p className="font-semibold text-gray-500">{row.draws}</p></div>
                  <div className="hidden sm:block"><p className="text-[10px] text-gray-400 uppercase">패</p><p className="font-semibold text-red-500">{row.losses}</p></div>
                  <div className="hidden sm:block"><p className="text-[10px] text-gray-400 uppercase">득실</p><p className={`font-semibold ${row.goal_diff > 0 ? "text-green-600" : row.goal_diff < 0 ? "text-red-500" : "text-gray-500"}`}>{row.goal_diff > 0 ? `+${row.goal_diff}` : row.goal_diff}</p></div>
                  <div className="hidden sm:block"><p className="text-[10px] text-gray-400 uppercase">득/실</p><p className="font-semibold text-xs">{row.goals_for}/{row.goals_against}</p></div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="text-xs text-gray-400 text-center pt-1">
          승: +3점 · 무: +2점 · 패: +1점 · 기권패: 0점
        </div>
      </div>
    );
  }

  // ── Tab: 경기 결과 ─────────────────────────────────────────────────────────
  function TabResults() {
    if (resultWeeks.length === 0) {
      return <div className="empty-state py-10"><p className="empty-state-text">아직 확정된 경기 결과가 없습니다.</p></div>;
    }
    return (
      <div className="space-y-4">
        {resultWeeks.map(w => (
          <div key={w.week_no} className="card overflow-hidden">
            <div className="px-4 py-2 border-b bg-gray-50 flex items-center gap-2">
              <span className="font-bold text-gray-700 text-sm">{w.week_no}주차</span>
              {w.week_date && (
                <span className="text-xs text-gray-400">{String(w.week_date).slice(0, 10)}</span>
              )}
            </div>
            <div className="divide-y">
              {w.matches.map(m => {
                const isForfeit = m.status === "FORFEIT";
                const homeWon   = !isForfeit && m.home_score > m.away_score;
                const awayWon   = !isForfeit && m.away_score > m.home_score;
                return (
                  <div key={m.match_id} className="px-4 py-3 flex items-center gap-2 sm:gap-4">
                    {/* Home team */}
                    <div className={`flex items-center gap-1.5 flex-1 justify-end ${homeWon ? "font-bold" : ""}`}>
                      <span className="text-sm text-gray-700">{TEAM_LABEL[m.home_team]}</span>
                      <TeamTag code={m.home_team} />
                    </div>

                    {/* Score */}
                    <div className="shrink-0 text-center w-24">
                      {isForfeit ? (
                        <div className="space-y-0.5">
                          <MatchBadge status="FORFEIT" />
                          <p className="text-[10px] text-gray-400">
                            {TEAM_LABEL[m.forfeited_team]} 기권패
                          </p>
                        </div>
                      ) : (
                        <div className="flex items-center justify-center gap-1">
                          <span className={`text-lg tabular-nums font-bold ${homeWon ? "text-blue-600" : "text-gray-400"}`}>
                            {m.home_score ?? "-"}
                          </span>
                          <span className="text-gray-300 text-sm">:</span>
                          <span className={`text-lg tabular-nums font-bold ${awayWon ? "text-blue-600" : "text-gray-400"}`}>
                            {m.away_score ?? "-"}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Away team */}
                    <div className={`flex items-center gap-1.5 flex-1 ${awayWon ? "font-bold" : ""}`}>
                      <TeamTag code={m.away_team} />
                      <span className="text-sm text-gray-700">{TEAM_LABEL[m.away_team]}</span>
                    </div>

                    <div className="shrink-0">
                      <Link
                        to={`/league/scoresheet/view?seasonId=${seasonId}&matchId=${m.match_id}`}
                        className="btn-secondary btn btn-sm"
                      >
                        기록지 보기
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Tab: 개인 스탯 ─────────────────────────────────────────────────────────
  function TabStats() {
    if (playerStats.length === 0) {
      return <div className="empty-state py-10"><p className="empty-state-text">기록된 개인 스탯이 없습니다.</p></div>;
    }
    return (
      <div className="space-y-4">
        {/* Top 3 scorer spotlight */}
        <div className="grid grid-cols-3 gap-3">
          {playerStats.slice(0, 3).map((p, i) => (
            <div key={p.emp_id} className="card p-3 text-center">
              <div className="text-2xl mb-1">{RANK_MEDAL[i + 1]}</div>
              <button
                type="button"
                onClick={() => openProfile(p.emp_id)}
                className="font-bold text-gray-800 text-sm truncate hover:text-blue-600 hover:underline w-full"
              >{p.name}</button>
              <TeamTag code={p.team_code} />
              <div className="mt-2">
                <p className="text-2xl font-bold text-blue-600">{p.total_points}</p>
                <p className="text-[10px] text-gray-400">총 득점</p>
              </div>
              <div className="mt-1 text-[10px] text-gray-400 space-y-0.5">
                <div>{p.games}경기 · {p.games > 0 ? (p.total_points / p.games).toFixed(1) : 0}점/경기</div>
              </div>
            </div>
          ))}
        </div>

        {/* Full stat table */}
        <div className="card overflow-hidden">
          <div className="overflow-x-auto w-full">
            <table className="data-table" style={{ minWidth: 640 }}>
              <thead>
                <tr>
                  <th className="text-left" style={{ minWidth: 28 }}>순</th>
                  <th className="text-left" style={{ minWidth: 64 }}>이름</th>
                  <th style={{ minWidth: 36 }}>팀</th>
                  <th style={{ minWidth: 36 }}>경기</th>
                  <th className="text-blue-600" style={{ minWidth: 44 }}>총득점</th>
                  <th style={{ minWidth: 40 }} title="경기당 평균">평균</th>
                  <th style={{ minWidth: 36 }} title="2점 성공">2M</th>
                  <th style={{ minWidth: 36 }} title="3점 성공">3M</th>
                  <th style={{ minWidth: 36 }} title="자유투">FM</th>
                  <th style={{ minWidth: 36 }} title="공수리바운드">RB</th>
                  <th style={{ minWidth: 36 }} title="어시스트">AS</th>
                  <th style={{ minWidth: 36 }} title="스틸">ST</th>
                  <th style={{ minWidth: 36 }} title="블락">BK</th>
                  <th style={{ minWidth: 36 }} title="턴오버">TO</th>
                </tr>
              </thead>
              <tbody>
                {playerStats.map((p, i) => (
                  <tr key={p.emp_id}>
                    <td className="text-gray-400 text-xs">{i + 1}</td>
                    <td className="font-semibold text-left">
                      <button
                        type="button"
                        onClick={() => openProfile(p.emp_id)}
                        className="text-gray-800 hover:text-blue-600 hover:underline text-left"
                      >{p.name}</button>
                    </td>
                    <td><TeamTag code={p.team_code} /></td>
                    <td className="tabular-nums">{p.games}</td>
                    <td className="font-bold text-blue-600 tabular-nums">{p.total_points}</td>
                    <td className="tabular-nums text-gray-500">{p.games > 0 ? (p.total_points / p.games).toFixed(1) : 0}</td>
                    <td className="tabular-nums">{p.fg2_made}</td>
                    <td className="tabular-nums">{p.fg3_made}</td>
                    <td className="tabular-nums">{p.ft_made}</td>
                    <td className="tabular-nums">{p.o_rebound + p.d_rebound}</td>
                    <td className="tabular-nums">{p.assist}</td>
                    <td className="tabular-nums">{p.steal}</td>
                    <td className="tabular-nums">{p.block}</td>
                    <td className="tabular-nums text-red-400">{p.turnover}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────────────────
  return (
    <div className="page-container space-y-4">
      {profileEmpId && (
        <PlayerCareerModal empId={profileEmpId} onClose={() => setProfileEmpId(null)} />
      )}
      {error && <div className="alert-error">{error}</div>}

      {/* Season selector */}
      <div className="card p-4 flex items-center gap-3 flex-wrap">
        <select
          className="field-select"
          style={{ minWidth: 200 }}
          value={seasonId || ""}
          onChange={e => {
            const id = Number(e.target.value);
            setSeasonId(id);
            setStandings([]);
            setSchedule([]);
            setPlayerStats([]);
          }}
        >
          <option value="">시즌 선택</option>
          {seasons.map(s => (
            <option key={s.id} value={s.id}>{s.title} ({s.code})</option>
          ))}
        </select>
        {currentSeason && (
          <span className="text-sm text-gray-500">
            총 {currentSeason.total_weeks}주차
            {currentSeason.start_date ? ` · 시작일 ${String(currentSeason.start_date).slice(0, 10)}` : ""}
          </span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex border-b bg-white rounded-t-xl overflow-hidden shadow-sm">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 py-3 text-sm font-semibold transition-colors ${
              tab === t.key
                ? "border-b-2 border-blue-500 text-blue-600 bg-blue-50"
                : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {seasons.length === 0 ? (
        <div className="empty-state py-12">
          <p className="empty-state-text">등록된 리그 시즌이 없습니다.</p>
        </div>
      ) : (
        <div>
          {tab === "standings" && <TabStandings />}
          {tab === "results"   && <TabResults />}
          {tab === "stats"     && <TabStats />}
        </div>
      )}
    </div>
  );
}
