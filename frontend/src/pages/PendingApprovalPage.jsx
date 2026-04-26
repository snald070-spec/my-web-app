import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function PendingApprovalPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/", { replace: true });
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-sm w-full text-center space-y-5">
        <div className="w-20 h-20 bg-blue-100 rounded-2xl flex items-center justify-center text-4xl mx-auto">
          🏀
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-bold text-gray-800">가입 신청 접수 완료</h1>
          <p className="text-sm text-gray-600 leading-relaxed">
            Draw Basketball Team 관리자가 가입 요청을 검토 중입니다.
            <br />
            승인이 완료되면 앱을 이용하실 수 있습니다.
          </p>
        </div>
        <div className="rounded-xl bg-blue-50 border border-blue-200 px-4 py-3">
          <p className="text-xs text-blue-700 leading-relaxed">
            승인 후 다시 로그인하시면 자동으로 입장됩니다.
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="w-full btn-secondary btn py-2.5 rounded-xl text-sm font-semibold"
        >
          로그아웃
        </button>
      </div>
    </div>
  );
}
