/**
 * DashboardPage — the entry point for authenticated users.
 *
 * Admin sees stats + "View as Employee" toggle.
 * Employee sees a personalised welcome card.
 *
 * EXTEND THIS FILE to add real modules/cards.
 */
import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PreviewToggleButton, PreviewModeBanner } from "../components/EmployeePreviewToggle";
import PlayerCareerModal from "../components/PlayerCareerModal";
import api from "../api";

/** Reusable stat card */
function StatCard({ label, value, icon, colour = "blue", to }) {
  const colours = {
    blue:  "bg-blue-50  text-blue-600",
    green: "bg-green-50 text-green-600",
    amber: "bg-amber-50 text-amber-600",
    red:   "bg-red-50   text-red-600",
  };
  const Wrapper = to ? Link : "div";
  return (
    <Wrapper to={to} className={`stat-card ${to ? "transition-all hover:-translate-y-0.5 hover:shadow-md" : ""}`}>
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-lg ${colours[colour]}`}>
        {icon}
      </div>
      <p className="stat-value mt-2">{value ?? "—"}</p>
      <p className="stat-label">{label}</p>
    </Wrapper>
  );
}

/** Admin view — stats + module shortcuts */
function AdminView({ onPreview }) {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [alertMsg, setAlertMsg] = useState("");
  const [statsEmpId, setStatsEmpId] = useState(null);

  useEffect(() => {
    api.get("/api/dashboard/admin-stats")
      .then(r => setStats(r.data))
      .catch(() => {});
  }, []);

  async function handleAcknowledgeNonFeeAlerts() {
    try {
      const { data } = await api.post("/api/dashboard/admin/non-fee-deposits/ack-all?today_only=true");
      setAlertMsg(data?.message || "확인 처리되었습니다.");
      const refreshed = await api.get("/api/dashboard/admin-stats");
      setStats(refreshed.data);
    } catch (e) {
      setAlertMsg(e?.response?.data?.detail || "확인 처리에 실패했습니다.");
    }
  }

  return (
    <div className="page-container">
      {statsEmpId && (
        <PlayerCareerModal empId={statsEmpId} onClose={() => setStatsEmpId(null)} />
      )}
      <PreviewToggleButton onPreview={onPreview} />

      <div className="page-header">
        <h1 className="page-title">🏢 Draw Basketball Team 관리자 대시보드</h1>
        <p className="page-subtitle">포털 전체 현황입니다.</p>
      </div>



      {user?.role === "MASTER" && (stats?.non_fee_deposit_alerts_today || 0) > 0 && (
        <div className="card border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-bold text-red-700">회비 외 입금 내역이 확인되었습니다.</p>
          <p className="text-xs text-red-600 mt-1">
            오늘 감지 건수: {stats?.non_fee_deposit_alerts_today}건 (전체 누적: {stats?.non_fee_deposit_alerts}건)
          </p>
          <div className="mt-3 space-y-1">
            {(stats?.recent_non_fee_deposits || []).slice(0, 3).map((r) => (
              <p key={r.id} className="text-xs text-red-700">
                {r.depositor_name} / {Number(r.amount || 0).toLocaleString("ko-KR")}원 / {r.year_month}
              </p>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <Link to="/fees" className="btn-primary btn btn-sm">회비 관리에서 확인</Link>
            <button className="btn-secondary btn btn-sm" onClick={handleAcknowledgeNonFeeAlerts}>오늘 알림 확인 처리</button>
          </div>
          {alertMsg && <p className="mt-2 text-xs text-red-700">{alertMsg}</p>}
        </div>
      )}

      {/* Module card grid — add a card per feature */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mt-2">
        <ModuleCard icon="👥" title="회원 관리"    description="전체 계정을 조회하고 상태를 확인합니다."                          to="/admin/users"            colour="blue"   />
        <ModuleCard icon="📢" title="공지사항"     description="운영 공지를 작성하고 확인합니다."                                to="/notices"                colour="green"  />
        <ModuleCard icon="💳" title="회비 관리"    description="회원 회비 납부 현황을 조회하고 납부 완료를 체크합니다."              to="/fees"                   colour="amber"  />
        <ModuleCard icon="🔔" title="회비 납부 알림" description="월말/월초 알림 대상을 조회하고 발송 기록을 관리합니다."           to="/fees"                   colour="orange" />
        <ModuleCard icon="🗳️" title="출석 투표"    description="출석 일정을 생성하고 회원 누적 출석을 관리합니다."                  to="/attendance"             colour="purple" />
        <ModuleCard icon="🏆" title="리그전 운영"   description="시즌 생성, 경기 결과 입력, 주차별 순위를 관리합니다."              to="/league"                 colour="indigo" />
        <ModuleCard icon="📋" title="경기 기록지"   description="경기를 보면서 선수별 스탯을 실시간으로 입력합니다."                to="/league/scoresheet"      colour="teal"   />
        <ModuleCard icon="📄" title="기록지 조회"   description="저장된 경기 기록과 분석을 읽기 전용으로 확인합니다."               to="/league/scoresheet/view" colour="cyan"   />
        <ModuleCard icon="🔍" title="회원 검색"    description="활동 회원 목록과 커리어 스탯을 확인합니다."                        to="/members"                colour="pink"   />
        <ModuleCard icon="📊" title="내 스탯 보기"  description="내 커리어 통산 및 시즌별 기록을 확인합니다."                      onClick={() => setStatsEmpId(user?.emp_id)} colour="violet" />
        <ModuleCard icon="👤" title="내 정보 수정"  description="프로필 사진, 이름, 나이, 포지션을 수정합니다."                    to="/profile"                colour="rose"   />
      </div>
    </div>
  );
}

/** Attendance summary mini-card */
function AttendanceSummary() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get("/api/attendance/me/summary").then(r => setSummary(r.data)).catch(() => {});
  }, []);

  if (!summary) return null;

  const rate = summary.attendance_rate ?? 0;
  const barColor = rate >= 70 ? "bg-green-400" : rate >= 40 ? "bg-amber-400" : "bg-red-400";

  return (
    <div className="rounded-2xl bg-white border border-slate-200 shadow-sm px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">내 출석 현황</p>
        <span className="text-xs text-slate-400">{summary.total_votes}경기</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <div className="flex justify-between text-[11px] text-slate-500 mb-1">
            <span>출석률</span>
            <span className="font-bold text-slate-700">{rate}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${rate}%` }} />
          </div>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[11px] text-slate-400">누적점수</p>
          <p className="text-sm font-bold text-blue-600">{summary.cumulative_score ?? 0}점</p>
        </div>
      </div>
      <div className="mt-2 flex gap-3 text-[11px] text-slate-500">
        <span>출석 <b className="text-green-600">{summary.attend_count}</b></span>
        <span>지각 <b className="text-amber-500">{summary.late_count}</b></span>
        <span>결석 <b className="text-red-500">{summary.absent_count}</b></span>
      </div>
    </div>
  );
}

