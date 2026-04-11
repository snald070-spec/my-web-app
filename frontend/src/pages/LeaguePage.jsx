import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

const TEAMS = ["A", "B", "C"];

function teamLabel(code) {
  return code ? `${code}팀` : "-";
}

function nextSeasonCode(seasons, year) {
  const prefix = `${year}-`;
  let maxSeq = 0;

  for (const season of seasons || []) {
    const code = String(season?.code || "").trim();
    if (!code.startsWith(prefix)) continue;
    const suffix = code.slice(prefix.length);
    if (!/^\d+$/.test(suffix)) continue;
    maxSeq = Math.max(maxSeq, Number(suffix));
  }

  return `${year}-${String(maxSeq + 1).padStart(2, "0")}`;
}

function toErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join(" / ");
  }

  if (detail && typeof detail === "object") {
    return detail.message || JSON.stringify(detail);
  }

  return error?.message || fallback;
}

export default function LeaguePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [seasons, setSeasons] = useState([]);
  const [seasonId, setSeasonId] = useState(null);
  const [schedule, setSchedule] = useState([]);
  const [standingsWeek, setStandingsWeek] = useState(1);
  const [standings, setStandings] = useState([]);
  const [teamAssignments, setTeamAssignments] = useState([]);
  const [tradeProposals, setTradeProposals] = useState([]);
  const [tradeWindow, setTradeWindow] = useState(null);

  const [newTotalWeeks, setNewTotalWeeks] = useState(8);
  const [newStartDate, setNewStartDate] = useState("");

  const [protectedDraft, setProtectedDraft] = useState({ A: "", B: "", C: "" });
  const [tradeForm, setTradeForm] = useState({
    proposer_team: "A",
    partner_team: "B",
    proposer_out_emp_id: "",
    partner_out_emp_id: "",
    note: "",
  });

  const [matchEdits, setMatchEdits] = useState({});

  const currentSeason = useMemo(
    () => seasons.find((s) => String(s.id) === String(seasonId)) || null,
    [seasons, seasonId]
  );

  async function loadSeasons(selectLatest = false) {
    const { data } = await api.get("/api/league/admin/seasons");
    const rows = Array.isArray(data) ? data : [];
    setSeasons(rows);

    if (rows.length === 0) {
      setSeasonId(null);
      setTradeWindow(null);
      return;
    }

    if (selectLatest || !seasonId || !rows.some((r) => String(r.id) === String(seasonId))) {
      const latest = rows[0];
      setSeasonId(Number(latest.id));
      setStandingsWeek(1);
      setTradeWindow(null);
    }
  }

  async function loadSeasonDetail(targetSeasonId, weekNo = standingsWeek, refresh = false) {
    if (!targetSeasonId) return;

    const [scheduleRes, standingsRes, proposalsRes] = await Promise.all([
      api.get(`/api/league/admin/seasons/${targetSeasonId}/schedule`),
      api.get(`/api/league/admin/seasons/${targetSeasonId}/standings?week_no=${weekNo}&refresh=${refresh ? "true" : "false"}`),
      api.get(`/api/league/admin/seasons/${targetSeasonId}/trade-proposals`),
    ]);

    setSchedule(scheduleRes.data?.weeks || []);
    setStandings(standingsRes.data?.rows || []);
    setTradeProposals(Array.isArray(proposalsRes.data) ? proposalsRes.data : []);
  }

  async function loadTeamAssignments() {
    const { data } = await api.get("/api/attendance/admin/team-assignments");
    setTeamAssignments(Array.isArray(data?.items) ? data.items : []);
  }

  async function initializePage() {
    setLoading(true);
    setError("");
    try {
      await Promise.all([loadSeasons(false), loadTeamAssignments()]);
    } catch (e) {
      setError(toErrorMessage(e, "리그전 데이터를 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    initializePage();
  }, []);

  useEffect(() => {
    if (!seasonId) {
      setSchedule([]);
      setStandings([]);
      setTradeWindow(null);
      return;
    }

    setError("");
    loadSeasonDetail(seasonId, standingsWeek, false).catch((e) => {
      setError(toErrorMessage(e, "시즌 상세 조회에 실패했습니다."));
    });
  }, [seasonId, standingsWeek]);

  useEffect(() => {
    if (!success) return undefined;
    const t = setTimeout(() => setSuccess(""), 1800);
    return () => clearTimeout(t);
  }, [success]);

  function getEdit(matchId) {
    return matchEdits[matchId] || {
      status: "FINAL",
      home_score: "",
      away_score: "",
      forfeited_team: "",
      note: "",
    };
  }

  function setEdit(matchId, patch) {
    setMatchEdits((prev) => ({
      ...prev,
      [matchId]: {
        ...getEdit(matchId),
        ...patch,
      },
    }));
  }

  async function handleCreateSeason() {
    const weeks = Number(newTotalWeeks);
    if (!Number.isFinite(weeks) || weeks < 1 || weeks > 30) {
      setError("총 주차는 1~30 사이 정수여야 합니다.");
      return;
    }

    setError("");
    try {
      const clientYear = new Date().getFullYear();
      const derivedCode = nextSeasonCode(seasons, clientYear);
      const { data } = await api.post("/api/league/admin/seasons", {
        code: derivedCode,
        title: derivedCode,
        total_weeks: weeks,
        client_year: clientYear,
        start_date: newStartDate || null,
      });

      setNewTotalWeeks(8);
      setNewStartDate("");
      await loadSeasons(true);
      setSuccess("시즌이 생성되었습니다.");
      if (data?.season_id) {
        navigate(`/league/draft?seasonId=${data.season_id}`);
      }
    } catch (e) {
      setError(toErrorMessage(e, "시즌 생성에 실패했습니다."));
    }
  }

  async function handleSyncSchedule() {
    if (!seasonId) return;
    setError("");
    try {
      await api.post(`/api/league/admin/seasons/${seasonId}/schedule/sync`);
      await loadSeasonDetail(seasonId, standingsWeek, false);
      setSuccess("시즌 스케줄을 동기화했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "스케줄 동기화에 실패했습니다."));
    }
  }

  async function handleRefreshStandings() {
    if (!seasonId) return;
    setError("");
    try {
      await loadSeasonDetail(seasonId, standingsWeek, true);
      setSuccess("순위를 재계산했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "순위 재계산에 실패했습니다."));
    }
  }

  async function handleSaveMatchResult(matchId) {
    const edit = getEdit(matchId);
    setError("");

    try {
      if (edit.home_score === "" || edit.away_score === "") {
        setError("홈/원정 점수를 모두 입력해주세요.");
        return;
      }
      await api.post(`/api/league/admin/matches/${matchId}/result`, {
        status: "FINAL",
        home_score: Number(edit.home_score),
        away_score: Number(edit.away_score),
        note: edit.note || null,
      });

      await loadSeasonDetail(seasonId, standingsWeek, false);
      setSuccess("경기 결과를 저장했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "경기 결과 저장에 실패했습니다."));
    }
  }

  async function handleEvaluateTradeWindow() {
    if (!seasonId) return;
    setError("");
    try {
      const { data } = await api.post(`/api/league/admin/seasons/${seasonId}/trade-window/evaluate`, { week_no: 3 });
      setTradeWindow(data);
      await loadSeasonDetail(seasonId, standingsWeek, false);
      setSuccess("3주차 트레이드 윈도우를 평가했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "트레이드 윈도우 평가에 실패했습니다."));
    }
  }

  async function handleSetWaive(waived) {
    if (!seasonId) return;
    setError("");
    try {
      const { data } = await api.post(`/api/league/admin/seasons/${seasonId}/trade-window/waive`, {
        waived,
      });
      setTradeWindow(data);
      setSuccess(waived ? "트레이드권 포기를 반영했습니다." : "트레이드권 포기를 해제했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "트레이드 포기 설정에 실패했습니다."));
    }
  }

  async function handleSaveProtected(teamCode) {
    if (!seasonId) return;
    const raw = String(protectedDraft[teamCode] || "");
    const empIds = raw
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);

    setError("");
    try {
      await api.post(`/api/league/admin/seasons/${seasonId}/trade-protected`, {
        team_code: teamCode,
        emp_ids: empIds,
        week_no: 3,
      });
      setSuccess(`${teamLabel(teamCode)} 보호선수를 저장했습니다.`);
    } catch (e) {
      setError(toErrorMessage(e, "보호선수 저장에 실패했습니다."));
    }
  }

  async function handleCreateTradeProposal() {
    if (!seasonId) return;
    if (tradeForm.proposer_team === tradeForm.partner_team) {
      setError("제안팀과 상대팀은 달라야 합니다.");
      return;
    }
    if (!tradeForm.proposer_out_emp_id || !tradeForm.partner_out_emp_id) {
      setError("양 팀의 대상 선수를 선택해주세요.");
      return;
    }

    setError("");
    try {
      await api.post(`/api/league/admin/seasons/${seasonId}/trade-proposals`, {
        ...tradeForm,
      });
      await loadSeasonDetail(seasonId, standingsWeek, false);
      setSuccess("트레이드 제안을 생성했습니다.");
      setTradeForm((prev) => ({
        ...prev,
        proposer_out_emp_id: "",
        partner_out_emp_id: "",
        note: "",
      }));
    } catch (e) {
      setError(toErrorMessage(e, "트레이드 제안 생성에 실패했습니다."));
    }
  }

  async function handleTradeDecision(proposalId, approve) {
    setError("");
    try {
      await api.post(`/api/league/admin/trade-proposals/${proposalId}/decision`, {
        approve,
      });
      await loadSeasonDetail(seasonId, standingsWeek, false);
      setSuccess(approve ? "트레이드를 승인/실행했습니다." : "트레이드 제안을 반려했습니다.");
    } catch (e) {
      setError(toErrorMessage(e, "트레이드 처리에 실패했습니다."));
    }
  }

  const membersByTeam = useMemo(() => {
    const grouped = { A: [], B: [], C: [] };
    for (const row of teamAssignments) {
      if (row.team_code && grouped[row.team_code]) {
        grouped[row.team_code].push(row);
      }
    }
    return grouped;
  }, [teamAssignments]);

  if (loading) {
    return (
      <div className="page-container">
        <div className="card p-6"><span className="spinner" /></div>
      </div>
    );
  }

  return (
    <div className="page-container">
      {success && <div className="fixed right-4 top-4 z-[70] alert-success shadow-lg">{success}</div>}
      <div>
        <h1 className="page-title">리그전 운영</h1>
        <p className="page-subtitle">시즌 생성, 주차 스케줄/결과 입력, 순위 재계산</p>
      </div>

      {error && <div className="alert-danger">{error}</div>}

      <div className="card p-4 space-y-3">
        <p className="section-title">시즌 생성</p>
        <div className="action-bar">
          <span className="hidden sm:inline text-xs text-gray-500">코드와 시즌명은 휴대폰 시간 기준으로 자동 배정 (예: 2026-01, 2026-02)</span>
          <input
            className="field-input"
            style={{ width: 100 }}
            type="number"
            min={1}
            max={30}
            value={newTotalWeeks}
            onChange={(e) => setNewTotalWeeks(e.target.value)}
          />
          <input
            className="field-input"
            style={{ width: 170 }}
            type="date"
            value={newStartDate}
            onChange={(e) => setNewStartDate(e.target.value)}
          />
          <button className="btn-primary btn btn-sm" onClick={handleCreateSeason}>시즌 생성</button>
        </div>
      </div>

      <div className="card p-4 space-y-3">
        <div className="space-y-2">
          <div className="action-bar">
            <select
              className="field-select flex-1"
              style={{ minWidth: 0 }}
              value={seasonId || ""}
              onChange={(e) => {
                setSeasonId(e.target.value ? Number(e.target.value) : null);
                setStandingsWeek(1);
                setTradeWindow(null);
              }}
            >
              <option value="">시즌 선택</option>
              {seasons.map((s) => (
                <option key={s.id} value={s.id}>{s.code} | {s.title}</option>
              ))}
            </select>
            <button className="btn-secondary btn btn-sm whitespace-nowrap" disabled={!seasonId} onClick={handleSyncSchedule}>스케줄 동기화</button>
          </div>
          <div className="action-bar">
            <select
              className="field-select"
              style={{ width: 120 }}
              value={standingsWeek}
              onChange={(e) => setStandingsWeek(Number(e.target.value))}
              disabled={!currentSeason}
            >
              {Array.from({ length: Number(currentSeason?.total_weeks || 1) }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n}주차</option>
              ))}
            </select>
            <button className="btn-secondary btn btn-sm whitespace-nowrap" disabled={!seasonId} onClick={handleRefreshStandings}>순위 재계산</button>
          </div>
        </div>
      </div>

      <div className="card p-4 space-y-4">
        <p className="section-title">3주차 트레이드 윈도우</p>
        <div className="action-bar">
          <button className="btn-secondary btn btn-sm" disabled={!seasonId} onClick={handleEvaluateTradeWindow}>윈도우 평가</button>
          <button className="btn-secondary btn btn-sm" disabled={!seasonId} onClick={() => handleSetWaive(true)}>트레이드권 포기</button>
          <button className="btn-secondary btn btn-sm" disabled={!seasonId} onClick={() => handleSetWaive(false)}>포기 해제</button>
        </div>
        {tradeWindow && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="stat-card"><p className="stat-label">대상팀</p><p className="stat-value text-lg">{teamLabel(tradeWindow.eligible_team)}</p></div>
            <div className="stat-card"><p className="stat-label">1위 승점차</p><p className="stat-value text-lg">{tradeWindow.gap_with_leader ?? "-"}</p></div>
            <div className="stat-card"><p className="stat-label">윈도우 상태</p><p className="stat-value text-lg">{tradeWindow.window_status || "-"}</p></div>
          </div>
        )}
      </div>

      <div className="card p-4 space-y-3">
        <p className="section-title">보호선수 설정 (쉼표 구분)</p>
        {TEAMS.map((teamCode) => (
          <div key={teamCode} className="action-bar">
            <span className="badge-blue">{teamLabel(teamCode)}</span>
            <input
              className="field-input flex-1 min-w-0"
              style={{ minWidth: 0 }}
              placeholder="예: user01,user02"
              value={protectedDraft[teamCode]}
              onChange={(e) => setProtectedDraft((prev) => ({ ...prev, [teamCode]: e.target.value }))}
            />
            <button className="btn-secondary btn btn-sm" disabled={!seasonId} onClick={() => handleSaveProtected(teamCode)}>저장</button>
          </div>
        ))}
      </div>

      <div className="card p-4 space-y-3">
        <p className="section-title">트레이드 제안 생성</p>
        <div className="space-y-2">
          <div className="action-bar">
            <span className="text-xs text-gray-500 whitespace-nowrap">제안팀</span>
            <select
              className="field-select"
              style={{ width: 72 }}
              value={tradeForm.proposer_team}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, proposer_team: e.target.value, proposer_out_emp_id: "" }))}
            >
              {TEAMS.map((t) => <option key={t} value={t}>{t}팀</option>)}
            </select>
            <select
              className="field-select flex-1 min-w-0"
              style={{ minWidth: 0 }}
              value={tradeForm.proposer_out_emp_id}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, proposer_out_emp_id: e.target.value }))}
            >
              <option value="">선수 선택</option>
              {(membersByTeam[tradeForm.proposer_team] || []).map((m) => (
                <option key={m.emp_id} value={m.emp_id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div className="action-bar">
            <span className="text-xs text-gray-500 whitespace-nowrap">상대팀</span>
            <select
              className="field-select"
              style={{ width: 72 }}
              value={tradeForm.partner_team}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, partner_team: e.target.value, partner_out_emp_id: "" }))}
            >
              {TEAMS.map((t) => <option key={t} value={t}>{t}팀</option>)}
            </select>
            <select
              className="field-select flex-1 min-w-0"
              style={{ minWidth: 0 }}
              value={tradeForm.partner_out_emp_id}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, partner_out_emp_id: e.target.value }))}
            >
              <option value="">선수 선택</option>
              {(membersByTeam[tradeForm.partner_team] || []).map((m) => (
                <option key={m.emp_id} value={m.emp_id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div className="action-bar">
            <input
              className="field-input flex-1 min-w-0"
              style={{ minWidth: 0 }}
              placeholder="메모(선택)"
              value={tradeForm.note}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, note: e.target.value }))}
            />
            <button className="btn-primary btn btn-sm whitespace-nowrap" disabled={!seasonId} onClick={handleCreateTradeProposal}>제안 등록</button>
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b">
          <p className="section-title">트레이드 제안 목록</p>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>상태</th>
                <th>제안팀</th>
                <th>상대팀</th>
                <th>OUT (제안팀)</th>
                <th>OUT (상대팀)</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {tradeProposals.length === 0 ? (
                <tr><td colSpan={7}><div className="empty-state py-8"><p className="empty-state-text">트레이드 제안이 없습니다.</p></div></td></tr>
              ) : tradeProposals.map((p) => {
                const actionable = p.status === "SUBMITTED" || p.status === "DRAFT";
                return (
                  <tr key={p.proposal_id}>
                    <td>{p.proposal_id}</td>
                    <td>{p.status}</td>
                    <td>{teamLabel(p.proposer_team)}</td>
                    <td>{teamLabel(p.partner_team)}</td>
                    <td>{p.proposer_out_emp_id}</td>
                    <td>{p.partner_out_emp_id}</td>
                    <td>
                      <div className="flex justify-center gap-2">
                        <button className="btn-secondary btn btn-sm" disabled={!actionable} onClick={() => handleTradeDecision(p.proposal_id, true)}>승인</button>
                        <button className="btn-secondary btn btn-sm" disabled={!actionable} onClick={() => handleTradeDecision(p.proposal_id, false)}>반려</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b">
          <p className="section-title">{standingsWeek}주차 순위</p>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>팀</th>
                <th>경기</th>
                <th>승</th>
                <th>무</th>
                <th>패</th>
                <th>승점</th>
                <th>득실차</th>
              </tr>
            </thead>
            <tbody>
              {standings.length === 0 ? (
                <tr><td colSpan={8}><div className="empty-state py-8"><p className="empty-state-text">순위 데이터가 없습니다.</p></div></td></tr>
              ) : standings.map((s) => (
                <tr key={`${s.team_code}-${s.rank}`}>
                  <td>{s.rank}</td>
                  <td>{teamLabel(s.team_code)}</td>
                  <td>{s.played}</td>
                  <td>{s.wins}</td>
                  <td>{s.draws}</td>
                  <td>{s.losses}</td>
                  <td>{s.points}</td>
                  <td>{s.goal_diff}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b">
          <p className="section-title">주차 스케줄 및 결과 입력</p>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>주차</th>
                <th>순번</th>
                <th>대진</th>
                <th>결과 입력</th>
                <th>저장</th>
              </tr>
            </thead>
            <tbody>
              {schedule.length === 0 ? (
                <tr><td colSpan={5}><div className="empty-state py-8"><p className="empty-state-text">시즌을 선택해주세요.</p></div></td></tr>
              ) : schedule.flatMap((w) => w.matches.map((m) => ({ ...m, week_no: w.week_no }))).map((m) => {
                const edit = getEdit(m.match_id);
                return (
                  <tr key={m.match_id}>
                    <td>{m.week_no}</td>
                    <td>{m.order}</td>
                    <td className="whitespace-nowrap">{teamLabel(m.home_team)} vs {teamLabel(m.away_team)}</td>
                    <td>
                      <div className="flex flex-col items-center gap-1">
                        <input
                          className="field-input text-center"
                          style={{ width: 64 }}
                          type="number"
                          min={0}
                          placeholder="홈"
                          value={edit.home_score}
                          onChange={(e) => setEdit(m.match_id, { home_score: e.target.value })}
                        />
                        <input
                          className="field-input text-center"
                          style={{ width: 64 }}
                          type="number"
                          min={0}
                          placeholder="원정"
                          value={edit.away_score}
                          onChange={(e) => setEdit(m.match_id, { away_score: e.target.value })}
                        />
                      </div>
                    </td>
                    <td>
                      <button className="btn-secondary btn btn-sm" onClick={() => handleSaveMatchResult(m.match_id)}>저장</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
