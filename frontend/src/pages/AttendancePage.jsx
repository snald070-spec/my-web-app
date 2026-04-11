import { useEffect, useState } from "react";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import { getItems, getTotal } from "../utils/apiHelpers";

const responseLabel = {
  ATTEND: "참석",
  ABSENT: "불참",
  LATE: "지각",
};

export default function AttendancePage() {
  const { user } = useAuth();
  const isAdmin = ["MASTER", "ADMIN"].includes(user?.role);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  const [events, setEvents] = useState([]);
  const [mySummary, setMySummary] = useState(null);
  const [memberSummary, setMemberSummary] = useState([]);
  const [memberSummaryTotal, setMemberSummaryTotal] = useState(0);
  const [pendingReminders, setPendingReminders] = useState([]);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState(null);

  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newNote, setNewNote] = useState("");
  const [newVoteType, setNewVoteType] = useState("REST");
  const [newTargetTeam, setNewTargetTeam] = useState("A");

  async function loadAll() {
    setLoading(true);
    setErr("");
    try {
      const eventRes = await api.get("/api/attendance/events?skip=0&limit=200");
      setEvents(getItems(eventRes.data));

      if (isAdmin) {
        const memberRes = await api.get("/api/attendance/admin/member-summary?skip=0&limit=100");
        setMemberSummary(getItems(memberRes.data));
        setMemberSummaryTotal(getTotal(memberRes.data));

        const reminderRes = await api.get("/api/attendance/admin/reminders/pending");
        setPendingReminders(getItems(reminderRes.data));
      } else {
        const meRes = await api.get("/api/attendance/me/summary");
        setMySummary(meRes.data);
      }
    } catch (e) {
      setErr(e.response?.data?.detail || "출석 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, [isAdmin]);

  async function createEvent() {
    if (!newTitle.trim() || !newDate) {
      setErr("일정 제목과 날짜를 입력해주세요.");
      return;
    }
    setErr("");
    try {
      await api.post("/api/attendance/events", {
        title: newTitle,
        event_date: newDate,
        note: newNote,
        vote_type: newVoteType,
        target_team: newVoteType === "LEAGUE" ? newTargetTeam : null,
      });
      setNewTitle("");
      setNewDate("");
      setNewNote("");
      setSuccess("출석 투표 일정을 생성했습니다.");
      await loadAll();
    } catch (e) {
      setErr(e.response?.data?.detail || "일정 생성에 실패했습니다.");
    }
  }

  async function dispatchReminder(eventId, stage) {
    setErr("");
    try {
      await api.post("/api/attendance/admin/reminders/dispatch", {
        event_id: eventId,
        stage,
      });
      setSuccess("미투표 대상 알림을 기록했습니다.");
      await loadAll();
    } catch (e) {
      setErr(e.response?.data?.detail || "알림 처리에 실패했습니다.");
    }
  }

  async function changeStatus(eventId, status) {
    setErr("");
    try {
      await api.patch(`/api/attendance/events/${eventId}/status`, { status });
      setSuccess("일정 상태를 변경했습니다.");
      await loadAll();
    } catch (e) {
      setErr(e.response?.data?.detail || "상태 변경에 실패했습니다.");
    }
  }

  async function vote(eventId, response) {
    setErr("");
    try {
      await api.post(`/api/attendance/events/${eventId}/vote`, { response });
      setSuccess("출석 응답을 저장했습니다.");
      await loadAll();
    } catch (e) {
      setErr(e.response?.data?.detail || "출석 응답 저장에 실패했습니다.");
    }
  }

  async function openEventDetail(eventId) {
    setDetailModalOpen(true);
    setDetailLoading(true);
    setDetailData(null);
    try {
      const res = await api.get(`/api/attendance/events/${eventId}/vote-detail`);
      setDetailData(res.data || null);
    } catch (e) {
      setErr(e.response?.data?.detail || "투표 상세 정보를 불러오지 못했습니다.");
      setDetailModalOpen(false);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeEventDetail() {
    setDetailModalOpen(false);
    setDetailData(null);
  }

  useEffect(() => {
    if (!success) return undefined;
    const t = setTimeout(() => setSuccess(""), 1800);
    return () => clearTimeout(t);
  }, [success]);

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
        <h1 className="page-title">출석 투표 및 누적 출석</h1>
        <p className="page-subtitle">일정별 참석 투표와 회원 누적 출석 현황</p>
      </div>

      {err && <div className="alert-danger">{err}</div>}

      {isAdmin && (
        <>
          <div className="card p-4 space-y-2">
            <p className="section-title">출석 투표 일정 생성</p>
            <div className="action-bar">
              <input
                className="field-input"
                style={{ maxWidth: 260 }}
                placeholder="예: 수요일 정기 운동"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
              <select
                className="field-select"
                style={{ width: 180 }}
                value={newVoteType}
                onChange={(e) => setNewVoteType(e.target.value)}
              >
                <option value="REST">휴식기 출석 투표</option>
                <option value="LEAGUE">리그전 출석 투표</option>
              </select>
              {newVoteType === "LEAGUE" && (
                <select
                  className="field-select"
                  style={{ width: 120 }}
                  value={newTargetTeam}
                  onChange={(e) => setNewTargetTeam(e.target.value)}
                >
                  <option value="A">A팀</option>
                  <option value="B">B팀</option>
                  <option value="C">C팀</option>
                </select>
              )}
              <input
                className="field-input"
                style={{ width: 180 }}
                type="date"
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
              />
              <input
                className="field-input"
                style={{ maxWidth: 260 }}
                placeholder="메모(선택)"
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
              />
              <button className="btn-primary btn btn-sm" onClick={createEvent}>일정 생성</button>
            </div>
            {newVoteType === "REST" && (
              <p className="field-hint">휴식기 투표는 선택한 날짜가 속한 주차 기준으로 목요일 12:00 시작, 일요일 12:00 종료로 자동 설정됩니다.</p>
            )}
          </div>

          <div className="card overflow-hidden">
            <div className="p-4 border-b">
              <p className="section-title">미투표 알림 예정/발송</p>
              <p className="field-hint">휴식기/리그전 투표 모두 종료 1일 전(DAY_BEFORE), 1시간 전(HOUR_BEFORE) 미투표자만 대상으로 처리됩니다.</p>
            </div>
            <div className="overflow-x-auto w-full">
              <table className="data-table attendance-compact-table">
                <thead>
                  <tr>
                    <th>이벤트</th>
                    <th>유형</th>
                    <th>팀</th>
                    <th>단계</th>
                    <th>대상 수</th>
                    <th>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingReminders.length === 0 ? (
                    <tr><td colSpan={6}><div className="empty-state py-8"><p className="empty-state-text">현재 발송할 알림이 없습니다.</p></div></td></tr>
                  ) : pendingReminders.map((r) => (
                    <tr key={`${r.event_id}-${r.stage}`}>
                      <td>{r.title}</td>
                      <td>{r.vote_type === "LEAGUE" ? "리그전" : "휴식기"}</td>
                      <td>{r.target_team ? `${r.target_team}팀` : "전체"}</td>
                      <td>{r.stage === "DAY_BEFORE" ? "종료 1일 전" : "종료 1시간 전"}</td>
                      <td>{r.target_count}</td>
                      <td>
                        <button className="btn-secondary btn btn-sm" onClick={() => dispatchReminder(r.event_id, r.stage)}>알림 기록</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="p-4 border-b">
              <p className="section-title">회원 누적 출석 ({memberSummaryTotal}명)</p>
            </div>
            <div className="overflow-x-auto w-full">
              <table className="data-table attendance-compact-table">
                <thead>
                  <tr>
                    <th>이름</th>
                    <th>부서</th>
                    <th>참석</th>
                    <th>지각</th>
                    <th>불참</th>
                    <th>참석률</th>
                    <th>누적 점수</th>
                  </tr>
                </thead>
                <tbody>
                  {memberSummary.length === 0 ? (
                    <tr><td colSpan={7}><div className="empty-state py-8"><p className="empty-state-text">데이터가 없습니다.</p></div></td></tr>
                  ) : memberSummary.map((m) => (
                    <tr key={m.emp_id}>
                      <td>{m.name}</td>
                      <td>{m.department}</td>
                      <td>{m.attend_count}</td>
                      <td>{m.late_count}</td>
                      <td>{m.absent_count}</td>
                      <td>{Number(m.attendance_rate || 0).toFixed(1)}%</td>
                      <td>{Number(m.cumulative_score || 0).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!isAdmin && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="stat-card"><p className="stat-label">참석</p><p className="stat-value">{mySummary?.attend_count ?? 0}</p></div>
          <div className="stat-card"><p className="stat-label">지각</p><p className="stat-value">{mySummary?.late_count ?? 0}</p></div>
          <div className="stat-card"><p className="stat-label">불참</p><p className="stat-value">{mySummary?.absent_count ?? 0}</p></div>
          <div className="stat-card"><p className="stat-label">누적 점수</p><p className="stat-value">{Number(mySummary?.cumulative_score || 0).toFixed(1)}</p></div>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="p-4 border-b">
          <p className="section-title">출석 일정 목록</p>
        </div>
        <div className="overflow-x-auto w-full">
              <table className="data-table attendance-compact-table">
            <thead>
              <tr>
                <th>날짜</th>
                <th>제목</th>
                <th>유형</th>
                <th>상태</th>
                <th>대상</th>
                <th>참석/불참</th>
                <th>내 응답</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr><td colSpan={8}><div className="empty-state py-10"><p className="empty-state-text">등록된 일정이 없습니다.</p></div></td></tr>
              ) : events.map((e) => (
                <tr
                  key={e.id}
                  className="cursor-pointer"
                  onClick={() => openEventDetail(e.id)}
                >
                  <td>{e.event_date}</td>
                  <td>{e.title}</td>
                  <td>{e.vote_type === "LEAGUE" ? "리그전" : "휴식기"}</td>
                  <td>{e.status === "OPEN" ? <span className="badge-green">진행중</span> : <span className="badge-gray">마감</span>}</td>
                  <td>{e.vote_type === "LEAGUE" ? `${e.target_team || "-"}팀` : "전체"}</td>
                  <td>{e.counts.ATTEND}/{e.counts.ABSENT}</td>
                  <td>{e.my_vote ? (responseLabel[e.my_vote] || e.my_vote) : "-"}</td>
                  <td>
                    {isAdmin ? (
                      <div className="flex gap-2" onClick={(event) => event.stopPropagation()}>
                        <button className="btn-secondary btn btn-sm" onClick={() => openEventDetail(e.id)}>상세</button>
                        {e.status === "OPEN" ? (
                          <button className="btn-secondary btn btn-sm" onClick={() => changeStatus(e.id, "CLOSED")}>마감</button>
                        ) : (
                          <button className="btn-secondary btn btn-sm" onClick={() => changeStatus(e.id, "OPEN")}>재오픈</button>
                        )}
                      </div>
                    ) : (
                      e.eligible ? (
                        <div className="flex gap-1" onClick={(event) => event.stopPropagation()}>
                          <button className="btn-secondary btn btn-sm" disabled={!e.can_vote} onClick={() => vote(e.id, "ATTEND")}>참석</button>
                          <button className="btn-secondary btn btn-sm" disabled={!e.can_vote} onClick={() => vote(e.id, "ABSENT")}>불참</button>
                        </div>
                      ) : (
                        <span className="badge-gray">투표 대상 아님 (결과 조회만 가능)</span>
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {detailModalOpen && (
        <div className="modal-overlay" onClick={closeEventDetail}>
          <div className="modal-panel max-w-4xl" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="modal-title">투표 상세</p>
                {detailData?.event && (
                  <p className="text-xs text-gray-500 mt-1">
                    {detailData.event.event_date} · {detailData.event.title}
                  </p>
                )}
              </div>
              <button className="btn-secondary btn btn-sm" onClick={closeEventDetail}>닫기</button>
            </div>
            <div className="modal-body space-y-4">
              {detailLoading ? (
                <div className="py-8 text-center"><span className="spinner" /></div>
              ) : detailData ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="stat-card"><p className="stat-label">투표 대상</p><p className="stat-value text-lg">{detailData.summary?.eligible_count ?? 0}명</p></div>
                    <div className="stat-card"><p className="stat-label">투표 완료</p><p className="stat-value text-lg">{detailData.summary?.voted_count ?? 0}명</p></div>
                    <div className="stat-card"><p className="stat-label">미투표</p><p className="stat-value text-lg">{detailData.summary?.pending_count ?? 0}명</p></div>
                  </div>
                  {detailData?.event?.vote_type === "LEAGUE" && (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="stat-card"><p className="stat-label">A팀 참석</p><p className="stat-value text-lg">{detailData.summary?.attend_by_team?.A ?? 0}명</p></div>
                      <div className="stat-card"><p className="stat-label">B팀 참석</p><p className="stat-value text-lg">{detailData.summary?.attend_by_team?.B ?? 0}명</p></div>
                      <div className="stat-card"><p className="stat-label">C팀 참석</p><p className="stat-value text-lg">{detailData.summary?.attend_by_team?.C ?? 0}명</p></div>
                    </div>
                  )}

                  <div className="card overflow-hidden">
                    <div className="p-4 border-b">
                      <p className="section-title">투표 완료 명단</p>
                    </div>
                    <div className="overflow-x-auto w-full">
                      <table className="data-table attendance-compact-table">
                        <thead>
                          <tr>
                            <th>이름</th>
                            <th>부서</th>
                            <th>리그 팀</th>
                            <th>응답</th>
                            <th>투표 시각</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(detailData.voted || []).length === 0 ? (
                            <tr><td colSpan={5}><div className="empty-state py-8"><p className="empty-state-text">아직 투표한 회원이 없습니다.</p></div></td></tr>
                          ) : (detailData.voted || []).map((row) => (
                            <tr key={`voted_${row.emp_id}`}>
                              <td>{row.name}</td>
                              <td>{row.department || "-"}</td>
                              <td>{row.league_team ? `${row.league_team}팀` : "-"}</td>
                              <td>{responseLabel[row.response] || row.response}</td>
                              <td>{row.voted_at ? String(row.voted_at).replace("T", " ") : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="card overflow-hidden">
                    <div className="p-4 border-b">
                      <p className="section-title">미투표 명단</p>
                    </div>
                    <div className="overflow-x-auto w-full">
                      <table className="data-table attendance-compact-table">
                        <thead>
                          <tr>
                            <th>이름</th>
                            <th>부서</th>
                            <th>리그 팀</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(detailData.pending || []).length === 0 ? (
                            <tr><td colSpan={3}><div className="empty-state py-8"><p className="empty-state-text">모든 대상자가 투표를 완료했습니다.</p></div></td></tr>
                          ) : (detailData.pending || []).map((row) => (
                            <tr key={`pending_${row.emp_id}`}>
                              <td>{row.name}</td>
                              <td>{row.department || "-"}</td>
                              <td>{row.league_team ? `${row.league_team}팀` : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div className="empty-state py-8"><p className="empty-state-text">상세 정보를 불러올 수 없습니다.</p></div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