/** Member view — personalised welcome */
function MemberView() {
  const { user } = useAuth();
  const orgLabel = "Draw Basketball Team";
  const [statsEmpId, setStatsEmpId] = useState(null);

  return (
    <div className="page-container">
      {statsEmpId && (
        <PlayerCareerModal empId={statsEmpId} onClose={() => setStatsEmpId(null)} />
      )}
      <div className="card px-6 py-8 text-center max-w-lg mx-auto">
        <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl mx-auto mb-4">
          👋
        </div>
        <h1 className="text-xl font-bold text-gray-800 mb-1">
          {user?.name}님, 환영합니다!
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          {orgLabel}
        </p>

        <AttendanceSummary />

        <div className="grid grid-cols-2 gap-3 mt-4">
          <ModuleCard icon="📢" title="공지사항"      description="최신 운영 공지를 확인합니다."                                  to="/notices"                colour="green"  />
          <ModuleCard icon="💳" title="회비 납부 현황" description="이번 달 회비 납부 상태와 내 납부 이력을 확인합니다."             to="/fees"                   colour="amber"  />
          <ModuleCard icon="🗳️" title="출석 투표"     description="일정별로 참석/지각/불참을 투표하고 누적 출석을 확인합니다."        to="/attendance"             colour="purple" />
          <ModuleCard icon="🏀" title="리그전 현황"   description="시즌별 순위표, 경기 결과, 개인 스탯을 확인합니다."               to="/league/view"            colour="indigo" />
          <ModuleCard icon="📄" title="경기 기록 조회" description="저장된 경기 기록지와 경기 분석을 확인합니다."                   to="/league/scoresheet/view" colour="teal"   />
          <ModuleCard icon="🔍" title="회원 검색"     description="활동 회원 목록, 포지션, 커리어 스탯을 한눈에 확인합니다."         to="/members"                colour="pink"   />
          <ModuleCard icon="📊" title="내 스탯 보기"  description="내 커리어 통산 및 시즌별 기록을 확인합니다."                    onClick={() => setStatsEmpId(user?.emp_id)} colour="violet" />
          <ModuleCard icon="👤" title="내 정보 수정"  description="프로필 사진, 이름, 나이, 포지션을 수정합니다."                   to="/profile"                colour="rose"   />
        </div>
      </div>
    </div>
  );
}

