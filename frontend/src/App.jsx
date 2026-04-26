import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Component, useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Avatar from "./components/Avatar";
import UpdateBanner from "./components/UpdateBanner";
import LoginPage      from "./pages/LoginPage";
import DashboardPage  from "./pages/DashboardPage";
import UserManagementPage from "./pages/UserManagementPage";
import NoticePage from "./pages/NoticePage";
import FeeManagementPage from "./pages/FeeManagementPage";
import AttendancePage from "./pages/AttendancePage";
import LeaguePage from "./pages/LeaguePage";
import ScoreSheetPage from "./pages/ScoreSheetPage";
import ScoreSheetViewPage from "./pages/ScoreSheetViewPage";
import LeagueViewPage from "./pages/LeagueViewPage";
import LeagueDraftPage from "./pages/LeagueDraftPage";
import MembersPage from "./pages/MembersPage";
import MyProfilePage from "./pages/MyProfilePage";
import GoogleProfileSetupPage from "./pages/GoogleProfileSetupPage";

// ── Error boundary (prevents full white-screen crashes) ───────────────────────
class RouteErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { hasError: false, msg: "" }; }
  static getDerivedStateFromError(err) { return { hasError: true, msg: String(err?.message || err) }; }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-8">
          <div className="bg-white rounded-2xl shadow p-8 max-w-md w-full text-center space-y-3">
            <p className="text-2xl">⚠️</p>
            <p className="font-bold text-gray-800">페이지를 불러오는 중 오류가 발생했습니다.</p>
            <p className="text-xs text-gray-400 break-all">{this.state.msg}</p>
            <button className="btn-primary btn px-5 py-2 rounded-xl"
              onClick={() => { this.setState({ hasError: false }); window.location.reload(); }}>
              다시 불러오기
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Global user banner: always shown when logged in ───────────────────────────
const ROLE_BADGE = {
  MASTER:  { label: "마스터", cls: "bg-purple-100 text-purple-700" },
  ADMIN:   { label: "관리자", cls: "bg-blue-100 text-blue-700" },
  GENERAL: { label: "일반",   cls: "bg-gray-100 text-gray-600" },
  STUDENT: { label: "학생",   cls: "bg-green-100 text-green-700" },
};

