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
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-2">
        <ModuleCard
          icon="👥"
          title="회원 관리"
          description="전체 계정을 조회하고 상태를 확인합니다."
          to="/admin/users"
          colour="blue"
        />
        <ModuleCard
          icon="📢"
          title="공지사항"
          description="운영 공지를 작성하고 확인합니다."
          to="/notices"
          colour="green"
        />
        <ModuleCard
          icon="💳"
          title="회비 관리"
          description="회원 회비 납부 현황을 조회하고 납부 완료를 체크합니다."
          to="/fees"
          colour="amber"
        />
        <ModuleCard
          icon="🔔"
          title="회비 납부 알림"
          description="월말/월초 알림 대상을 조회하고 발송 기록을 관리합니다."
          to="/fees"
          colour="green"
        />
        <ModuleCard
          icon="🗳️"
          title="출석 투표"
          description="출석 일정을 생성하고 회원 누적 출석을 관리합니다."
          to="/attendance"
          colour="blue"
        />
        <ModuleCard
          icon="🏆"
          title="리그전 운영"
          description="시즌 생성, 경기 결과 입력, 주차별 순위를 관리합니다."
          to="/league"
          colour="amber"
        />
        <ModuleCard
          icon="📋"
          title="경기 기록지"
          description="경기를 보면서 선수별 스탯을 실시간으로 입력합니다."
          to="/league/scoresheet"
          colour="green"
        />
        <ModuleCard
          icon="📄"
          title="기록지 조회"
          description="저장된 경기 기록과 분석을 읽기 전용으로 확인합니다."
          to="/league/scoresheet/view"
          colour="blue"
        />
        {/* <ModuleCard icon="🚗" title="Vehicle Dispatch" ... /> */}
      </div>
    </div>
  );
}

/** Member view — personalised welcome */
function MemberView() {
  const { user } = useAuth();
  const orgParts = [user?.department, user?.division].filter((v) => !!(v && String(v).trim()));
  const orgLabel = orgParts.length > 0 ? orgParts.join(" · ") : "소속 미지정";

  return (
    <div className="page-container">
      <div className="card px-6 py-8 text-center max-w-lg mx-auto">
        <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl mx-auto mb-4">
          👋
        </div>
        <h1 className="text-xl font-bold text-gray-800 mb-1">
          {user?.name}님, 환영합니다!
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          {orgLabel}
        </p>
        <div className="grid grid-cols-1 gap-3">
          <ModuleCard
            icon="📢"
            title="공지사항"
            description="최신 운영 공지를 확인합니다."
            to="/notices"
            colour="green"
          />
          <ModuleCard
            icon="💳"
            title="회비 납부 현황"
            description="이번 달 회비 납부 상태와 내 납부 이력을 확인합니다."
            to="/fees"
            colour="amber"
          />
          <ModuleCard
            icon="🗳️"
            title="출석 투표"
            description="일정별로 참석/지각/불참을 투표하고 누적 출석을 확인합니다."
            to="/attendance"
            colour="blue"
          />
          <ModuleCard
            icon="🏀"
            title="리그전 현황"
            description="시즌별 순위표, 경기 결과, 개인 스탯을 확인합니다."
            to="/league/view"
            colour="amber"
          />
          <ModuleCard
            icon="📄"
            title="경기 기록 조회"
            description="저장된 경기 기록지와 경기 분석을 확인합니다."
            to="/league/scoresheet/view"
            colour="blue"
          />
        </div>
      </div>
    </div>
  );
}

/** Module shortcut card */
function ModuleCard({ icon, title, description, to, colour = "blue" }) {
  const colours = {
    blue:  "bg-blue-50  text-blue-600  hover:bg-blue-100",
    green: "bg-green-50 text-green-600 hover:bg-green-100",
    amber: "bg-amber-50 text-amber-700 hover:bg-amber-100",
  };
  return (
    <Link
      to={to}
      className={`card p-5 flex items-start gap-4 text-left cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5`}
    >
      <div className={`w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0 ${colours[colour]}`}>
        {icon}
      </div>
      <div>
        <p className="font-bold text-gray-800 text-sm">{title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{description}</p>
      </div>
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
