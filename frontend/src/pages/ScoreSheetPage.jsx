import { Fragment, useState, useEffect, useMemo } from "react";
import api from "../api";
import MetricInfoChip from "../components/MetricInfoChip";

// ── Stat column definitions ──────────────────────────────────────────────────
const SHOOTING_GROUPS = [
  { prefix: "ft", label: "자유투" },
  { prefix: "fg2", label: "2점" },
  { prefix: "fg3", label: "3점" },
];

const ETC_COLS = [
  { key: "o_rebound", label: "공리", title: "공격리바운드" },
  { key: "d_rebound", label: "수리", title: "수비리바운드" },
  { key: "assist", label: "어시스트", title: "어시스트" },
  { key: "steal", label: "스틸", title: "스틸" },
  { key: "block", label: "블락", title: "블락" },
  { key: "foul", label: "파울", title: "파울" },
  { key: "turnover", label: "턴오버", title: "턴오버" },
];

const TEAM_LABEL = { A: "A팀", B: "B팀", C: "C팀" };
const QUARTERS = [1, 2, 3, 4];

// ── Helpers ──────────────────────────────────────────────────────────────────
function calcPts(row) {
  return (
    (Number(row.fg2_made) || 0) * 2 +
    (Number(row.fg3_made) || 0) * 3 +
    (Number(row.ft_made)  || 0)
  );
}

function emptyQuarterStat() {
  return {
    ft_made: 0,
    ft_miss: 0,
    fg2_made: 0,
    fg2_miss: 0,
    fg3_made: 0,
    fg3_miss: 0,
    o_rebound: 0,
    d_rebound: 0,
    assist: 0,
    steal: 0,
    block: 0,
    foul: 0,
    turnover: 0,
  };
}