function UserBanner() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  const badge = ROLE_BADGE[user?.role] ?? { label: user?.role ?? "", cls: "bg-gray-100 text-gray-600" };

  function handleLogout() {
    if (confirming) {
      logout();
      navigate("/", { replace: true });
    } else {
      setConfirming(true);
    }
  }

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(false), 3000);
    return () => clearTimeout(t);
  }, [confirming]);

  return (
    <div className="shrink-0 bg-white border-b border-gray-100">
      <div className="px-3 sm:px-6 py-2 flex items-center justify-between gap-3">
        <span className="text-sm font-extrabold text-blue-600 tracking-tight select-none">
          🏀 Draw
        </span>
        <div className="flex items-center gap-2">
          <span className={`badge text-xs font-semibold px-2 py-0.5 rounded-full ${badge.cls}`}>
            {badge.label}
          </span>
          <button
            type="button"
            onClick={() => navigate("/profile")}
            className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
            title="내 정보 수정"
          >
            <Avatar name={user?.name} avatarUrl={user?.avatar_url} size="sm" />
            <span className="text-sm font-semibold text-gray-700 max-w-[100px] truncate">
              {user?.name}
            </span>
          </button>
          <button
            onClick={handleLogout}
            className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition-all ${
              confirming
                ? "bg-red-500 text-white hover:bg-red-600 scale-105"
                : "text-gray-500 hover:text-red-500 hover:bg-red-50"
            }`}
          >
            {confirming ? "정말 로그아웃?" : "로그아웃"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Shared page chrome: header bar + scrollable content area ──────────────────
function PageHeader({ label, backTo = "/", backLabel = "← Draw Basketball Team 홈" }) {
  const navigate = useNavigate();
  return (
    <div className="shrink-0 bg-white border-b shadow-header">
      <div className="px-3 sm:px-6 py-3 flex items-center gap-3">
        <button
          className="text-sm text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1 transition-colors"
          onClick={() => navigate(backTo)}
        >{backLabel}</button>
        <span className="w-px h-4 bg-gray-200 shrink-0" />
        <span className="text-sm text-gray-700 font-semibold flex-1">{label}</span>
      </div>
    </div>
  );
}

function PageLayout({ label, backTo, backLabel, scrollable = true, children }) {
  return (
    <div className="lg:flex-1 lg:min-h-0 lg:flex lg:flex-col">
      <PageHeader label={label} backTo={backTo} backLabel={backLabel} />
      <div className={`lg:flex-1 lg:min-h-0${scrollable ? " lg:overflow-y-auto" : " lg:overflow-hidden"}`}>
        {children}
      </div>
    </div>
  );
}

// ── RBAC guards ───────────────────────────────────────────────────────────────
function RequireAdmin({ children }) {
  const { user } = useAuth();
  if (!["MASTER", "ADMIN"].includes(user?.role)) return <Navigate to="/" replace />;
  return children;
}

// ── App routes ────────────────────────────────────────────────────────────────
function AppRoutes() {
  const { user } = useAuth();

  // Not logged in or first-login forced password change
  if (!user || user.is_first_login) {
    const current = window.location.pathname + window.location.search;
    if (current !== "/" && !sessionStorage.getItem("loginRedirect")) {
      sessionStorage.setItem("loginRedirect", current);
    }
    return <LoginPage />;
  }

  // Google 신규 가입자 프로필 미완성
  if (user.is_profile_complete === false) {
    return <GoogleProfileSetupPage />;
  }

  return (
    <div className="min-h-screen lg:h-screen lg:overflow-hidden lg:flex lg:flex-col">
      <UserBanner />
      <div className="lg:flex-1 lg:min-h-0 lg:flex lg:flex-col">
        <Routes>

          {/* ── Home / Dashboard ─────────────────────────────────── */}
          <Route path="/" element={
            <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
              <DashboardPage />
            </div>
          } />

          <Route path="/admin/users" element={
            <RequireAdmin>
              <PageLayout label="👥 회원 관리" scrollable>
                <RouteErrorBoundary>
                  <UserManagementPage />
                </RouteErrorBoundary>
              </PageLayout>
            </RequireAdmin>
          } />

          <Route path="/notices" element={
            <PageLayout label="📢 공지사항" scrollable>
              <RouteErrorBoundary>
                <NoticePage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/fees" element={
            <PageLayout label="💳 회비 관리" scrollable>
              <RouteErrorBoundary>
                <FeeManagementPage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/attendance" element={
            <PageLayout label="🗳️ 출석 투표" scrollable>
              <RouteErrorBoundary>
                <AttendancePage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/league" element={
            <RequireAdmin>
              <PageLayout label="🏆 리그전 운영" scrollable>
                <RouteErrorBoundary>
                  <LeaguePage />
                </RouteErrorBoundary>
              </PageLayout>
            </RequireAdmin>
          } />

          <Route path="/league/scoresheet" element={
            <RequireAdmin>
              <PageLayout label="📋 경기 기록지" scrollable>
                <RouteErrorBoundary>
                  <ScoreSheetPage />
                </RouteErrorBoundary>
              </PageLayout>
            </RequireAdmin>
          } />

          <Route path="/league/scoresheet/view" element={
            <PageLayout label="📄 경기 기록 조회" scrollable>
              <RouteErrorBoundary>
                <ScoreSheetViewPage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/league/draft" element={
            <PageLayout label="🎯 리그 드래프트" scrollable>
              <RouteErrorBoundary>
                <LeagueDraftPage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/league/view" element={
            <PageLayout label="🏀 리그전 현황" scrollable>
              <RouteErrorBoundary>
                <LeagueViewPage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/members" element={
            <PageLayout label="🔍 회원 검색" scrollable>
              <RouteErrorBoundary>
                <MembersPage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          <Route path="/profile" element={
            <PageLayout label="👤 내 정보 수정" scrollable>
              <RouteErrorBoundary>
                <MyProfilePage />
              </RouteErrorBoundary>
            </PageLayout>
          } />

          {/* ── ADD FEATURE ROUTES BELOW ────────────────────────────
              Pattern for a scrollable full-width page:

              <Route path="/my-feature" element={
                <PageLayout label="🔧 My Feature" scrollable>
                  <RouteErrorBoundary>
                    <MyFeaturePage />
                  </RouteErrorBoundary>
                </PageLayout>
              } />

              Pattern for admin-only page:

              <Route path="/admin/users" element={
                <RequireAdmin>
                  <PageLayout label="👥 User Management" scrollable>
                    <RouteErrorBoundary>
                      <UsersPage />
                    </RouteErrorBoundary>
                  </PageLayout>
                </RequireAdmin>
              } />
          ────────────────────────────────────────────────────────── */}

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />

        </Routes>
      </div>
    </div>
  );
}

function AndroidBackButtonHandler() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "android") {
      return;
    }

    let listenerHandle;

    const register = async () => {
      listenerHandle = await CapacitorApp.addListener("backButton", () => {
        if (location.pathname === "/") {
          const shouldExit = window.confirm("종료하시겠습니까?");
          if (shouldExit) {
            CapacitorApp.exitApp();
          }
          return;
        }

        if (window.history.length > 1) {
          navigate(-1);
        } else {
          navigate("/", { replace: true });
        }
      });
    };

    register();

    return () => {
      if (listenerHandle) {
        listenerHandle.remove();
      }
    };
  }, [location.pathname, navigate]);

  return null;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

// Google OAuth 리디렉션 콜백 처리 (인앱 브라우저 지원용)
// Google이 #access_token=... 을 붙여 돌아왔을 때 로그인을 완성한다.
function GoogleOAuthRedirectHandler() {
  const { loginWithGoogle } = useAuth();
  const handled = useRef(false);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    if (handled.current) return;
    const hash = window.location.hash.slice(1);
    if (!hash) return;

    const params = new URLSearchParams(hash);
    const accessToken = params.get("access_token");
    const returnedState = params.get("state");
    const savedState = sessionStorage.getItem("google_oauth_state");

    if (!accessToken || !returnedState || returnedState !== savedState) return;

    handled.current = true;
    sessionStorage.removeItem("google_oauth_state");
    // 해시를 URL에서 제거
    window.history.replaceState({}, "", window.location.pathname + window.location.search);

    setProcessing(true);
    loginWithGoogle(accessToken)
      .then(() => {
        const redirect = sessionStorage.getItem("loginRedirect");
        sessionStorage.removeItem("loginRedirect");
        window.location.replace(redirect || "/");
      })
      .catch(() => setProcessing(false));
  }, [loginWithGoogle]);

  if (!processing) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-white">
      <p className="text-sm text-gray-500">Google 로그인 처리 중...</p>
    </div>
  );
}

export default function App() {
  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <BrowserRouter>
        <AuthProvider>
          <AndroidBackButtonHandler />
          <GoogleOAuthRedirectHandler />
          <AppRoutes />
          <UpdateBanner />
        </AuthProvider>
      </BrowserRouter>
    </GoogleOAuthProvider>
  );
}
