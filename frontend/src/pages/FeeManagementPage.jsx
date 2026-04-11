import { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import { getItems, getTotal } from "../utils/apiHelpers";

function currentYearMonth() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

const MEMBER_STATUS_OPTIONS = ["ALL", "NORMAL", "INJURED", "DORMANT"];
const PLAN_OPTIONS = ["MONTHLY", "SEMI_ANNUAL", "ANNUAL"];

const memberStatusLabel = {
  NORMAL: "일반",
  INJURED: "부상",
  DORMANT: "휴면",
};

const memberTypeLabel = {
  GENERAL: "일반",
  STUDENT: "학생",
};

const planLabel = {
  MONTHLY: "월납",
  SEMI_ANNUAL: "6개월",
  ANNUAL: "1년",
};

export default function FeeManagementPage() {
  const { user } = useAuth();
  const isAdmin = ["MASTER", "ADMIN"].includes(user?.role);

  const [activeTab, setActiveTab] = useState("status"); // "status" | "reminders"
  const [yearMonth, setYearMonth] = useState(currentYearMonth);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  // Member view
  const [myStatus, setMyStatus] = useState(null);
  const [myHistory, setMyHistory] = useState([]);

  // Admin view - Fee status
  const [keyword, setKeyword] = useState("");
  const [memberStatus, setMemberStatus] = useState("ALL");
  const [members, setMembers] = useState([]);
  const [memberTotal, setMemberTotal] = useState(0);
  const [adminSummary, setAdminSummary] = useState(null);
  const [matrixData, setMatrixData] = useState(null);
  const [savingId, setSavingId] = useState("");
  const [editById, setEditById] = useState({});
  const [planById, setPlanById] = useState({});

  // Admin view - Fee reminders
  const [reminderPeriod, setReminderPeriod] = useState("MONTH_END");
  const [reminderMemo, setReminderMemo] = useState("");
  const [targetsData, setTargetsData] = useState(null);
  const [reminderLogs, setReminderLogs] = useState([]);
  const [reminderLoading, setReminderLoading] = useState(false);
  const [effectiveness, setEffectiveness] = useState(null);
  const [depositLogs, setDepositLogs] = useState([]);
  const [depositKeyword, setDepositKeyword] = useState("");
  const [depositName, setDepositName] = useState("");
  const [depositAmount, setDepositAmount] = useState("");
  const [depositRawText, setDepositRawText] = useState("");
  const [depositAutoApply, setDepositAutoApply] = useState(true);
  const [depositLoading, setDepositLoading] = useState(false);

  const unpaidCount = useMemo(() => members.filter((m) => !m.is_paid).length, [members]);
  const unpaidMembers = useMemo(() => members.filter((m) => !m.is_paid), [members]);

  useEffect(() => {
    if (!success) return undefined;
    const t = setTimeout(() => setSuccess(""), 1800);
    return () => clearTimeout(t);
  }, [success]);

  // ===== 회비 관리 탭 로드 =====
  async function loadMemberView() {
    const [statusRes, historyRes] = await Promise.all([
      api.get(`/api/fees/me?year_month=${yearMonth}`),
      api.get("/api/fees/me/history?skip=0&limit=12"),
    ]);
    setMyStatus(statusRes.data);
    setMyHistory(getItems(historyRes.data));
  }

  async function loadAdminView() {
    const params = new URLSearchParams({
      year_month: yearMonth,
      skip: "0",
      limit: "200",
      keyword: keyword.trim(),
      member_status: memberStatus,
    });

    const [membersRes, summaryRes, matrixRes] = await Promise.all([
      api.get(`/api/fees/admin/members?${params.toString()}`),
      api.get(`/api/fees/admin/summary?year_month=${yearMonth}`),
      api.get(`/api/fees/admin/matrix?end_year_month=${yearMonth}&months=15`),
    ]);

    setMembers(getItems(membersRes.data));
    setMemberTotal(getTotal(membersRes.data));
    setAdminSummary(summaryRes.data);
    setMatrixData(matrixRes.data);

    const profileMap = {};
    const planMap = {};
    getItems(membersRes.data).forEach((m) => {
      profileMap[m.emp_id] = {
        membership_type: m.membership_type,
        member_status: m.member_status,
      };
      planMap[m.emp_id] = "MONTHLY";
    });
    setEditById(profileMap);
    setPlanById(planMap);
  }

  async function loadReminderLogs() {
    const { data } = await api.get("/api/fees/admin/reminders/log?skip=0&limit=20");
    setReminderLogs(getItems(data));
  }

  async function loadReminderTargets() {
    setErr("");
    try {
      const { data } = await api.get(
        `/api/fees/admin/reminders?year_month=${yearMonth}&period=${reminderPeriod}`,
      );
      setTargetsData(data);
    } catch (e) {
      setErr(e.response?.data?.detail || "알림 대상 조회에 실패했습니다.");
    }
  }

  async function loadEffectiveness() {
    try {
      const { data } = await api.get("/api/fees/admin/reminders/effectiveness");
      setEffectiveness(data);
    } catch (e) {
      console.error("효과 측정 실패:", e);
    }
  }

  async function loadDepositLogs() {
    const params = new URLSearchParams({
      skip: "0",
      limit: "20",
      keyword: depositKeyword.trim(),
    });
    const { data } = await api.get(`/api/fees/admin/deposits/log?${params.toString()}`);
    setDepositLogs(getItems(data));
  }

  async function loadAll() {
    setLoading(true);
    setErr("");
    try {
      if (isAdmin) {
        await loadAdminView();
        await loadReminderLogs();
        await loadDepositLogs();
      } else {
        await loadMemberView();
      }
    } catch (e) {
      setErr(e.response?.data?.detail || "회비 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, [isAdmin, yearMonth, keyword, memberStatus]);

  // ===== 회비 실시간 추적 (미납자 업데이트) =====
  async function checkUnpaidMembers() {
    if (!isAdmin || activeTab !== "status") return;
    try {
      const params = new URLSearchParams({
        year_month: yearMonth,
        skip: "0",
        limit: "200",
        keyword: keyword.trim(),
        member_status: memberStatus,
      });
      const { data } = await api.get(`/api/fees/admin/members?${params.toString()}`);
      setMembers(getItems(data));
    } catch (e) {
      console.error("미납자 체크 실패:", e);
    }
  }

  // 탭 전환 시 데이터 새로고침
  useEffect(() => {
    if (activeTab === "reminders" && isAdmin) {
      loadReminderLogs();
      loadEffectiveness();
      loadDepositLogs();
    } else if (activeTab === "status" && isAdmin) {
      checkUnpaidMembers();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === "reminders" && isAdmin) {
      loadDepositLogs();
    }
  }, [depositKeyword]);

  async function handleSaveProfile(empId) {
    const form = editById[empId];
    if (!form) return;

    setSavingId(empId);
    setErr("");
    try {
      await api.patch(`/api/fees/admin/members/${empId}/profile`, form);
      await loadAdminView();
      setSuccess("회원 설정을 저장했습니다.");
    } catch (e) {
      setErr(e.response?.data?.detail || "회원 설정 저장에 실패했습니다.");
    } finally {
      setSavingId("");
    }
  }

  async function handleMarkPaid(empId) {
    const plan = planById[empId] || "MONTHLY";
    setSavingId(empId);
    setErr("");
    try {
      await api.post(`/api/fees/admin/members/${empId}/mark-paid`, {
        year_month: yearMonth,
        plan_type: plan,
      });
      await loadAdminView();
      setSuccess("납부 완료로 체크했습니다.");
    } catch (e) {
      setErr(e.response?.data?.detail || "납부 체크에 실패했습니다.");
    } finally {
      setSavingId("");
    }
  }

  // ===== 알림 관련 함수 =====
  async function handleLogReminder() {
    setErr("");
    try {
      await api.post("/api/fees/admin/reminders/log", {
        year_month: yearMonth,
        period: reminderPeriod,
        memo: reminderMemo,
      });
      setReminderMemo("");
      await loadReminderLogs();
      setSuccess("알림 발송 기록을 저장했습니다.");
    } catch (e) {
      setErr(e.response?.data?.detail || "알림 기록 저장에 실패했습니다.");
    }
  }

  async function handleIngestDeposit() {
    setErr("");
    if (!depositName.trim()) {
      setErr("입금자 이름을 입력해주세요.");
      return;
    }
    const amount = Number(depositAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setErr("입금 금액을 올바르게 입력해주세요.");
      return;
    }

    setDepositLoading(true);
    try {
      const payload = {
        depositor_name: depositName.trim(),
        amount,
        year_month: yearMonth,
        source: "KOOKMINBANK_ALERT",
        bank_name: "국민은행",
        account_number: "331301-04-169767",
        account_holder: "박한올",
        raw_text: depositRawText.trim() || null,
        auto_apply: depositAutoApply,
      };
      const { data } = await api.post("/api/fees/admin/deposits/ingest", payload);

      if (data.duplicate) {
        setSuccess("이미 처리된 입금 이벤트입니다.");
      } else if (data.match_status === "APPLIED") {
        setSuccess("입금 알림이 자동으로 납부 반영되었습니다.");
      } else {
        setSuccess(`입금 이벤트 처리 완료: ${data.match_status}`);
      }

      setDepositRawText("");
      await Promise.all([loadDepositLogs(), loadAdminView()]);
    } catch (e) {
      setErr(e.response?.data?.detail || "입금 이벤트 처리에 실패했습니다.");
    } finally {
      setDepositLoading(false);
    }
  }

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

      <div className="flex flex-col gap-6">
        {/* 헤더 */}
        <div>
          <h1 className="page-title">회비 관리</h1>
          <p className="page-subtitle">월 회비: 일반 3만원, 학생 2만원, 일반 6개월 15만원, 1년 30만원</p>
        </div>

        {err && <div className="alert-danger">{err}</div>}

        {!isAdmin && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="stat-card">
                <p className="stat-label">회원 구분</p>
                <p className="stat-value">{memberTypeLabel[myStatus?.membership_type] || "-"}</p>
              </div>
              <div className="stat-card">
                <p className="stat-label">회원 상태</p>
                <p className="stat-value">{memberStatusLabel[myStatus?.member_status] || "-"}</p>
              </div>
              <div className="stat-card">
                <p className="stat-label">이번 달 납부 상태</p>
                <p className="stat-value">{myStatus?.is_paid ? "완료" : "미납"}</p>
              </div>
            </div>

            <div className="card p-4">
              <p className="text-sm text-gray-700">
                이번 달 기준 예상 회비는 <b>{Number(myStatus?.expected_monthly_amount || 0).toLocaleString("ko-KR")}원</b> 입니다.
              </p>
              <p className="text-xs text-gray-500 mt-2">
                실제 납부 반영은 운영진(관리자)이 수기 확인 후 체크합니다.
              </p>
            </div>

            <div className="card overflow-hidden">
              <div className="p-4 border-b">
                <p className="section-title">최근 납부 이력</p>
              </div>
              <div className="overflow-x-auto w-full">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>기준 월</th>
                      <th>납부 구분</th>
                      <th>커버 기간</th>
                      <th>금액</th>
                      <th>확인자</th>
                      <th>확인일</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myHistory.length === 0 ? (
                      <tr>
                        <td colSpan={6}>
                          <div className="empty-state py-10">
                            <p className="empty-state-text">납부 이력이 없습니다.</p>
                          </div>
                        </td>
                      </tr>
                    ) : myHistory.map((r) => (
                      <tr key={r.id}>
                        <td>{r.year_month}</td>
                        <td>{planLabel[r.plan_type] || r.plan_type}</td>
                        <td>{r.coverage_start_month} ~ {r.coverage_end_month}</td>
                        <td>{Number(r.paid_amount || 0).toLocaleString("ko-KR")}원</td>
                        <td>{r.marked_by}</td>
                        <td>{new Date(r.marked_at).toLocaleString("ko-KR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {isAdmin && (
          <>
            {/* 탭 네비게이션 */}
            <div className="flex gap-2 border-b">
              <button
                className={`px-4 py-3 font-semibold border-b-2 transition-colors ${
                  activeTab === "status"
                    ? "text-blue-600 border-blue-600"
                    : "text-gray-600 border-transparent hover:text-gray-900"
                }`}
                onClick={() => setActiveTab("status")}
              >
                회비 현황
              </button>
              <button
                className={`px-4 py-3 font-semibold border-b-2 transition-colors ${
                  activeTab === "reminders"
                    ? "text-blue-600 border-blue-600"
                    : "text-gray-600 border-transparent hover:text-gray-900"
                }`}
                onClick={() => setActiveTab("reminders")}
              >
                납부 알림 ({unpaidCount}명)
              </button>
            </div>

            {/* 회비 현황 탭 */}
            {activeTab === "status" && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="stat-card">
                    <p className="stat-label">대상 회원 수</p>
                    <p className="stat-value">{memberTotal.toLocaleString("ko-KR")}</p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">미납 인원</p>
                    <p className="stat-value text-red-600">{unpaidCount.toLocaleString("ko-KR")}</p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">납부 완료 인원</p>
                    <p className="stat-value text-green-600">{(memberTotal - unpaidCount).toLocaleString("ko-KR")}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="stat-card">
                    <p className="stat-label">납부율</p>
                    <p className="stat-value">{Number(adminSummary?.payment_rate || 0).toFixed(1)}%</p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">일반 회원(완료/전체)</p>
                    <p className="stat-value">
                      {(adminSummary?.by_membership_type?.GENERAL?.paid || 0).toLocaleString("ko-KR")}
                      /
                      {(adminSummary?.by_membership_type?.GENERAL?.total || 0).toLocaleString("ko-KR")}
                    </p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">학생 회원(완료/전체)</p>
                    <p className="stat-value">
                      {(adminSummary?.by_membership_type?.STUDENT?.paid || 0).toLocaleString("ko-KR")}
                      /
                      {(adminSummary?.by_membership_type?.STUDENT?.total || 0).toLocaleString("ko-KR")}
                    </p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">휴면 회원(미납/전체)</p>
                    <p className="stat-value">
                      {(adminSummary?.by_member_status?.DORMANT?.unpaid || 0).toLocaleString("ko-KR")}
                      /
                      {(adminSummary?.by_member_status?.DORMANT?.total || 0).toLocaleString("ko-KR")}
                    </p>
                  </div>
                </div>

                <div className="card overflow-hidden">
                  <div className="px-3 sm:px-4 py-3 border-b bg-gray-50 text-center">
                    <p className="text-xl font-bold text-gray-900">{matrixData?.title || "DRAW 회비 납부 현황"}</p>
                  </div>
                  <div className="px-3 sm:px-4 py-2 border-b text-center text-orange-600 font-semibold text-sm">
                    {matrixData?.banner || ""}
                  </div>
                  <div className="overflow-x-auto w-full">
                    <table className="data-table fee-matrix-table">
                      <thead>
                        <tr>
                          <th rowSpan={2}>이름</th>
                          {(matrixData?.year_groups || []).map((g, idx) => (
                            <th key={`${g.year}-${idx}`} colSpan={g.colspan} className="text-center">{g.year}년</th>
                          ))}
                        </tr>
                        <tr>
                          {(matrixData?.months || []).map((m) => (
                            <th key={m.key} className="text-center">{m.month}월</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(matrixData?.rows || []).map((r) => (
                          <tr key={r.emp_id}>
                            <td className="font-semibold text-gray-800">{r.name}</td>
                            {(r.cells || []).map((v, i) => (
                              <td key={`${r.emp_id}-${i}`} className="align-middle">
                                <div className="flex items-center justify-center">
                                  {v === "O" && <span className="text-red-500 font-bold">O</span>}
                                  {v === "X" && <span className="text-gray-900 font-bold">X</span>}
                                  {v === "휴면" && <span className="text-gray-900 font-bold">휴면</span>}
                                  {v === "부상" && <span className="text-gray-900 font-bold">부상</span>}
                                </div>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="card overflow-hidden">
                  <div className="p-4 border-b">
                    <p className="section-title">최근 6개월 납부 추이</p>
                  </div>
                  <div className="overflow-x-auto w-full">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>기준 월</th>
                          <th>전체</th>
                          <th>완료</th>
                          <th>미납</th>
                          <th>납부율</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(adminSummary?.monthly_trend || []).map((m) => (
                          <tr key={m.year_month}>
                            <td>{m.year_month}</td>
                            <td>{Number(m.total || 0).toLocaleString("ko-KR")}</td>
                            <td>{Number(m.paid || 0).toLocaleString("ko-KR")}</td>
                            <td>{Number(m.unpaid || 0).toLocaleString("ko-KR")}</td>
                            <td>{Number(m.payment_rate || 0).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="card p-4">
                  <div className="action-bar">
                    <input
                      className="field-input"
                      style={{ maxWidth: 280 }}
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                      placeholder="아이디/이름/부서 검색"
                    />
                    <select
                      className="field-select"
                      style={{ width: 160 }}
                      value={memberStatus}
                      onChange={(e) => setMemberStatus(e.target.value)}
                    >
                      {MEMBER_STATUS_OPTIONS.map((v) => (
                        <option key={v} value={v}>{v === "ALL" ? "전체 상태" : memberStatusLabel[v]}</option>
                      ))}
                    </select>
                    <button className="btn-secondary btn btn-sm" onClick={() => { setKeyword(""); setMemberStatus("ALL"); }}>
                      필터 초기화
                    </button>
                  </div>
                </div>

                <div className="card overflow-hidden">
                  <div className="overflow-x-auto w-full">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>아이디</th>
                          <th>이름</th>
                          <th>부서</th>
                          <th>회원 구분</th>
                          <th>회원 상태</th>
                          <th>월 기준 회비</th>
                          <th>이번 달 납부</th>
                          <th>납부 체크</th>
                          <th>저장</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.length === 0 ? (
                          <tr>
                            <td colSpan={9}>
                              <div className="empty-state py-10">
                                <p className="empty-state-text">조회 결과가 없습니다.</p>
                              </div>
                            </td>
                          </tr>
                        ) : members.map((m) => (
                          <tr key={m.emp_id}>
                            <td>{m.emp_id}</td>
                            <td>{m.name}</td>
                            <td>{m.department}</td>
                            <td>
                              <select
                                className="field-select"
                                value={editById[m.emp_id]?.membership_type || m.membership_type}
                                onChange={(e) => setEditById((prev) => ({
                                  ...prev,
                                  [m.emp_id]: {
                                    ...(prev[m.emp_id] || {}),
                                    membership_type: e.target.value,
                                    member_status: (prev[m.emp_id]?.member_status || m.member_status),
                                  },
                                }))}
                              >
                                <option value="GENERAL">일반</option>
                                <option value="STUDENT">학생</option>
                              </select>
                            </td>
                            <td>
                              <select
                                className="field-select"
                                value={editById[m.emp_id]?.member_status || m.member_status}
                                onChange={(e) => setEditById((prev) => ({
                                  ...prev,
                                  [m.emp_id]: {
                                    ...(prev[m.emp_id] || {}),
                                    membership_type: (prev[m.emp_id]?.membership_type || m.membership_type),
                                    member_status: e.target.value,
                                  },
                                }))}
                              >
                                <option value="NORMAL">일반</option>
                                <option value="INJURED">부상</option>
                                <option value="DORMANT">휴면</option>
                              </select>
                            </td>
                            <td>{Number(m.expected_monthly_amount || 0).toLocaleString("ko-KR")}원</td>
                            <td>
                              {m.is_paid
                                ? <span className="badge-green">완료</span>
                                : <span className="badge-red">미납</span>}
                            </td>
                            <td>
                              <div className="flex items-center justify-center gap-2">
                                <select
                                  className="field-select"
                                  style={{ width: 110 }}
                                  value={planById[m.emp_id] || "MONTHLY"}
                                  onChange={(e) => setPlanById((prev) => ({ ...prev, [m.emp_id]: e.target.value }))}
                                >
                                  {PLAN_OPTIONS.map((p) => (
                                    <option key={p} value={p}>{planLabel[p]}</option>
                                  ))}
                                </select>
                                <button
                                  className="btn-primary btn btn-sm"
                                  disabled={savingId === m.emp_id}
                                  onClick={() => handleMarkPaid(m.emp_id)}
                                >
                                  {savingId === m.emp_id ? "처리 중..." : "납부 완료 체크"}
                                </button>
                              </div>
                            </td>
                            <td>
                              <button
                                className="btn-secondary btn btn-sm"
                                disabled={savingId === m.emp_id}
                                onClick={() => handleSaveProfile(m.emp_id)}
                              >
                                저장
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* 납부 알림 탭 */}
            {activeTab === "reminders" && (
              <div className="space-y-6">
                {/* 미납자 목록 */}
                {unpaidMembers.length > 0 && (
                  <div className="card p-4 border-l-4 border-red-500">
                    <p className="font-semibold text-gray-900">미납자 자동 감지 ({unpaidMembers.length}명)</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {unpaidMembers.slice(0, 30).map((m) => (
                        <span key={m.emp_id} className="badge-red text-sm">
                          {m.name} ({m.emp_id})
                        </span>
                      ))}
                      {unpaidMembers.length > 30 && (
                        <span className="badge-gray">외 {unpaidMembers.length - 30}명</span>
                      )}
                    </div>
                  </div>
                )}

                {/* 알림 설정 */}
                <div className="card p-4 space-y-3">
                  <div className="action-bar">
                    <label className="text-xs text-gray-500">기준 월</label>
                    <input
                      type="month"
                      className="field-input"
                      style={{ width: 170 }}
                      value={yearMonth}
                      onChange={(e) => setYearMonth(e.target.value)}
                    />
                    <select
                      className="field-select"
                      style={{ width: 180 }}
                      value={reminderPeriod}
                      onChange={(e) => setReminderPeriod(e.target.value)}
                    >
                      <option value="MONTH_END">월말 알림</option>
                      <option value="MONTH_START">월초 알림</option>
                    </select>
                    <button className="btn-secondary btn btn-sm" onClick={loadReminderTargets}>
                      알림 대상 조회
                    </button>
                  </div>

                  {targetsData && (
                    <div className="card p-3">
                      <p className="text-sm font-semibold text-gray-700">{targetsData.title}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        대상 {targetsData.target_count}명 ({targetsData.year_month})
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {targetsData.targets.slice(0, 30).map((t) => (
                          <span key={t.emp_id} className="badge-red text-sm">
                            {t.name} ({t.emp_id})
                          </span>
                        ))}
                        {targetsData.targets.length > 30 && (
                          <span className="badge-gray">외 {targetsData.targets.length - 30}명</span>
                        )}
                      </div>
                    </div>
                  )}

                  <textarea
                    className="field-textarea"
                    placeholder="알림 발송 메모(선택)"
                    value={reminderMemo}
                    onChange={(e) => setReminderMemo(e.target.value)}
                  />
                  <button className="btn-primary btn btn-sm" onClick={handleLogReminder}>
                    알림 발송 기록 저장
                  </button>
                </div>

                {/* 알림 기록 */}
                <div className="card overflow-hidden">
                  <div className="p-4 border-b">
                    <p className="section-title">최근 알림 기록</p>
                  </div>
                  <div className="overflow-x-auto w-full">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>기준 월</th>
                          <th>구분</th>
                          <th>대상 수</th>
                          <th>발송자</th>
                          <th>시간</th>
                          <th>메모</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reminderLogs.length === 0 ? (
                          <tr>
                            <td colSpan={6}>
                              <div className="empty-state py-8">
                                <p className="empty-state-text">기록이 없습니다.</p>
                              </div>
                            </td>
                          </tr>
                        ) : reminderLogs.map((r) => (
                          <tr key={r.id}>
                            <td>{r.year_month}</td>
                            <td>{r.period === "MONTH_END" ? "월말" : "월초"}</td>
                            <td>{r.target_count}명</td>
                            <td>{r.sent_by}</td>
                            <td>{new Date(r.created_at).toLocaleString("ko-KR")}</td>
                            <td>{r.memo || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 알림 효과 측정 */}
                {effectiveness && effectiveness.effectiveness.length > 0 && (
                  <div className="card overflow-hidden">
                    <div className="p-4 border-b  bg-blue-50">
                      <p className="section-title">알림 효과 분석 ({effectiveness.analysis_period})</p>
                    </div>
                    <div className="overflow-x-auto w-full">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>기준 월</th>
                            <th>알림 구분</th>
                            <th>알림 대상</th>
                            <th>전체 회원</th>
                            <th>납부율</th>
                            <th>발송자</th>
                            <th>메모</th>
                          </tr>
                        </thead>
                        <tbody>
                          {effectiveness.effectiveness.map((e, idx) => (
                            <tr key={idx}>
                              <td>{e.year_month}</td>
                              <td>{e.period === "MONTH_END" ? "월말" : "월초"}</td>
                              <td>{e.reminder_target_count}명</td>
                              <td>{e.total_members}명</td>
                              <td className={e.current_paid_rate >= 70 ? "text-green-600 font-semibold" : "text-orange-600 font-semibold"}>
                                {e.current_paid_rate.toFixed(1)}%
                              </td>
                              <td>{e.sent_by}</td>
                              <td className="text-xs">{e.memo || "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* 입금 연동 테스트 / 수동 반영 */}
                <div className="card p-4 space-y-3">
                  <p className="section-title">입금 연동 (이름 + 금액 자동 반영)</p>
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    연동 대상 계좌: 국민은행 331301-04-169767 (예금주: 박한올)
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    <input
                      className="field-input"
                      placeholder="입금자 이름"
                      value={depositName}
                      onChange={(e) => setDepositName(e.target.value)}
                    />
                    <input
                      className="field-input"
                      placeholder="입금 금액"
                      type="number"
                      value={depositAmount}
                      onChange={(e) => setDepositAmount(e.target.value)}
                    />
                    <input
                      type="month"
                      className="field-input"
                      value={yearMonth}
                      onChange={(e) => setYearMonth(e.target.value)}
                    />
                    <label className="flex items-center gap-2 text-sm text-gray-700 px-2">
                      <input
                        type="checkbox"
                        checked={depositAutoApply}
                        onChange={(e) => setDepositAutoApply(e.target.checked)}
                      />
                      자동 반영
                    </label>
                  </div>
                  <textarea
                    className="field-textarea"
                    placeholder="원문 알림 텍스트 (선택)"
                    value={depositRawText}
                    onChange={(e) => setDepositRawText(e.target.value)}
                  />
                  <button
                    className="btn-primary btn btn-sm"
                    disabled={depositLoading}
                    onClick={handleIngestDeposit}
                  >
                    {depositLoading ? "처리 중..." : "입금 이벤트 반영"}
                  </button>
                </div>

                {/* 입금 연동 로그 */}
                <div className="card overflow-hidden">
                  <div className="p-4 border-b flex flex-wrap gap-2 items-center justify-between">
                    <p className="section-title">입금 연동 처리 로그</p>
                    <input
                      className="field-input"
                      style={{ maxWidth: 260 }}
                      placeholder="이름/상태/emp_id 검색"
                      value={depositKeyword}
                      onChange={(e) => setDepositKeyword(e.target.value)}
                    />
                  </div>
                  <div className="overflow-x-auto w-full">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>시간</th>
                          <th>입금자</th>
                          <th>금액</th>
                          <th>기준 월</th>
                          <th>상태</th>
                          <th>매칭 회원</th>
                          <th>개월 수</th>
                          <th>연결 납부ID</th>
                          <th>메모</th>
                        </tr>
                      </thead>
                      <tbody>
                        {depositLogs.length === 0 ? (
                          <tr>
                            <td colSpan={9}>
                              <div className="empty-state py-8">
                                <p className="empty-state-text">입금 연동 로그가 없습니다.</p>
                              </div>
                            </td>
                          </tr>
                        ) : depositLogs.map((r) => (
                          <tr key={r.id}>
                            <td>{new Date(r.created_at).toLocaleString("ko-KR")}</td>
                            <td>{r.depositor_name}</td>
                            <td>{Number(r.amount || 0).toLocaleString("ko-KR")}원</td>
                            <td>{r.year_month}</td>
                            <td>
                              {r.match_status === "APPLIED" && <span className="badge-green">APPLIED</span>}
                              {r.match_status !== "APPLIED" && <span className="badge-red">{r.match_status}</span>}
                            </td>
                            <td>{r.matched_emp_id || "-"}</td>
                            <td>{r.months_covered || 0}</td>
                            <td>{r.linked_payment_id || "-"}</td>
                            <td className="text-xs">{r.note || "-"}</td>
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
  );
}