function asInt(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function pctText(made, attempts) {
  if (attempts <= 0) return "-";
  return `${((made / attempts) * 100).toFixed(1)}%`;
}

function shootingRate(row, prefix) {
  const made = asInt(row[`${prefix}_made`]);
  const miss = asInt(row[`${prefix}_miss`]);
  const attempts = made + miss;
  return pctText(made, attempts);
}

function totalFgRate(row) {
  const made = asInt(row.fg2_made) + asInt(row.fg3_made);
  const attempts = made + asInt(row.fg2_miss) + asInt(row.fg3_miss);
  return pctText(made, attempts);
}

function renderEtcHeaderLabel(c) {
  if (c.key === "o_rebound") {
    return <>공격<br />리바운드</>;
  }
  if (c.key === "d_rebound") {
    return <>수비<br />리바운드</>;
  }
  return c.label;
}

function emptyRow(emp_id, team_code, name) {
  const quarters = {};
  QUARTERS.forEach((q) => {
    quarters[q] = emptyQuarterStat();
  });

  return {
    emp_id, team_code, name,
    participated: true,
    quarters,
  };
}

function quarterRow(row, quarterNo) {
  return row?.quarters?.[quarterNo] || emptyQuarterStat();
}

function calcQuarterPts(row, quarterNo) {
  const q = quarterRow(row, quarterNo);
  return calcPts(q);
}

function calcGamePts(row) {
  return QUARTERS.reduce((sum, q) => sum + calcQuarterPts(row, q), 0);
}

function shootingRateByQuarter(row, prefix, quarterNo) {
  return shootingRate(quarterRow(row, quarterNo), prefix);
}

function totalFgRateByQuarter(row, quarterNo) {
  return totalFgRate(quarterRow(row, quarterNo));
}

function sumQuarterField(row, field) {
  return QUARTERS.reduce((sum, q) => sum + asInt(quarterRow(row, q)[field]), 0);
}

function fromApiStat(s) {
  const base = emptyRow(s.emp_id, s.team_code, s.name);
  base.participated = Boolean(s.participated ?? true);
  base.quarters[1] = {
    ...base.quarters[1],
    ft_made: asInt(s.ft_made),
    ft_miss: Math.max(asInt(s.ft_attempted) - asInt(s.ft_made), 0),
    fg2_made: asInt(s.fg2_made),
    fg2_miss: Math.max(asInt(s.fg2_attempted) - asInt(s.fg2_made), 0),
    fg3_made: asInt(s.fg3_made),
    fg3_miss: Math.max(asInt(s.fg3_attempted) - asInt(s.fg3_made), 0),
    o_rebound: asInt(s.o_rebound),
    d_rebound: asInt(s.d_rebound),
    assist: asInt(s.assist),
    steal: asInt(s.steal),
    block: asInt(s.block),
    foul: asInt(s.foul),
    turnover: asInt(s.turnover),
  };

  return {
    ...base,
    id: s.id,
    updated_at: s.updated_at,
  };
}

function formatMetric(value, suffix = "", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatRatio(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(2);
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function ScoreSheetPage() {
  const [seasons,         setSeasons]         = useState([]);
  const [seasonId,        setSeasonId]        = useState(null);
  const [matches,         setMatches]         = useState([]);   // flat list
  const [matchId,         setMatchId]         = useState(null);
  const [teamAssignments, setTeamAssignments] = useState([]);
  const [statDraft,       setStatDraft]       = useState({});   // emp_id → row
  const [savingId,        setSavingId]        = useState(null);
  const [savedAt,         setSavedAt]         = useState({});   // emp_id → time string
  const [currentQuarter,  setCurrentQuarter]  = useState(1);
  const [error,           setError]           = useState("");
  const [analysis,        setAnalysis]        = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError,   setAnalysisError]   = useState("");

  // ── Initial load ───────────────────────────────────────────────────────────
  useEffect(() => {
    api.get("/api/league/admin/seasons")
      .then(r => {
        setSeasons(r.data);
        if (r.data.length > 0) setSeasonId(Number(r.data[0].id));
      })
      .catch(() => setError("시즌 목록을 불러올 수 없습니다."));

    api.get("/api/attendance/admin/team-assignments")
      .then(r => setTeamAssignments(r.data.items || []))
      .catch(() => {});
  }, []);

  // ── Load matches when season changes ──────────────────────────────────────
  useEffect(() => {
    if (!seasonId) { setMatches([]); setMatchId(null); return; }
    api.get(`/api/league/admin/seasons/${seasonId}/schedule`)
      .then(r => {
        const flat = (r.data.weeks || []).flatMap(w =>
          (w.matches || []).map(m => ({
            ...m,
            week_no: w.week_no,
            label: `${w.week_no}주차 · ${TEAM_LABEL[m.home_team] || m.home_team} vs ${TEAM_LABEL[m.away_team] || m.away_team}`,
          }))
        );
        setMatches(flat);
        setMatchId(flat.length > 0 ? flat[0].match_id : null);
      })
      .catch(() => {});
  }, [seasonId]);

  // ── Load existing stats when match changes ─────────────────────────────────
  useEffect(() => {
    if (!matchId) { setStatDraft({}); setSavedAt({}); return; }
    api.get(`/api/league/admin/matches/${matchId}/stats`)
      .then(r => {
        const map = {};
        (r.data || []).forEach(s => { map[s.emp_id] = fromApiStat(s); });
        setStatDraft(map);
        setSavedAt({});
      })
      .catch(() => { setStatDraft({}); setSavedAt({}); });
  }, [matchId]);

  useEffect(() => {
    if (!matchId) {
      setAnalysis(null);
      setAnalysisError("");
      return;
    }
    loadAnalysis(matchId);
  }, [matchId]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const selectedMatch = useMemo(
    () => matches.find(m => m.match_id === matchId),
    [matches, matchId]
  );

  // Players for each team in the selected match
  const teamPlayers = useMemo(() => {
    if (!selectedMatch) return { home: [], away: [] };
    return {
      home: teamAssignments.filter(p => p.team_code === selectedMatch.home_team),
      away: teamAssignments.filter(p => p.team_code === selectedMatch.away_team),
    };
  }, [selectedMatch, teamAssignments]);

  // Running team totals for display in section header
  function teamTotal(players, teamCode) {
    return players.reduce((sum, p) => {
      const row = statDraft[p.emp_id] || emptyRow(p.emp_id, teamCode, p.name);
      return sum + calcQuarterPts(row, currentQuarter);
    }, 0);
  }

  function teamGameTotal(players, teamCode) {
    return players.reduce((sum, p) => {
      const row = statDraft[p.emp_id] || emptyRow(p.emp_id, teamCode, p.name);
      return sum + calcGamePts(row);
    }, 0);
  }

  // ── State helpers ─────────────────────────────────────────────────────────
  function getRow(emp_id, team_code, name) {
    return statDraft[emp_id] || emptyRow(emp_id, team_code, name);
  }

  async function loadAnalysis(targetMatchId = matchId) {
    if (!targetMatchId) {
      setAnalysis(null);
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError("");
    try {
      const res = await api.get(`/api/league/admin/matches/${targetMatchId}/analysis`);
      setAnalysis(res.data);
    } catch (e) {
      setAnalysis(null);
      setAnalysisError(e.response?.data?.detail || "AI 평가를 불러올 수 없습니다.");
    } finally {
      setAnalysisLoading(false);
    }
  }

  function setField(emp_id, team_code, name, quarterNo, field, value) {
    setStatDraft(prev => {
      const row = prev[emp_id] || emptyRow(emp_id, team_code, name);
      return {
        ...prev,
        [emp_id]: {
          ...row,
          quarters: {
            ...row.quarters,
            [quarterNo]: {
              ...quarterRow(row, quarterNo),
              [field]: value,
            },
          },
        },
      };
    });
  }

  // ── Save handler ──────────────────────────────────────────────────────────
  async function handleSave(emp_id, team_code, name, options = {}) {
    const { refreshAnalysis = true } = options;
    if (!matchId) return;
    const row = getRow(emp_id, team_code, name);
    setSavingId(emp_id);
    setError("");
    try {
      const ftMade = sumQuarterField(row, "ft_made");
      const ftMiss = sumQuarterField(row, "ft_miss");
      const fg2Made = sumQuarterField(row, "fg2_made");
      const fg2Miss = sumQuarterField(row, "fg2_miss");
      const fg3Made = sumQuarterField(row, "fg3_made");
      const fg3Miss = sumQuarterField(row, "fg3_miss");

      const res = await api.post(`/api/league/admin/matches/${matchId}/stats/upsert`, {
        emp_id,
        team_code,
        name,
        participated:   row.participated,
        fg2_made:       fg2Made,
        fg2_attempted:  fg2Made + fg2Miss,
        fg3_made:       fg3Made,
        fg3_attempted:  fg3Made + fg3Miss,
        ft_made:        ftMade,
        ft_attempted:   ftMade + ftMiss,
        o_rebound:      sumQuarterField(row, "o_rebound"),
        d_rebound:      sumQuarterField(row, "d_rebound"),
        assist:         sumQuarterField(row, "assist"),
        steal:          sumQuarterField(row, "steal"),
        block:          sumQuarterField(row, "block"),
        foul:           sumQuarterField(row, "foul"),
        turnover:       sumQuarterField(row, "turnover"),
      });
      setStatDraft(prev => ({ ...prev, [emp_id]: { ...row, id: res.data.id, updated_at: res.data.updated_at } }));
      setSavedAt(prev => ({ ...prev, [emp_id]: new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }));
      if (refreshAnalysis) {
        await loadAnalysis(matchId);
      }
    } catch (e) {
      setError(`저장 실패 (${name}): ${e.response?.data?.detail || e.message}`);
    } finally {
      setSavingId(null);
    }
  }

  // ── Save All for a team ───────────────────────────────────────────────────
  async function handleSaveAll(players, team_code) {
    setError("");
    for (const p of players) {
      await handleSave(p.emp_id, team_code, p.name, { refreshAnalysis: false });
    }
  }

  async function handleSaveQuarterBanner() {
    if (!selectedMatch || savingId !== null) return;
    setError("");
    await handleSaveAll(teamPlayers.home, selectedMatch.home_team);
    await handleSaveAll(teamPlayers.away, selectedMatch.away_team);
    await loadAnalysis(matchId);
  }

  // ── Team table render ─────────────────────────────────────────────────────
  function renderTeamTable(players, team_code, quarterNo) {
    if (players.length === 0) {
      return (
        <div className="empty-state py-6">
          <p className="empty-state-text">편성된 선수가 없습니다.</p>
        </div>
      );
    }

    return (
      <div className="overflow-x-auto w-full">
        <table className="data-table" style={{ minWidth: 1320 }}>
          <thead>
            <tr>
              <th
                className="text-left"
                style={{ minWidth: 76, position: "sticky", left: 0, background: "#f8fafc", zIndex: 2, boxShadow: "2px 0 4px -2px rgba(0,0,0,.08)" }}
              >이름</th>
              <th style={{ minWidth: 42 }} title="출전여부">출전</th>
              {SHOOTING_GROUPS.map((g) => (
                <Fragment key={`head_${g.prefix}`}>
                  <th key={`${g.prefix}_made`} title={`${g.label} 성공`} style={{ minWidth: 46 }}>{g.label}↑</th>
                  <th key={`${g.prefix}_miss`} title={`${g.label} 실패`} style={{ minWidth: 46 }}>{g.label}↓</th>
                  <th key={`${g.prefix}_pct`} title={`${g.label} 성공률`} style={{ minWidth: 68, lineHeight: "1.1" }}>
                    {g.label}<br />성공률
                  </th>
                </Fragment>
              ))}
              <th title="2점+3점 통합 야투율" style={{ minWidth: 82 }}>통합야투율</th>
              {ETC_COLS.map(c => (
                <th key={c.key} title={c.title} style={{ minWidth: 50, lineHeight: "1.1" }}>{renderEtcHeaderLabel(c)}</th>
              ))}
              <th className="text-blue-600" style={{ minWidth: 42 }}>득점</th>
              <th style={{ minWidth: 52 }}>저장</th>
            </tr>
          </thead>
          <tbody>
            {players.map(p => {
              const row      = getRow(p.emp_id, team_code, p.name);
              const qRow     = quarterRow(row, quarterNo);
              const pts      = calcQuarterPts(row, quarterNo);
              const isSaving = savingId === p.emp_id;
              const saved    = savedAt[p.emp_id];
              const dimmed   = !row.participated;

              return (
                <tr key={p.emp_id} className={dimmed ? "opacity-40" : ""}>
                  {/* Sticky name column */}
                  <td
                    style={{
                      position: "sticky", left: 0, zIndex: 1,
                      background: dimmed ? "#f3f4f6" : "#ffffff",
                      boxShadow: "2px 0 4px -2px rgba(0,0,0,.08)",
                      minWidth: 76,
                    }}
                  >
                    <div className="text-xs font-semibold leading-tight">{p.name}</div>
                    {saved && <div className="text-[10px] text-green-500 leading-tight">{saved}</div>}
                  </td>

                  {/* Participation toggle */}
                  <td>
                    <input
                      type="checkbox"
                      checked={row.participated}
                      onChange={e => {
                        setStatDraft(prev => {
                          const current = prev[p.emp_id] || emptyRow(p.emp_id, team_code, p.name);
                          return { ...prev, [p.emp_id]: { ...current, participated: e.target.checked } };
                        });
                      }}
                      className="w-4 h-4 cursor-pointer"
                    />
                  </td>

                  {/* Shooting inputs + rates */}
                  {SHOOTING_GROUPS.map((g) => (
                    <Fragment key={`${p.emp_id}_${g.prefix}`}>
                      <td key={`${p.emp_id}_${g.prefix}_made`} className="p-1">
                        <input
                          type="number"
                          inputMode="numeric"
                          min={0}
                          max={99}
                          value={qRow[`${g.prefix}_made`]}
                          onChange={e => setField(p.emp_id, team_code, p.name, quarterNo, `${g.prefix}_made`, e.target.value)}
                          disabled={!row.participated}
                          className="field-input text-center"
                          style={{ width: 38, padding: "3px 2px", fontSize: 13, lineHeight: "1.2" }}
                        />
                      </td>
                      <td key={`${p.emp_id}_${g.prefix}_miss`} className="p-1">
                        <input
                          type="number"
                          inputMode="numeric"
                          min={0}
                          max={99}
                          value={qRow[`${g.prefix}_miss`]}
                          onChange={e => setField(p.emp_id, team_code, p.name, quarterNo, `${g.prefix}_miss`, e.target.value)}
                          disabled={!row.participated}
                          className="field-input text-center"
                          style={{ width: 38, padding: "3px 2px", fontSize: 13, lineHeight: "1.2" }}
                        />
                      </td>
                      <td key={`${p.emp_id}_${g.prefix}_pct`} className="tabular-nums text-[11px] text-gray-500 font-semibold">
                        {shootingRateByQuarter(row, g.prefix, quarterNo)}
                      </td>
                    </Fragment>
                  ))}

                  <td className="tabular-nums text-[11px] text-indigo-600 font-semibold">{totalFgRateByQuarter(row, quarterNo)}</td>

                  {/* Other stat inputs */}
                  {ETC_COLS.map(c => (
                    <td key={`${p.emp_id}_${c.key}`} className="p-1">
                      <input
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={99}
                        value={qRow[c.key]}
                        onChange={e => setField(p.emp_id, team_code, p.name, quarterNo, c.key, e.target.value)}
                        disabled={!row.participated}
                        className="field-input text-center"
                        style={{ width: 38, padding: "3px 2px", fontSize: 13, lineHeight: "1.2" }}
                      />
                    </td>
                  ))}

                  {/* Calculated points */}
                  <td className="font-bold text-blue-600 tabular-nums">{pts}</td>

                  {/* Save button */}
                  <td>
                    <button
                      className="btn-secondary btn btn-sm"
                      onClick={() => handleSave(p.emp_id, team_code, p.name)}
                      disabled={isSaving}
                      style={{ padding: "3px 8px", fontSize: 12 }}
                    >
                      {isSaving ? "…" : "저장"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  function renderAnalysisSection(title, teams, players, isCumulative = false) {
    return (
      <div className="card p-4 space-y-4">
        <div>
          <p className="section-title">{title}</p>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          {teams.map((team) => (
            <div key={`${title}_${team.team_code}`} className="rounded-2xl border border-gray-200 bg-gray-50 p-4 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <p className="font-bold text-gray-900">{TEAM_LABEL[team.team_code] || `${team.team_code}팀`}</p>
                <div className="text-right text-xs text-gray-500">
                  {isCumulative ? `${team.games}경기 누적` : `${team.score}점`}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-700 md:grid-cols-4">
                <div className="rounded-xl bg-white px-3 py-2">야투율 {team.fg_pct}%</div>
                <div className="rounded-xl bg-white px-3 py-2">3점율 {team.fg3_pct == null ? "-" : `${team.fg3_pct}%`}</div>
                <div className="rounded-xl bg-white px-3 py-2">리바운드 {team.rebounds ?? team.avg_rebounds}</div>
                <div className="rounded-xl bg-white px-3 py-2">어시스트 {team.assist ?? team.avg_assist}</div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-slate-700 md:grid-cols-3 xl:grid-cols-5">
                <MetricInfoChip metricKey="margin" label="득점마진" value={team.margin == null ? "-" : `${team.margin > 0 ? "+" : ""}${team.margin}`} />
                <MetricInfoChip metricKey="off_rating" label="ORTG" value={formatMetric(team.off_rating)} />
                <MetricInfoChip metricKey="def_rating" label="DRTG" value={formatMetric(team.def_rating)} />
                <MetricInfoChip metricKey="net_rating" label="NET" value={team.net_rating == null ? "-" : `${team.net_rating > 0 ? "+" : ""}${formatMetric(team.net_rating)}`} />
                <MetricInfoChip metricKey="ast_to_ratio" label="AST/TO" value={formatRatio(team.ast_to_ratio)} />
                <MetricInfoChip metricKey="efg_pct" label="eFG" value={formatMetric(team.efg_pct, "%")} />
                <MetricInfoChip metricKey="ts_pct" label="TS" value={formatMetric(team.ts_pct, "%")} />
                <MetricInfoChip metricKey="rebound_rate" label="REB%" value={formatMetric(team.rebound_rate, "%")} />
                <MetricInfoChip metricKey="oreb_dreb_rate" label="OREB% / DREB%" value={`${formatMetric(team.oreb_rate, "%")} / ${formatMetric(team.dreb_rate, "%")}`} />
                <MetricInfoChip metricKey="fg3_pct" label="3P%" value={formatMetric(team.fg3_pct, "%")} />
              </div>
            </div>
          ))}
        </div>

        <div>
          <p className="text-sm font-bold text-gray-900 mb-3">주요 선수 지표</p>
          <div className="space-y-3">
            {players.map((player) => (
              <div key={`${title}_${player.emp_id}`} className="rounded-2xl border border-gray-200 p-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="font-semibold text-gray-900">{player.name} · {TEAM_LABEL[player.team_code] || `${player.team_code}팀`}</p>
                    <p className="text-xs text-gray-500">
                      {isCumulative ? `${player.games}경기 누적 · 평균 ${player.avg_points ?? player.points}점` : `${player.points}점 · 리바운드 ${player.rebounds} · 어시스트 ${player.assist}`}
                    </p>
                  </div>
                  <div className="text-sm font-bold text-emerald-700">임팩트 {player.impact_score}</div>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-slate-700 md:grid-cols-4">
                  <MetricInfoChip metricKey="efg_pct" label="eFG" value={formatMetric(player.efg_pct, "%")} />
                  <MetricInfoChip metricKey="ts_pct" label="TS" value={formatMetric(player.ts_pct, "%")} />
                  <MetricInfoChip metricKey="ast_to_ratio" label="AST/TO" value={formatRatio(player.ast_to_ratio)} />
                  <MetricInfoChip metricKey="turnover" label="턴오버" value={player.turnover} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="page-container space-y-4">
      {error && <div className="alert-error">{error}</div>}

      {/* ── Controls ──────────────────────────────────────────────────── */}
      <div className="card p-4">
        <div className="action-bar flex-wrap gap-3">
          <select
            className="field-select"
            style={{ minWidth: 180 }}
            value={seasonId || ""}
            onChange={e => {
              setSeasonId(Number(e.target.value));
              setMatchId(null);
              setStatDraft({});
              setSavedAt({});
            }}
          >
            <option value="">시즌 선택</option>
            {seasons.map(s => (
              <option key={s.id} value={s.id}>{s.title} ({s.code})</option>
            ))}
          </select>

          <select
            className="field-select"
            style={{ minWidth: 240 }}
            value={matchId || ""}
            onChange={e => setMatchId(Number(e.target.value))}
            disabled={matches.length === 0}
          >
            <option value="">경기 선택</option>
            {matches.map(m => (
              <option key={m.match_id} value={m.match_id}>{m.label}</option>
            ))}
          </select>

          <div className="flex items-center gap-1 rounded-xl border border-gray-200 p-1">
            {QUARTERS.map((q) => (
              <button
                key={q}
                className={`btn btn-sm ${currentQuarter === q ? "btn-primary" : "btn-secondary"}`}
                style={{ minWidth: 64 }}
                onClick={() => setCurrentQuarter(q)}
                type="button"
              >
                {q}쿼터
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Score sheet ───────────────────────────────────────────────── */}
      {selectedMatch ? (
        <>
          <div className="card p-4 border-l-4 border-l-emerald-500 bg-emerald-50/70">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="section-title text-emerald-900">{currentQuarter}쿼터 통합 저장</p>
                <p className="text-sm font-semibold text-emerald-800">
                  {TEAM_LABEL[selectedMatch.home_team]} {teamTotal(teamPlayers.home, selectedMatch.home_team)}점 · {TEAM_LABEL[selectedMatch.away_team]} {teamTotal(teamPlayers.away, selectedMatch.away_team)}점
                </p>
                <p className="text-xs text-emerald-700 mt-1">현재 선택한 쿼터 기록을 저장하면 경기 지표와 누적 지표도 함께 갱신됩니다.</p>
              </div>
              <button
                className="btn-primary btn btn-sm"
                onClick={handleSaveQuarterBanner}
                disabled={savingId !== null}
                style={{ fontSize: 13, padding: "8px 14px", minWidth: 120 }}
              >
                {savingId !== null ? "저장 중..." : "저장 + 경기 지표"}
              </button>
            </div>
          </div>

          {/* Home team */}
          <div className="card overflow-hidden">
            <div className="p-3 border-b flex items-center justify-between bg-blue-50">
              <div>
                <span className="section-title">{TEAM_LABEL[selectedMatch.home_team]} (홈)</span>
                <span className="ml-3 text-sm font-bold text-blue-700">
                  {currentQuarter}쿼터 {teamTotal(teamPlayers.home, selectedMatch.home_team)}점 · 누적 {teamGameTotal(teamPlayers.home, selectedMatch.home_team)}점
                </span>
              </div>
            </div>
            {renderTeamTable(teamPlayers.home, selectedMatch.home_team, currentQuarter)}
          </div>

          {/* Away team */}
          <div className="card overflow-hidden">
            <div className="p-3 border-b flex items-center justify-between bg-red-50">
              <div>
                <span className="section-title">{TEAM_LABEL[selectedMatch.away_team]} (원정)</span>
                <span className="ml-3 text-sm font-bold text-red-700">
                  {currentQuarter}쿼터 {teamTotal(teamPlayers.away, selectedMatch.away_team)}점 · 누적 {teamGameTotal(teamPlayers.away, selectedMatch.away_team)}점
                </span>
              </div>
            </div>
            {renderTeamTable(teamPlayers.away, selectedMatch.away_team, currentQuarter)}
          </div>

          {/* Stat legend */}
          <div className="card p-3">
            <p className="text-xs text-gray-400 leading-relaxed">
              <span><b>기록 순서</b> 자유투 → 2점 → 3점</span>
              {" · "}
              <span><b>입력 방식</b> ↑성공, ↓실패</span>
              {" · "}
              <span><b>성공률</b> 자유투율/2점율/3점율 자동 계산</span>
              {" · "}
              <span><b>통합야투율</b> (2점성공+3점성공) / (2점시도+3점시도)</span>
              {" · "}
              <span><b>입력 단위</b> 현재 선택한 쿼터</span>
              {" · "}
              <span><b>저장 방식</b> 1~4쿼터 합산 저장</span>
              {" · "}
              <span><b>득점</b> 2점↑×2 + 3점↑×3 + 자유투↑</span>
            </p>
          </div>

          <div className="space-y-4">
            <div className="card p-4 bg-slate-50 border border-slate-200">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="section-title">경기 지표 분석</p>
                  <p className="text-sm text-gray-600 mt-1">기록 저장 데이터를 기준으로 팀 지표와 누적 지표를 자동 계산합니다.</p>
                </div>
                {analysisLoading && <span className="text-sm font-semibold text-emerald-700">지표 갱신 중...</span>}
              </div>
              {analysisError && <p className="text-sm text-red-600 mt-3">{analysisError}</p>}
              {!analysisLoading && !analysisError && !analysis?.match_analysis && (
                <p className="text-sm text-gray-500 mt-3">선수 기록을 저장하면 해당 경기 지표가 생성됩니다.</p>
              )}
            </div>

            {analysis?.match_analysis && renderAnalysisSection(
              `${analysis.match_analysis.week_no}주차 ${analysis.match_analysis.match_order}경기 평가`,
              analysis.match_analysis.teams,
              analysis.match_analysis.top_players,
              false,
            )}

            {analysis?.cumulative_analysis && renderAnalysisSection(
              `${analysis.cumulative_analysis.completed_matches}경기 누적 평가`,
              analysis.cumulative_analysis.teams,
              analysis.cumulative_analysis.top_players,
              true,
            )}
          </div>
        </>
      ) : (
        seasons.length > 0 && (
          <div className="card empty-state py-12">
            <p className="empty-state-text">시즌과 경기를 선택해주세요.</p>
          </div>
        )
      )}
    </div>
  );
}