/** Module shortcut card — supports Link (to) or button (onClick) */
function ModuleCard({ icon, title, description, to, onClick, colour = "blue" }) {
  const colourMap = {
    blue:   { cardBg: "#93c5fd", iconCls: "bg-blue-600   text-white" },
    green:  { cardBg: "#6ee7b7", iconCls: "bg-emerald-600 text-white" },
    amber:  { cardBg: "#fcd34d", iconCls: "bg-amber-600  text-white" },
    orange: { cardBg: "#fdba74", iconCls: "bg-orange-600 text-white" },
    purple: { cardBg: "#d8b4fe", iconCls: "bg-purple-600 text-white" },
    indigo: { cardBg: "#a5b4fc", iconCls: "bg-indigo-600 text-white" },
    teal:   { cardBg: "#5eead4", iconCls: "bg-teal-600   text-white" },
    cyan:   { cardBg: "#67e8f9", iconCls: "bg-cyan-600   text-white" },
    pink:   { cardBg: "#f9a8d4", iconCls: "bg-pink-600   text-white" },
    violet: { cardBg: "#c4b5fd", iconCls: "bg-violet-600 text-white" },
    rose:   { cardBg: "#fda4af", iconCls: "bg-rose-600   text-white" },
    red:    { cardBg: "#fca5a5", iconCls: "bg-red-600    text-white" },
  };
  const c = colourMap[colour] ?? colourMap.blue;
  const inner = (
    <>
      <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-2xl mb-3 ${c.iconCls}`}>
        {icon}
      </div>
      <p className="font-bold text-gray-800 text-sm leading-tight">{title}</p>
      <p className="text-xs text-gray-700 mt-1 leading-relaxed">{description}</p>
    </>
  );
  const cardCls = "card p-4 flex flex-col items-center text-center cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 justify-center overflow-hidden";
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${cardCls} w-full`}
        style={{ backgroundColor: c.cardBg }}
      >
        {inner}
      </button>
    );
  }
  return (
    <Link
      to={to}
      className={cardCls}
      style={{ backgroundColor: c.cardBg }}
    >
      {inner}
    </Link>
  );
}

/** Main export */
export default function DashboardPage() {
  const { user } = useAuth();
  const [previewMode, setPreviewMode] = useState(false);

  const isAdmin = !previewMode && ["MASTER", "ADMIN"].includes(user?.role);

  return (
    <>
      {["MASTER", "ADMIN"].includes(user?.role) && previewMode && (
        <PreviewModeBanner onReturn={() => setPreviewMode(false)} />
      )}
      {isAdmin
        ? <AdminView onPreview={() => setPreviewMode(true)} />
        : <MemberView />
      }
    </>
  );
}
