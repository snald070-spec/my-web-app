import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import MetricInfoChip from "../components/MetricInfoChip";

const TEAM_LABEL = { A: "A팀", B: "B팀", C: "C팀" };

function formatMetric(value, suffix = "", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatRatio(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(2);
}

function formatShootingPct(made, attempted) {
  const m = Number(made || 0);
  const a = Number(attempted || 0);
  if (a <= 0) return "-";
  return `${((m / a) * 100).toFixed(1)}%`;
}

function TeamTable({ title, players = [] }) {
  if (players.length === 0) {
    return (
      <div className="card p-6">
        <p className="text-sm text-gray-500">저장된 선수 기록이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
        <p className="section-title">{title}</p>
        <span className="text-xs text-gray-500">경기 합산 기록</span>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table scoresheet-team-table" style={{ minWidth: 1180 }}>
          <thead>
            <tr>
              <th rowSpan={2} className="text-left whitespace-nowrap">이름</th>
              <th rowSpan={2}>출전</th>
              <th rowSpan={2} className="text-blue-600">득점</th>
              <th colSpan={2}>자유투</th>
              <th colSpan={2}>2점</th>
              <th colSpan={2}>3점</th>
              <th rowSpan={2}>종합 야투율</th>
              <th rowSpan={2}>리바운드</th>
              <th rowSpan={2}>어시스트</th>
              <th rowSpan={2}>스틸</th>
              <th rowSpan={2}>블록</th>
              <th rowSpan={2}>파울</th>
              <th rowSpan={2}>턴오버</th>
            </tr>
            <tr>
              <th>
                <span className="hidden md:inline">성공/시도</span>
                <span className="md:hidden">M/A</span>
              </th>
              <th>성공률</th>
              <th>
                <span className="hidden md:inline">성공/시도</span>
                <span className="md:hidden">M/A</span>
              </th>
              <th>성공률</th>
              <th>
                <span className="hidden md:inline">성공/시도</span>
                <span className="md:hidden">M/A</span>
              </th>
              <th>성공률</th>
            </tr>
          </thead>
          <tbody>
            {players.map((player) => (
              <tr key={player.emp_id}>
                <td className="text-left font-semibold text-gray-800 whitespace-nowrap">{player.name}</td>
                <td>
                  <span className="hidden sm:inline">{player.participated ? "출전" : "미출전"}</span>
                  <span className="sm:hidden">{player.participated ? "출" : "미"}</span>
                </td>
                <td className="font-bold text-blue-600">{player.total_points}</td>
                <td>{player.ft_made}/{player.ft_attempted}</td>
                <td>{formatShootingPct(player.ft_made, player.ft_attempted)}</td>
                <td>{player.fg2_made}/{player.fg2_attempted}</td>
                <td>{formatShootingPct(player.fg2_made, player.fg2_attempted)}</td>
                <td>{player.fg3_made}/{player.fg3_attempted}</td>
                <td>{formatShootingPct(player.fg3_made, player.fg3_attempted)}</td>
                <td>{formatShootingPct(Number(player.fg2_made || 0) + Number(player.fg3_made || 0), Number(player.fg2_attempted || 0) + Number(player.fg3_attempted || 0))}</td>
                <td>{player.o_rebound + player.d_rebound}</td>
                <td>{player.assist}</td>
                <td>{player.steal}</td>
                <td>{player.block}</td>
                <td>{player.foul}</td>
                <td className="text-red-400">{player.turnover}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AnalysisBlock({ title, analysis }) {
  const teams = Array.isArray(analysis?.teams) ? analysis.teams : [];
  const topPlayers = Array.isArray(analysis?.top_players) ? analysis.top_players : [];
  if (!analysis || (teams.length === 0 && topPlayers.length === 0)) return null;

  return (
    <div className="card p-4 space-y-4">
      <div>
        <p className="section-title">{title}</p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {teams.map((team) => (
          <div key={`${title}_${team.team_code}`} className="rounded-2xl border border-gray-200 bg-gray-50 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="font-bold text-gray-900">{TEAM_LABEL[team.team_code] || `${team.team_code}팀`}</p>
              <span className="text-xs text-gray-500">{team.games ? `${team.games}경기 누적` : `${team.score}점`}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
              <MetricInfoChip metricKey="margin" label="득점마진" value={team.margin == null ? "-" : `${team.margin > 0 ? "+" : ""}${team.margin}`} />
              <MetricInfoChip metricKey="off_rating" label="ORTG" value={formatMetric(team.off_rating)} />
              <MetricInfoChip metricKey="def_rating" label="DRTG" value={formatMetric(team.def_rating)} />
              <MetricInfoChip metricKey="net_rating" label="NET" value={team.net_rating == null ? "-" : `${team.net_rating > 0 ? "+" : ""}${formatMetric(team.net_rating)}`} />
              <MetricInfoChip metricKey="ast_to_ratio" label="AST/TO" value={formatRatio(team.ast_to_ratio)} />
              <MetricInfoChip metricKey="efg_pct" label="eFG" value={formatMetric(team.efg_pct, "%")} />
              <MetricInfoChip metricKey="ts_pct" label="TS" value={formatMetric(team.ts_pct, "%")} />
              <MetricInfoChip metricKey="rebound_rate" label="REB%" value={formatMetric(team.rebound_rate, "%")} />
              <MetricInfoChip metricKey="fg3_pct" label="3P%" value={formatMetric(team.fg3_pct, "%")} />
              <MetricInfoChip metricKey="oreb_dreb_rate" label="OREB% / DREB%" value={`${formatMetric(team.oreb_rate, "%")} / ${formatMetric(team.dreb_rate, "%")}`} />
            </div>
          </div>
        ))}
      </div>

      <div>
        <p className="text-sm font-bold text-gray-900 mb-3">주요 선수 지표</p>
        <div className="space-y-3">
          {topPlayers.map((player) => (
            <div key={`${title}_${player.emp_id}`} className="rounded-2xl border border-gray-200 p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="font-semibold text-gray-900">{player.name} · {TEAM_LABEL[player.team_code] || `${player.team_code}팀`}</p>
                  <p className="text-xs text-gray-500">
                    {player.games ? `${player.games}경기 누적 · 평균 ${player.avg_points}점` : `${player.points}점 · 리바운드 ${player.rebounds} · 어시스트 ${player.assist}`}
                  </p>
                </div>
                <div className="text-sm font-bold text-emerald-700">임팩트 {player.impact_score}</div>
              </div>
              <div className="grid grid-cols-2 gap-2 mt-3 md:grid-cols-4">
                <MetricInfoChip metricKey="efg_pct" label="eFG" value={formatMetric(player.efg_pct, "%")} />
                <MetricInfoChip metricKey="ts_pct" label="TS" value={formatMetric(player.ts_pct, "%")} />
                <MetricInfoChip metricKey="ast_to_ratio" label="AST/TO" value={formatRatio(player.ast_to_ratio)} />
                <MetricInfoChip metricKey="turnover" label="TO" value={player.turnover} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ScoreSheetViewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [seasons, setSeasons] = useState([]);
  const [seasonId, setSeasonId] = useState(null);
  const [matches, setMatches] = useState([]);
  const [matchId, setMatchId] = useState(null);
  const [stats, setStats] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [catalogLoaded, setCatalogLoaded] = useState(false);

  useEffect(() => {
    api.get("/api/league/public/scoresheets/catalog")
      .then((res) => {
        const nextSeasons = Array.isArray(res.data) ? res.data : [];
        setSeasons(nextSeasons);
        const querySeasonId = Number(searchParams.get("seasonId") || 0);
        const firstRecordedSeasonId = Number(nextSeasons.find((season) => Number(season.recorded_match_count || 0) > 0)?.id || 0);
        const fallbackSeasonId = firstRecordedSeasonId || Number(nextSeasons[0]?.id || 0);
        const nextSeasonId = querySeasonId || fallbackSeasonId || null;
        setSeasonId(nextSeasonId);
        setCatalogLoaded(true);
      })
      .catch(() => {
        setCatalogLoaded(true);
        setError("기록지 조회용 시즌 목록을 불러올 수 없습니다.");
      });
  }, []);

  useEffect(() => {
    if (!catalogLoaded) return;
    if (!seasonId) {
      setMatches([]);
      setMatchId(null);
      return;
    }
    const season = seasons.find((item) => Number(item.id) === Number(seasonId));
    const seasonMatches = Array.isArray(season?.matches) ? season.matches : [];
    const flat = seasonMatches.map((match) => ({
      ...match,
      label: `${match.week_no}주차 · ${TEAM_LABEL[match.home_team]} vs ${TEAM_LABEL[match.away_team]}`,
    }));
    setMatches(flat);
    const queryMatchId = Number(searchParams.get("matchId") || 0);
    const recordedMatches = flat.filter((match) => match.has_stats);
    const matchPool = recordedMatches.length > 0 ? recordedMatches : flat;
    const nextMatchId = matchPool.some((match) => match.match_id === queryMatchId)
      ? queryMatchId
      : Number(matchPool[0]?.match_id || 0) || null;
    setMatchId(nextMatchId);
  }, [catalogLoaded, seasonId, seasons]);

  useEffect(() => {
    if (!matchId) {
      setStats([]);
      setAnalysis(null);
      return;
    }
    setLoading(true);
    setError("");
    Promise.all([
      api.get(`/api/league/public/matches/${matchId}/stats`),
      api.get(`/api/league/public/matches/${matchId}/analysis`),
    ])
      .then(([statsRes, analysisRes]) => {
        setStats(statsRes.data || []);
        setAnalysis(analysisRes.data || null);
      })
      .catch(() => {
        setStats([]);
        setAnalysis(null);
        setError("기록지 데이터를 불러올 수 없습니다.");
      })
      .finally(() => setLoading(false));
  }, [matchId]);

  useEffect(() => {
    const next = {};
    if (seasonId) next.seasonId = String(seasonId);
    if (matchId) next.matchId = String(matchId);
    const currentSeasonId = searchParams.get("seasonId") || "";
    const currentMatchId = searchParams.get("matchId") || "";
    const nextSeasonId = next.seasonId || "";
    const nextMatchId = next.matchId || "";
    if (currentSeasonId !== nextSeasonId || currentMatchId !== nextMatchId) {
      setSearchParams(next, { replace: true });
    }
  }, [seasonId, matchId]);

  const selectedMatch = useMemo(
    () => (Array.isArray(matches) ? matches.find((match) => match.match_id === matchId) : null),
    [matches, matchId]
  );

  const groupedStats = useMemo(() => {
    if (!selectedMatch) return { home: [], away: [] };
    return {
      home: stats.filter((row) => row.team_code === selectedMatch.home_team),
      away: stats.filter((row) => row.team_code === selectedMatch.away_team),
    };
  }, [stats, selectedMatch]);

  const recordedSeasonCount = useMemo(
    () => seasons.filter((season) => Number(season.recorded_match_count || 0) > 0).length,
    [seasons]
  );

  return (
    <div className="page-container space-y-4">
      {error && <div className="alert-error">{error}</div>}

      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <select
            className="field-select"
            style={{ minWidth: 180 }}
            value={seasonId || ""}
            onChange={(e) => setSeasonId(Number(e.target.value))}
          >
            <option value="">시즌 선택</option>
            {seasons.map((season) => (
              <option key={season.id} value={season.id}>{season.title} ({season.code})</option>
            ))}
          </select>

          <select
            className="field-select"
            style={{ minWidth: 280 }}
            value={matchId || ""}
            onChange={(e) => setMatchId(Number(e.target.value))}
            disabled={matches.length === 0}
          >
            <option value="">경기 선택</option>
            {matches.map((match) => (
              <option key={match.match_id} value={match.match_id}>
                {match.label}{match.has_stats ? "" : " · 기록 없음"}
              </option>
            ))}
          </select>

          <Link to="/league/view" className="btn-secondary btn btn-sm">리그전 현황으로 돌아가기</Link>
        </div>

        <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          현재 조회 화면은 저장된 경기 합산 기록을 보여줍니다. 쿼터별 입력값은 서버에 별도 보존되지 않아 조회 화면에는 경기 총합 기준으로 표시됩니다.
        </div>

        {recordedSeasonCount > 0 && (
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            기록이 저장된 시즌이 자동 우선 선택됩니다. 현재 샘플 시즌이 보이지 않으면 시즌 선택에서 기록이 있는 시즌을 선택하면 됩니다.
          </div>
        )}
      </div>

      {loading && <div className="card p-6 text-sm text-gray-500">기록지를 불러오는 중입니다.</div>}

      {!loading && matches.length === 0 && (
        <div className="card p-6 text-sm text-gray-500">선택한 시즌에 조회 가능한 경기 기록이 없습니다.</div>
      )}

      {!loading && selectedMatch && (
        <>
          <div className="card p-4 border-l-4 border-l-blue-500 bg-blue-50/70">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="section-title text-blue-900">{selectedMatch.week_no}주차 경기 기록지</p>
                <p className="text-sm font-semibold text-blue-800">
                  {TEAM_LABEL[selectedMatch.home_team]} vs {TEAM_LABEL[selectedMatch.away_team]}
                </p>
              </div>
              <div className="text-sm font-bold text-blue-700">
                {selectedMatch.home_score ?? "-"} : {selectedMatch.away_score ?? "-"}
              </div>
            </div>
          </div>

          <TeamTable title={`${TEAM_LABEL[selectedMatch.home_team]} 기록`} players={groupedStats.home} />
          <TeamTable title={`${TEAM_LABEL[selectedMatch.away_team]} 기록`} players={groupedStats.away} />

          <AnalysisBlock
            title="경기 분석"
            analysis={analysis?.match_analysis}
          />

          <AnalysisBlock
            title="누적 분석"
            analysis={analysis?.cumulative_analysis}
          />
        </>
      )}
    </div>
  );
}