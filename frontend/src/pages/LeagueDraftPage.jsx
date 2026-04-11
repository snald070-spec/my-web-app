import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import { useAuth } from "../context/AuthContext";

const TEAM_LABEL = { A: "A팀", B: "B팀", C: "C팀" };
const DRAFT_ORDER = ["A", "B", "C"];

function toErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

export default function LeagueDraftPage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [seasons, setSeasons] = useState([]);
  const [teamAssignments, setTeamAssignments] = useState([]);
  const [me, setMe] = useState({ is_admin: false, is_captain: false, team_code: null });
  const [draft, setDraft] = useState({
    status: "PLANNED",
    current_round: null,
    current_pick_no: null,
    current_turn_team: null,
    current_turn_order: [],
    history: [],
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [savingTeam, setSavingTeam] = useState("");
  const [starting, setStarting] = useState(false);
  const [picking, setPicking] = useState(false);

  const seasonId = Number(searchParams.get("seasonId") || 0) || null;
  const canManageCaptains = Boolean(me?.is_admin);
  const canDraft = Boolean(me?.is_admin || me?.is_captain);

  async function loadPageData() {
    setError("");
    const { data } = await api.get("/api/league/draft/board", {
      params: seasonId ? { season_id: seasonId } : undefined,
    });
    setSeasons(Array.isArray(data?.seasons) ? data.seasons : []);
    setTeamAssignments(Array.isArray(data?.items) ? data.items : []);
    setMe(data?.me || { is_admin: false, is_captain: false, team_code: null });
    setDraft(data?.draft || {
      status: "PLANNED",
      current_round: null,
      current_pick_no: null,
      current_turn_team: null,
      current_turn_order: [],
      history: [],
    });
  }

  useEffect(() => {
    let active = true;

    const run = async () => {
      try {
        await loadPageData();
      } catch (e) {
        if (!active) return;
        setError(toErrorMessage(e, "드래프트 화면 데이터를 불러오지 못했습니다."));
      }
    };

    run();
    const timer = setInterval(run, 3000);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [seasonId]);

  useEffect(() => {
    if (!success) return undefined;
    const timer = setTimeout(() => setSuccess(""), 1800);
    return () => clearTimeout(timer);
  }, [success]);

  const currentSeason = useMemo(() => {
    if (!seasonId) return seasons[0] || null;
    return seasons.find((row) => Number(row.id) === seasonId) || null;
  }, [seasons, seasonId]);

  const participantItems = useMemo(
    () => teamAssignments.filter((row) => row.is_participant),
    [teamAssignments]
  );

  const grouped = useMemo(() => {
    const rows = { A: [], B: [], C: [], unassigned: [] };
    for (const member of participantItems) {
      if (member.team_code && rows[member.team_code]) {
        rows[member.team_code].push(member);
      } else {
        rows.unassigned.push(member);
      }
    }
    return rows;
  }, [participantItems]);

  const draftPool = grouped.unassigned;
  const draftStarted = draft.status === "OPEN";
  const draftClosed = draft.status === "CLOSED";
  const currentRound = draft.current_round || null;
  const currentPickNo = draft.current_pick_no || null;
  const currentTurnTeam = draft.current_turn_team || null;
  const currentTurnOrder = Array.isArray(draft.current_turn_order) && draft.current_turn_order.length > 0
    ? draft.current_turn_order
    : DRAFT_ORDER;
  const draftHistory = Array.isArray(draft.history) ? draft.history : [];
  const isMyTurn = canDraft && draftStarted && currentTurnTeam && (me?.is_admin || me?.team_code === currentTurnTeam);

  async function toggleParticipant(empId, include) {
    if (!currentSeason?.id) return;
    setError("");
    try {
      await api.put(`/api/league/draft/participants/${empId}`, { include }, {
        params: { season_id: currentSeason.id },
      });
      await loadPageData();
    } catch (e) {
      setError(toErrorMessage(e, "드래프트 참여 인원 설정에 실패했습니다."));
    }
  }

  async function startDraft() {
    if (!currentSeason?.id) return;
    setStarting(true);
    setError("");
    try {
      await api.post("/api/league/draft/start", { season_id: currentSeason.id });
      await loadPageData();
      setSuccess("드래프트를 시작했습니다. 모든 회원 화면에 실시간 반영됩니다.");
    } catch (e) {
      setError(toErrorMessage(e, "드래프트 시작에 실패했습니다."));
    } finally {
      setStarting(false);
    }
  }

  async function pickPlayer(empId) {
    if (!draftStarted || picking) return;
    const target = draftPool.find((row) => row.emp_id === empId);
    if (!target) return;

    setPicking(true);
    setError("");
    try {
      await api.put(`/api/league/draft/assignments/${empId}`, {}, {
        params: currentSeason?.id ? { season_id: currentSeason.id } : undefined,
      });
      await loadPageData();
      setSuccess(`${target.name} 선수를 ${TEAM_LABEL[currentTurnTeam]}이(가) 지명했습니다.`);
    } catch (e) {
      setError(toErrorMessage(e, "드래프트 지명에 실패했습니다."));
    } finally {
      setPicking(false);
    }
  }

  async function assignCaptain(teamCode, empId) {
    if (!empId) return;
    setSavingTeam(teamCode);
    setError("");
    try {
      const currentCaptain = grouped[teamCode].find((row) => row.is_captain);
      if (currentCaptain?.emp_id === empId) {
        return;
      }
      if (currentCaptain && currentCaptain.emp_id !== empId) {
        await api.put(`/api/attendance/admin/team-assignments/${currentCaptain.emp_id}`, {
          team_code: teamCode,
          is_captain: false,
        });
      }

      await api.put(`/api/attendance/admin/team-assignments/${empId}`, {
        team_code: teamCode,
        is_captain: true,
      });
      await loadPageData();
      setSuccess(`${TEAM_LABEL[teamCode]} 팀장을 지정했습니다.`);
    } catch (e) {
      setError(toErrorMessage(e, "팀장 지정에 실패했습니다."));
    } finally {
      setSavingTeam("");
    }
  }

  function renderTeamCard(teamCode) {
    const players = grouped[teamCode];
    const captain = players.find((row) => row.is_captain) || null;
    const candidates = [...players, ...grouped.unassigned];

    return (
      <div key={teamCode} className="card overflow-hidden">
        <div className="p-4 border-b space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="section-title">{TEAM_LABEL[teamCode]}</p>
            <span className="field-hint">{players.length}명</span>
          </div>
          <div className="flex flex-col md:flex-row md:items-center gap-2">
            <div className="text-sm text-gray-600">
              현재 팀장: <span className="font-semibold text-gray-900">{captain ? captain.name : "미지정"}</span>
            </div>
            {canManageCaptains && (
              <select
                className="field-select"
                style={{ width: 220 }}
                value={captain?.emp_id || ""}
                onChange={(e) => assignCaptain(teamCode, e.target.value)}
                disabled={candidates.length === 0 || savingTeam === teamCode}
              >
                <option value="">팀장을 선택하세요</option>
                {candidates.map((player) => (
                  <option key={player.emp_id} value={player.emp_id}>
                    {player.name} ({player.emp_id}){player.team_code ? "" : " - 미배정"}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>사번</th>
                <th>부서</th>
                <th>팀장</th>
              </tr>
            </thead>
            <tbody>
              {players.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-state py-8"><p className="empty-state-text">배정된 인원이 없습니다.</p></div>
                  </td>
                </tr>
              ) : players.map((row) => (
                <tr key={row.emp_id}>
                  <td>{row.name}</td>
                  <td>{row.emp_id}</td>
                  <td>{row.department || "-"}</td>
                  <td>{row.is_captain ? "팀장" : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container space-y-4">
      {success && <div className="fixed right-4 top-4 z-[70] alert-success shadow-lg">{success}</div>}
      <div>
        <h1 className="page-title">리그 드래프트</h1>
        <p className="page-subtitle">시즌 생성 후 바로 드래프트 준비 상태를 확인하고 팀장을 지정하는 화면입니다.</p>
      </div>

      {error && <div className="alert-danger">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="stat-card">
          <p className="stat-label">현재 시즌</p>
          <p className="stat-value text-lg">{currentSeason?.code || "-"}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">시즌명</p>
          <p className="stat-value text-lg">{currentSeason?.title || "-"}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">총 주차</p>
          <p className="stat-value text-lg">{currentSeason?.total_weeks || "-"}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">시작일</p>
          <p className="stat-value text-lg">{currentSeason?.start_date ? String(currentSeason.start_date).slice(0, 10) : "-"}</p>
        </div>
      </div>

      <div className="card p-4 space-y-3">
        <p className="section-title">현재 팀 배정 현황</p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {Object.entries({ A: grouped.A.length, B: grouped.B.length, C: grouped.C.length }).map(([code, count]) => (
            <div key={code} className="stat-card">
              <p className="stat-label">{TEAM_LABEL[code]}</p>
              <p className="stat-value text-lg">{count}명</p>
            </div>
          ))}
          <div className="stat-card">
            <p className="stat-label">미배정</p>
            <p className="stat-value text-lg">{grouped.unassigned.length}명</p>
          </div>
        </div>
      </div>

      <div className="card p-4 space-y-3">
        <p className="section-title">드래프트 참여 현황</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="stat-card">
            <p className="stat-label">참여 인원</p>
            <p className="stat-value text-lg">{draft.participant_count ?? 0}명</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">미배정(참여자)</p>
            <p className="stat-value text-lg">{draft.unassigned_count ?? 0}명</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">자동 제외</p>
            <p className="stat-value text-lg">{teamAssignments.filter((m) => m.auto_excluded).length}명</p>
          </div>
        </div>
      </div>

      {canManageCaptains && (
        <div className="card overflow-hidden">
          <div className="p-4 border-b">
            <p className="section-title">드래프트 참여 인원 설정 (마스터/관리자)</p>
            <p className="field-hint">휴면/부상 회원은 자동 제외되어 선택할 수 없습니다.</p>
          </div>
          <div className="overflow-x-auto w-full">
            <table className="data-table">
              <thead>
                <tr>
                  <th>이름</th>
                  <th>사번</th>
                  <th>부서</th>
                  <th>상태</th>
                  <th>참여</th>
                </tr>
              </thead>
              <tbody>
                {teamAssignments.map((row) => (
                  <tr key={`participant-${row.emp_id}`}>
                    <td>{row.name}</td>
                    <td>{row.emp_id}</td>
                    <td>{row.department || "-"}</td>
                    <td>{row.member_status || "NORMAL"}</td>
                    <td>
                      {row.auto_excluded ? (
                        <span className="text-xs text-red-600 font-semibold">자동 제외</span>
                      ) : (
                        <input
                          type="checkbox"
                          checked={Boolean(row.is_participant)}
                          onChange={(e) => toggleParticipant(row.emp_id, e.target.checked)}
                          disabled={draftStarted || picking || starting}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card p-4 space-y-3">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <p className="section-title">드래프트 진행</p>
            <p className="field-hint">스네이크 방식: 1R A → B → C, 2R C → B → A, 3R A → B → C</p>
            {canDraft && !me?.is_admin && (
              <p className="field-hint">내 팀: {me?.team_code ? TEAM_LABEL[me.team_code] : "미지정"} (내 팀 턴에서만 지명 가능)</p>
            )}
            {!canDraft && <p className="field-hint">모든 회원은 드래프트 진행 현황을 실시간으로 볼 수 있습니다.</p>}
          </div>
          {canDraft && (
            <button
              className="btn-primary btn btn-sm"
              onClick={startDraft}
              disabled={(draft.participant_count || 0) === 0 || picking || starting || draftStarted || draftClosed}
            >
              {draftStarted ? "드래프트 진행 중" : draftClosed ? "드래프트 종료" : "드래프트 시작"}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="stat-card">
            <p className="stat-label">현재 라운드</p>
            <p className="stat-value text-lg">{draftStarted && currentRound ? `${currentRound}R` : "-"}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">현재 순번</p>
            <p className="stat-value text-lg">{draftStarted && currentPickNo ? `${currentPickNo}순위` : "-"}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">현재 지명 팀</p>
            <p className="stat-value text-lg">{draftStarted && currentTurnTeam ? TEAM_LABEL[currentTurnTeam] : "-"}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm text-gray-700">
          <span className="font-semibold">현재 라운드 순서:</span>
          {currentTurnOrder.map((code, idx) => (
            <span key={code} className={`px-2 py-1 rounded-lg border ${draftStarted && currentTurnTeam === code ? "bg-blue-50 border-blue-200 text-blue-700" : "bg-white border-gray-200"}`}>
              {idx + 1}. {TEAM_LABEL[code]}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {(["A", "B", "C"]).map((teamCode) => renderTeamCard(teamCode))}
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <p className="section-title">미배정 인원</p>
          <Link to="/attendance" className="btn-secondary btn btn-sm">팀 배정으로 이동</Link>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>사번</th>
                <th>부서</th>
                <th>지명</th>
              </tr>
            </thead>
            <tbody>
              {grouped.unassigned.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-state py-8"><p className="empty-state-text">미배정 인원이 없습니다.</p></div>
                  </td>
                </tr>
              ) : grouped.unassigned.map((row) => (
                <tr key={row.emp_id}>
                  <td>{row.name}</td>
                  <td>{row.emp_id}</td>
                  <td>{row.department || "-"}</td>
                  <td>
                    {canDraft ? (
                      <button
                        className="btn-secondary btn btn-sm"
                        onClick={() => pickPlayer(row.emp_id)}
                        disabled={!draftStarted || picking || draftPool.length === 0 || !isMyTurn}
                      >
                        {!draftStarted ? "대기" : isMyTurn ? `${TEAM_LABEL[currentTurnTeam]} 지명` : "턴 아님"}
                      </button>
                    ) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b">
          <p className="section-title">드래프트 로그</p>
        </div>
        <div className="overflow-x-auto w-full">
          <table className="data-table">
            <thead>
              <tr>
                <th>라운드</th>
                <th>순번</th>
                <th>팀</th>
                <th>선수</th>
                <th>사번</th>
              </tr>
            </thead>
            <tbody>
              {draftHistory.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-state py-8"><p className="empty-state-text">아직 지명 내역이 없습니다.</p></div>
                  </td>
                </tr>
              ) : draftHistory.map((row, idx) => (
                <tr key={`${row.emp_id}-${idx}`}>
                  <td>{row.round}R</td>
                  <td>{row.pick_no}순위</td>
                  <td>{TEAM_LABEL[row.team_code]}</td>
                  <td>{row.name}</td>
                  <td>{row.emp_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
