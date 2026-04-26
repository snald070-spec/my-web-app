import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import api from "../api";

export default function PendingApprovalPage() {
  const { logout, updateUser } = useAuth();
  const navigate = useNavigate();
  const [checking, setChecking] = useState(false);
  const [msg, setMsg] = useState("");

  function handleLogout() {
    logout();
    navigate("/", { replace: true });
  }

  async function handleCheckApproval() {
    setChecking(true);
    setMsg("");
    try {
      const { data } = await api.get("/api/auth/me");
      if (data.is_approved) {
        updateUser(data);
        window.location.replace("/");
      } else {
        setMsg("아직 승인되지 않았습니다. 관리자에게 문의해주세요.");
      }
    } catch {
      setMsg("확인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setChecking(false);
    }
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
            승인 완료 알림을 받으셨다면 아래 버튼으로 확인하세요.
          </p>
        </div>
        {msg && (
          <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">{msg}</p>
        )}
        <button
          onClick={handleCheckApproval}
          disabled={checking}
          className="w-full btn-primary btn py-2.5 rounded-xl text-sm font-semibold disabled:opacity-60"
        >
          {checking ? "확인 중..." : "승인 여부 확인"}
        </button>
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
