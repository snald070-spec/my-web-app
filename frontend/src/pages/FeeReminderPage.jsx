import { useEffect, useState } from "react";
import api from "../api";
import { getItems } from "../utils/apiHelpers";

function currentYearMonth() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

export default function FeeReminderPage() {
  const [yearMonth, setYearMonth] = useState(currentYearMonth);
  const [period, setPeriod] = useState("MONTH_END");
  const [memo, setMemo] = useState("");

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  const [targetsData, setTargetsData] = useState(null);
  const [logs, setLogs] = useState([]);

  async function loadLogs() {
    const { data } = await api.get("/api/fees/admin/reminders/log?skip=0&limit=20");
    setLogs(getItems(data));
  }

  async function loadTargets() {
    setErr("");
    try {
      const { data } = await api.get(
        `/api/fees/admin/reminders?year_month=${yearMonth}&period=${period}`,
      );
      setTargetsData(data);
    } catch (e) {
      setErr(e.response?.data?.detail || "알림 대상 조회에 실패했습니다.");
    }
  }

  async function logReminder() {
    setErr("");
    try {
      await api.post("/api/fees/admin/reminders/log", {
        year_month: yearMonth,
        period,
        memo,
      });
      setMemo("");
      await loadLogs();
      setSuccess("알림 발송 기록을 저장했습니다.");
      setTimeout(() => setSuccess(""), 1800);
    } catch (e) {
      setErr(e.response?.data?.detail || "알림 기록 저장에 실패했습니다.");
    }
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      setErr("");
      try {
        await loadLogs();
      } catch (e) {
        setErr(e.response?.data?.detail || "알림 기록을 불러오지 못했습니다.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
        <h1 className="page-title">회비 납부 알림</h1>
        <p className="page-subtitle">월말/월초 회비 알림 대상 조회 및 발송 기록 관리</p>
      </div>

      {err && <div className="alert-danger">{err}</div>}

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
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="MONTH_END">월말 알림</option>
            <option value="MONTH_START">월초 알림</option>
          </select>
          <button className="btn-secondary btn btn-sm" onClick={loadTargets}>
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
                <span key={t.emp_id} className="badge-red">
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
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
        />
        <button className="btn-primary btn btn-sm" onClick={logReminder}>
          알림 발송 기록 저장
        </button>
      </div>

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
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-state py-8">
                      <p className="empty-state-text">기록이 없습니다.</p>
                    </div>
                  </td>
                </tr>
              ) : logs.map((r) => (
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
    </div>
  );
}
