import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import { getItems, getTotal } from "../utils/apiHelpers";

const PAGE_SIZE_OPTIONS = [10, 20, 50];
const ROLE_OPTIONS = ["ALL", "MASTER", "ADMIN", "GENERAL", "STUDENT"];
const STATUS_OPTIONS = ["ALL", "ACTIVE", "INACTIVE"];
const FIRST_LOGIN_OPTIONS = ["ALL", "PENDING", "COMPLETED"];
const SORT_BY_OPTIONS = ["created_at", "emp_id", "role"];
const SORT_DIR_OPTIONS = ["desc", "asc"];

function parseEnum(value, options, fallback) {
  const v = String(value || "").toUpperCase();
  return options.includes(v) ? v : fallback;
}

function parseSortBy(value) {
  const v = String(value || "").trim();
  return SORT_BY_OPTIONS.includes(v) ? v : "created_at";
}

function parseSortDir(value) {
  const v = String(value || "").trim().toLowerCase();
  return SORT_DIR_OPTIONS.includes(v) ? v : "desc";
}

function parsePositiveInt(value, fallback) {
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : fallback;
}

function toErrorMessage(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) => (item && typeof item === "object" ? item.msg : String(item || "")))
      .filter(Boolean);
    return msgs.length ? msgs.join(" / ") : fallback;
  }
  if (typeof detail === "object") {
    if (typeof detail.msg === "string" && detail.msg.trim()) return detail.msg;
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return String(detail);
}

export default function UserManagementPage() {
  const { user: currentUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState({ items: [], total: 0, skip: 0, limit: 10 });
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [roleSavingId, setRoleSavingId] = useState("");
  const [rolePopupUser, setRolePopupUser] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [err, setErr] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [copiedLink, setCopiedLink] = useState(false);
  const [confirmState, setConfirmState] = useState({ open: false, type: "", user: null });
  const [page, setPage] = useState(() => parsePositiveInt(searchParams.get("page"), 1));
  const [pageSize, setPageSize] = useState(() => {
    const n = parsePositiveInt(searchParams.get("page_size"), 10);
    return PAGE_SIZE_OPTIONS.includes(n) ? n : 10;
  });
  const [keyword, setKeyword] = useState(() => searchParams.get("keyword") || "");
  const [role, setRole] = useState(() => parseEnum(searchParams.get("role"), ROLE_OPTIONS, "ALL"));
  const [status, setStatus] = useState(() => parseEnum(searchParams.get("status"), STATUS_OPTIONS, "ALL"));
  const [firstLogin, setFirstLogin] = useState(() => parseEnum(searchParams.get("first_login"), FIRST_LOGIN_OPTIONS, "ALL"));
  const [sortBy, setSortBy] = useState(() => parseSortBy(searchParams.get("sort_by")));
  const [sortDir, setSortDir] = useState(() => parseSortDir(searchParams.get("sort_dir")));
  const [exporting, setExporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [auditUserId, setAuditUserId] = useState("");
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditRows, setAuditRows] = useState([]);
  const [auditActionFilter, setAuditActionFilter] = useState("ALL");
  const [tempPwInfo, setTempPwInfo] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [createForm, setCreateForm] = useState({
    emp_id: "",
    role: "GENERAL",
    is_vip: false,
  });
  const [form, setForm] = useState({
    emp_id: "",
    role: "GENERAL",
    is_vip: false,
  });

  const skip = (page - 1) * pageSize;
  const filterSelectStyle = {};
  const filterButtonClass = "btn-secondary btn btn-sm h-[42px] w-full";
  const rowActionButtonClass = "btn-secondary btn px-2 py-1 text-[11px] min-w-0";
  const rowToggleButtonClass = "btn btn px-2 py-1 text-[11px] min-w-0";

  const actionLabel = {
    create_user: "회원 생성",
    update_profile: "회원 정보 수정",
    update_status: "회원 상태 변경",
    issue_temp_password: "임시 비밀번호 발급",
    delete_user: "회원 삭제",
  };

  const roleLabel = {
    MASTER: "마스터",
    ADMIN: "관리자",
    GENERAL: "일반",
    STUDENT: "학생",
  };

  const canManageRoles = currentUser?.role === "MASTER";
  const creatableRoles = canManageRoles ? ["MASTER", "ADMIN", "GENERAL", "STUDENT"] : ["GENERAL", "STUDENT"];

  const statusLabel = {
    ACTIVE: "활성",
    INACTIVE: "비활성",
  };

  const firstLoginLabel = {
    PENDING: "초기비번 변경 필요",
    COMPLETED: "초기비번 변경 완료",
  };

  const filteredAuditRows = useMemo(() => {
    if (auditActionFilter === "ALL") return auditRows;
    return auditRows.filter((row) => row.action === auditActionFilter);
  }, [auditRows, auditActionFilter]);

  const formatDateTime = (value) => {
    if (!value) return "-";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  async function copyText(value) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = value;
        ta.setAttribute("readonly", "");
        ta.style.position = "absolute";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        return true;
      } catch {
        return false;
      }
    }
  }

  async function loadUsers() {
    setLoading(true);
    setErr("");

    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(pageSize),
      keyword: keyword.trim(),
      role,
      status,
      first_login: firstLogin,
      sort_by: sortBy,
      sort_dir: sortDir,
    });

    try {
      const r = await api.get(`/api/users?${params.toString()}`);
        setData({
          items: getItems(r.data),
          total: getTotal(r.data),
          skip: r.data?.skip ?? skip,
          limit: r.data?.limit ?? pageSize,
        });
      setSelectedIds(new Set());
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "회원 목록을 불러오지 못했습니다."));
      setData({ items: [], total: 0, skip, limit: pageSize });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, [skip, pageSize, keyword, role, status, firstLogin, sortBy, sortDir]);

  useEffect(() => {
    const next = new URLSearchParams();
    if (page > 1) next.set("page", String(page));
    if (pageSize !== 10) next.set("page_size", String(pageSize));
    if (keyword.trim()) next.set("keyword", keyword.trim());
    if (role !== "ALL") next.set("role", role);
    if (status !== "ALL") next.set("status", status);
    if (firstLogin !== "ALL") next.set("first_login", firstLogin);
    if (sortBy !== "created_at") next.set("sort_by", sortBy);
    if (sortDir !== "desc") next.set("sort_dir", sortDir);
    setSearchParams(next, { replace: true });
  }, [page, pageSize, keyword, role, status, firstLogin, sortBy, sortDir, setSearchParams]);

  useEffect(() => {
    if (!successMsg) return undefined;
    const t = setTimeout(() => setSuccessMsg(""), 1800);
    return () => clearTimeout(t);
  }, [successMsg]);

  useEffect(() => {
    if (!copiedLink) return undefined;
    const t = setTimeout(() => setCopiedLink(false), 1500);
    return () => clearTimeout(t);
  }, [copiedLink]);

  async function handleCopyShareLink() {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedLink(true);
      setSuccessMsg("현재 필터 링크가 복사되었습니다.");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = url;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      setCopiedLink(true);
      setSuccessMsg("현재 필터 링크가 복사되었습니다.");
    }
  }

  async function handleExportCsv() {
    setExporting(true);
    setErr("");
    try {
      const params = new URLSearchParams({
        skip: "0",
        limit: "1000",
        keyword: keyword.trim(),
        role,
        status,
        first_login: firstLogin,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      const { data } = await api.get(`/api/users?${params.toString()}`);
      const rows = getItems(data);

      const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const header = ["이름", "권한", "상태", "VIP"];
      const lines = [header.map(esc).join(",")];

      rows.forEach((u) => {
        lines.push([
          u.emp_id,
          u.role,
          u.is_resigned ? "비활성" : "활성",
          u.is_vip ? "Y" : "N",
        ].map(esc).join(","));
      });

      const bom = "\uFEFF";
      const blob = new Blob([bom + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      a.href = url;
      a.download = `users-${ts}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "CSV 내보내기에 실패했습니다."));
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    if (!showCreate) return undefined;
    const onEsc = (e) => {
      if (e.key === "Escape") setShowCreate(false);
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [showCreate]);

  useEffect(() => {
    if (!editingUser) return undefined;
    const onEsc = (e) => {
      if (e.key === "Escape") setEditingUser(null);
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [editingUser]);

  useEffect(() => {
    if (!rolePopupUser) return undefined;
    const onEsc = (e) => {
      if (e.key === "Escape" && !roleSavingId) setRolePopupUser(null);
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [rolePopupUser, roleSavingId]);

  function openEdit(user) {
    setErr("");
    setEditingUser(user);
    setForm({
      emp_id: user.emp_id || "",
      role: user.role || "GENERAL",
      is_vip: !!user.is_vip,
    });
  }

  function openCreate() {
    setErr("");
    setCreateForm({
      emp_id: "",
      role: canManageRoles ? "GENERAL" : "GENERAL",
      is_vip: false,
    });
    setShowCreate(true);
  }

  async function handleCreateUser() {
    const id = createForm.emp_id.trim();
    if (!id) {
      setErr("이름은 필수입니다.");
      return;
    }

    setCreating(true);
    setErr("");
    try {
      const { data } = await api.post("/api/users", {
        emp_id: id,
        department: "미지정",
        division: "",
        email: "",
        role: createForm.role,
        is_vip: !!createForm.is_vip,
      });
      setShowCreate(false);
      setTempPwInfo({
        emp_id: data.emp_id,
        temp_password: data.temp_password,
      });
      const copied = await copyText(data.temp_password);
      await loadUsers();
      setSuccessMsg(copied ? "회원이 생성되었고 임시 비밀번호가 복사되었습니다." : "회원이 생성되었습니다.");
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "회원 생성에 실패했습니다."));
    } finally {
      setCreating(false);
    }
  }

  async function handleSaveProfile() {
    if (!editingUser) return;
    if (!form.emp_id.trim()) {
      setErr("이름은 필수입니다.");
      return;
    }
    setUpdating(true);
    setErr("");
    try {
      await api.patch(`/api/users/${editingUser.emp_id}`, {
        emp_id: canManageRoles ? form.emp_id.trim() : editingUser.emp_id,
        department: editingUser.department || "미지정",
        division: editingUser.division || "",
        email: editingUser.email || "",
        role: canManageRoles ? form.role : editingUser.role,
        is_vip: !!form.is_vip,
      });
      await loadUsers();
      setEditingUser(null);
      setSuccessMsg("회원 정보가 저장되었습니다.");
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "회원 정보 저장에 실패했습니다."));
    } finally {
      setUpdating(false);
    }
  }

  async function handleToggleStatus(user) {
    const next = !user.is_resigned;
    setSavingId(user.emp_id);
    setErr("");
    try {
      await api.patch(`/api/users/${user.emp_id}/status`, { is_resigned: next });
      await loadUsers();
      setSuccessMsg(next ? "회원이 비활성화되었습니다." : "회원이 활성화되었습니다.");
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "회원 상태 변경에 실패했습니다."));
    } finally {
      setSavingId("");
    }
  }

  async function handleIssueTempPassword(user) {
    setSavingId(user.emp_id);
    setErr("");
    try {
      const { data } = await api.post(`/api/users/${user.emp_id}/issue-temp-password`);
      setTempPwInfo({
        emp_id: data.emp_id,
        temp_password: data.temp_password,
      });
      const copied = await copyText(data.temp_password);
      setSuccessMsg(copied ? "임시 비밀번호가 발급되었고 클립보드에 복사되었습니다." : "임시 비밀번호가 발급되었습니다.");
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "임시 비밀번호 발급에 실패했습니다."));
    } finally {
      setSavingId("");
    }
  }

  async function handleQuickRoleChange(user, nextRole) {
    if (!canManageRoles) return;
    if (!nextRole || nextRole === user.role) return true;
    if (user.emp_id === currentUser?.emp_id) {
      setErr("본인 권한은 회원 목록에서 직접 변경할 수 없습니다.");
      return false;
    }

    setRoleSavingId(user.emp_id);
    setErr("");
    try {
      let updatedUser = null;
      try {
        const { data } = await api.patch(`/api/users/${user.emp_id}/role`, { role: nextRole });
        updatedUser = data;
      } catch (roleOnlyErr) {
        const statusCode = roleOnlyErr?.response?.status;
        if (statusCode !== 404 && statusCode !== 405) {
          throw roleOnlyErr;
        }
        // Backward-compatible fallback when server has not been restarted with /role endpoint.
        const { data } = await api.patch(`/api/users/${user.emp_id}`, {
          emp_id: user.emp_id,
          department: user.department || "미지정",
          division: user.division || "",
          email: user.email || "",
          role: nextRole,
          is_vip: !!user.is_vip,
        });
        updatedUser = data;
      }

      if (updatedUser) {
        setData((prev) => ({
          ...prev,
          items: prev.items.map((it) =>
            it.emp_id === user.emp_id ? { ...it, role: updatedUser.role } : it
          ),
        }));
      }
      setSuccessMsg("회원 권한이 변경되었습니다.");
      return true;
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "권한 변경에 실패했습니다."));
      return false;
    } finally {
      setRoleSavingId("");
    }
  }

  function openRolePopup(user) {
    if (!canManageRoles) return;
    if (user.emp_id === currentUser?.emp_id) {
      setErr("본인 권한은 여기서 변경할 수 없습니다.");
      return;
    }
    setErr("");
    setRolePopupUser(user);
  }

  async function handleRolePopupSelect(nextRole) {
    if (!rolePopupUser) return;
    const target = rolePopupUser;
    // Close immediately so users get instant feedback to their tap/click.
    setRolePopupUser(null);
    await handleQuickRoleChange(target, nextRole);
  }

  async function openAudit(user) {
    setErr("");
    setAuditUserId(user.emp_id);
    setAuditLoading(true);
    setAuditRows([]);
    setAuditActionFilter("ALL");
    try {
      const { data } = await api.get(`/api/users/${user.emp_id}/audit?limit=30`);
      setAuditRows(getItems(data));
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "이력 조회에 실패했습니다."));
    } finally {
      setAuditLoading(false);
    }
  }

  function requestToggleStatus(user) {
    setConfirmState({ open: true, type: "toggle_status", user });
  }

  function requestIssueTempPassword(user) {
    setConfirmState({ open: true, type: "issue_temp_password", user });
  }

  function toggleSelectUser(empId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(empId)) next.delete(empId);
      else next.add(empId);
      return next;
    });
  }

  function toggleSelectAll() {
    const selectable = data.items
      .filter((u) => u.emp_id !== currentUser?.emp_id)
      .map((u) => u.emp_id);
    const allSelected = selectable.length > 0 && selectable.every((id) => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(selectable));
    }
  }

  async function handleBulkDelete() {
    setBulkDeleting(true);
    setErr("");
    const ids = [...selectedIds];
    try {
      const { data: res } = await api.post("/api/users/bulk-delete", { emp_ids: ids });
      setShowBulkDeleteConfirm(false);
      setSelectedIds(new Set());
      await loadUsers();
      setSuccessMsg(`${res.count}명의 회원이 삭제되었습니다.`);
    } catch (e) {
      setErr(toErrorMessage(e.response?.data?.detail, "회원 삭제에 실패했습니다."));
    } finally {
      setBulkDeleting(false);
    }
  }

  async function executeConfirmedAction() {
    const { type, user } = confirmState;
    if (!user) return;
    setConfirmState({ open: false, type: "", user: null });
    if (type === "toggle_status") {
      await handleToggleStatus(user);
      return;
    }
    if (type === "issue_temp_password") {
      await handleIssueTempPassword(user);
    }
  }

  const totalPages = useMemo(() => {
    const pages = Math.ceil((data.total || 0) / pageSize);
    return pages > 0 ? pages : 1;
  }, [data.total, pageSize]);

  const activeFilterBadges = useMemo(() => {
    const badges = [];
    if (keyword.trim()) badges.push(`검색: ${keyword.trim()}`);
    if (role !== "ALL") badges.push(`권한: ${roleLabel[role] || role}`);
    if (status !== "ALL") badges.push(`상태: ${statusLabel[status] || status}`);
    if (firstLogin !== "ALL") badges.push(firstLoginLabel[firstLogin] || `초기비번: ${firstLogin}`);
    if (sortBy !== "created_at" || sortDir !== "desc") {
      const sortField = sortBy === "emp_id"
        ? "이름"
        : sortBy === "role"
            ? "권한"
            : "생성일";
      const sortText = sortDir === "asc" ? "오름차순" : "내림차순";
      badges.push(`정렬: ${sortField} ${sortText}`);
    }
    if (pageSize !== 10) badges.push(`페이지 크기: ${pageSize}`);
    return badges;
  }, [keyword, role, status, firstLogin, sortBy, sortDir, pageSize]);

  const tableColCount = canManageRoles ? 5 : 4;

  return (
    <div className="page-container text-center">
      {successMsg && (
        <div className="fixed right-4 top-4 z-[70] alert-success shadow-lg">
          {successMsg}
        </div>
      )}

      <div className="flex items-end justify-between gap-3">
        <div className="flex-1 text-left">
          <h1 className="page-title">회원 관리</h1>
          <p className="page-subtitle">전체 계정을 조회하고 상태를 확인합니다.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge-blue">총 {data.total}명</span>
          <button className="btn-primary btn btn-sm" onClick={openCreate}>회원 추가</button>
        </div>
      </div>

      {err && <div className="alert-danger">{err}</div>}

      {activeFilterBadges.length > 0 && (
        <div className="card p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-500">적용 필터</span>
            {activeFilterBadges.map((badge) => (
              <span key={badge} className="badge-blue">{badge}</span>
            ))}
          </div>
        </div>
      )}

      <div className="card p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <input
            className="field-input col-span-2 sm:col-span-1 text-center h-[42px]"
            placeholder="이름 검색"
            value={keyword}
            onChange={(e) => { setPage(1); setKeyword(e.target.value); }}
          />

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={role}
            onChange={(e) => { setPage(1); setRole(e.target.value); }}
          >
            <option value="ALL">전체 권한</option>
            <option value="MASTER">마스터</option>
            <option value="ADMIN">관리자</option>
            <option value="GENERAL">일반</option>
            <option value="STUDENT">학생</option>
          </select>

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={status}
            onChange={(e) => { setPage(1); setStatus(e.target.value); }}
          >
            <option value="ALL">전체 상태</option>
            <option value="ACTIVE">활성</option>
            <option value="INACTIVE">비활성</option>
          </select>

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={firstLogin}
            onChange={(e) => { setPage(1); setFirstLogin(e.target.value); }}
          >
            <option value="ALL">초기비번 전체</option>
            <option value="PENDING">변경 필요</option>
            <option value="COMPLETED">변경 완료</option>
          </select>

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={sortBy}
            onChange={(e) => { setPage(1); setSortBy(e.target.value); }}
          >
            <option value="created_at">생성일</option>
            <option value="emp_id">이름</option>
            <option value="role">권한</option>
          </select>

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={sortDir}
            onChange={(e) => { setPage(1); setSortDir(e.target.value); }}
          >
            <option value="desc">내림차순</option>
            <option value="asc">오름차순</option>
          </select>

          <select
            className="field-select text-center h-[42px] [text-align-last:center]"
            value={pageSize}
            onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }}
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}개씩</option>
            ))}
          </select>

          <button
            className={filterButtonClass}
            onClick={() => {
              setPage(1);
              setKeyword("");
              setRole("ALL");
              setStatus("ALL");
              setFirstLogin("ALL");
              setSortBy("created_at");
              setSortDir("desc");
              setPageSize(10);
            }}
          >
            <span className="sm:hidden">초기화</span>
            <span className="hidden sm:inline">필터 초기화</span>
          </button>

          <button
            className={filterButtonClass}
            onClick={handleExportCsv}
            disabled={exporting || loading}
          >
            {exporting ? (
              <>
                <span className="sm:hidden">내보내는 중</span>
                <span className="hidden sm:inline">내보내는 중...</span>
              </>
            ) : (
              <>
                <span className="sm:hidden">CSV</span>
                <span className="hidden sm:inline">CSV 내보내기</span>
              </>
            )}
          </button>

          <button
            className={filterButtonClass}
            onClick={handleCopyShareLink}
            disabled={loading}
          >
            {copiedLink ? (
              <>
                <span className="sm:hidden">복사됨</span>
                <span className="hidden sm:inline">링크 복사됨</span>
              </>
            ) : (
              <>
                <span className="sm:hidden">공유링크</span>
                <span className="hidden sm:inline">공유 링크 복사</span>
              </>
            )}
          </button>
        </div>

      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-6"><span className="spinner" /></div>
        ) : (
          <div className="w-full">
            <table className="data-table table-fixed text-xs sm:text-sm">
              <thead>
                <tr>
                  {canManageRoles && (
                    <th className="!text-center w-10 hidden sm:table-cell">
                      <input
                        type="checkbox"
                        className="cursor-pointer"
                        checked={
                          data.items.length > 0 &&
                          data.items
                            .filter((u) => u.emp_id !== currentUser?.emp_id)
                            .every((u) => selectedIds.has(u.emp_id))
                        }
                        onChange={toggleSelectAll}
                        title="전체 선택"
                      />
                    </th>
                  )}
                  <th className="!text-center w-[28%] sm:w-[30%]">이름</th>
                  <th className="!text-center w-[22%] sm:w-[18%]">권한</th>
                  <th className="!text-center w-[16%] sm:w-[16%]">상태</th>
                  <th className="!text-center w-[34%] sm:w-[36%]">작업</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={tableColCount}>
                      <div className="empty-state py-10">
                        <p className="empty-state-text">등록된 계정이 없습니다.</p>
                      </div>
                    </td>
                  </tr>
                ) : data.items.map((u) => (
                  <tr key={u.emp_id} className={selectedIds.has(u.emp_id) ? "bg-red-50" : ""}>
                    {canManageRoles && (
                      <td className="text-center hidden sm:table-cell">
                        {u.emp_id !== currentUser?.emp_id && (
                          <input
                            type="checkbox"
                            className="cursor-pointer"
                            checked={selectedIds.has(u.emp_id)}
                            onChange={() => toggleSelectUser(u.emp_id)}
                          />
                        )}
                      </td>
                    )}
                    <td className="text-center truncate px-1 sm:px-3">{u.emp_id}</td>
                    <td className="text-center">
                      {canManageRoles ? (
                        <button
                          type="button"
                          className="text-[11px] sm:text-xs font-semibold text-gray-700 underline underline-offset-2 disabled:no-underline disabled:text-gray-400"
                          disabled={
                            loading ||
                            updating ||
                            savingId === u.emp_id ||
                            roleSavingId === u.emp_id ||
                            u.emp_id === currentUser?.emp_id
                          }
                          onClick={() => openRolePopup(u)}
                          title={u.emp_id === currentUser?.emp_id ? "본인 권한은 여기서 변경할 수 없습니다." : "권한 변경 팝업 열기"}
                        >
                          {roleLabel[u.role] || u.role}
                        </button>
                      ) : (
                        <span className="text-[11px] sm:text-xs text-gray-700">{roleLabel[u.role] || u.role}</span>
                      )}
                    </td>
                    <td className="text-center">
                      {u.is_resigned
                        ? <span className="badge-red text-[11px]">비활성</span>
                        : <span className="badge-green text-[11px]">활성</span>}
                    </td>
                    <td className="text-center">
                      <div className="grid grid-cols-2 gap-1 sm:flex sm:flex-nowrap sm:items-center sm:justify-center sm:gap-1">
                        <button
                          className={rowActionButtonClass}
                          disabled={loading || savingId === u.emp_id || updating}
                          onClick={() => openEdit(u)}
                        >
                          수정
                        </button>
                        <button
                          className={rowActionButtonClass}
                          disabled={loading || savingId === u.emp_id || updating}
                          onClick={() => openAudit(u)}
                        >
                          이력
                        </button>
                        <button
                          className={rowActionButtonClass}
                          disabled={loading || savingId === u.emp_id || updating}
                          onClick={() => requestIssueTempPassword(u)}
                        >
                          <span className="sm:hidden">임시비번</span>
                          <span className="hidden sm:inline">임시 비밀번호 발급</span>
                        </button>
                        <button
                          className={`${u.is_resigned ? "btn-secondary" : "btn-danger"} ${rowToggleButtonClass}`}
                          disabled={loading || savingId === u.emp_id || updating}
                          onClick={() => requestToggleStatus(u)}
                        >
                          {savingId === u.emp_id
                            ? <><span className="sm:hidden">처리중</span><span className="hidden sm:inline">처리 중...</span></>
                            : (u.is_resigned
                              ? <><span className="sm:hidden">활성</span><span className="hidden sm:inline">활성화</span></>
                              : <><span className="sm:hidden">비활성</span><span className="hidden sm:inline">비활성화</span></>)}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-gray-400">
          페이지 {page} / {totalPages}
        </p>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary btn btn-sm"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            이전
          </button>
          <button
            className="btn-secondary btn btn-sm"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            다음
          </button>
        </div>
      </div>

      {canManageRoles && selectedIds.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between gap-4 bg-gray-900 px-6 py-4 shadow-2xl">
          <div className="flex items-center gap-3">
            <span className="text-white font-semibold text-sm">
              {selectedIds.size}명 선택됨
            </span>
            <button
              className="text-gray-400 text-xs underline hover:text-white"
              onClick={() => setSelectedIds(new Set())}
            >
              선택 해제
            </button>
          </div>
          <button
            className="btn-danger btn"
            onClick={() => setShowBulkDeleteConfirm(true)}
            disabled={bulkDeleting}
          >
            {bulkDeleting ? "삭제 중..." : `선택한 ${selectedIds.size}명 삭제`}
          </button>
        </div>
      )}

      {editingUser && (
        <div
          className="modal-overlay"
          onClick={() => { if (!updating) setEditingUser(null); }}
        >
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">회원 정보 수정: {editingUser.emp_id}</h3>
            </div>
            <div className="modal-body space-y-3 text-center">
              <div>
                <label className="field-label text-center">이름</label>
                <input
                  className="field-input text-center"
                  value={form.emp_id}
                  onChange={(e) => setForm((p) => ({ ...p, emp_id: e.target.value }))}
                  disabled={!canManageRoles}
                />
                <p className="field-hint">회원 식별값은 이름과 동일하게 저장됩니다.</p>
              </div>
              <div>
                <label className="field-label text-center">권한</label>
                {canManageRoles ? (
                  <select
                    className="field-select text-center"
                    value={form.role}
                    onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))}
                  >
                    <option value="MASTER">마스터</option>
                    <option value="ADMIN">관리자</option>
                    <option value="GENERAL">일반</option>
                    <option value="STUDENT">학생</option>
                  </select>
                ) : (
                  <div className="field-input text-center bg-gray-50">{roleLabel[editingUser.role] || editingUser.role}</div>
                )}
              </div>
              <label className="inline-flex items-center justify-center gap-2 text-sm text-gray-700 w-full">
                <input
                  type="checkbox"
                  checked={form.is_vip}
                  onChange={(e) => setForm((p) => ({ ...p, is_vip: e.target.checked }))}
                />
                관리자 권한 부여
              </label>
            </div>
            <div className="modal-footer">
              <button
                className="btn-secondary btn"
                disabled={updating}
                onClick={() => setEditingUser(null)}
              >
                취소
              </button>
              <button
                className="btn-primary btn"
                disabled={updating}
                onClick={handleSaveProfile}
              >
                {updating ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}

      {rolePopupUser && (
        <div className="modal-overlay" onClick={() => !roleSavingId && setRolePopupUser(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">권한 선택: {rolePopupUser.emp_id}</h3>
            </div>
            <div className="modal-body space-y-3 text-center">
              <p className="text-sm text-gray-600">아래 권한을 누르면 즉시 변경됩니다.</p>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { value: "MASTER", label: "마스터" },
                  { value: "ADMIN", label: "관리자" },
                  { value: "GENERAL", label: "일반" },
                  { value: "STUDENT", label: "학생" },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={opt.value === rolePopupUser.role ? "btn-secondary btn" : "btn-primary btn"}
                    disabled={!!roleSavingId || opt.value === rolePopupUser.role}
                    onClick={() => handleRolePopupSelect(opt.value)}
                  >
                    {opt.value === rolePopupUser.role ? `${opt.label} (현재)` : opt.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400">권한 변경은 감사 이력에 기록됩니다.</p>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary btn"
                disabled={!!roleSavingId}
                onClick={() => setRolePopupUser(null)}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => { if (!creating) setShowCreate(false); }}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">신규 회원 추가</h3>
            </div>
            <div className="modal-body space-y-3 text-center">
              <div>
                <label className="field-label field-required text-center">이름</label>
                <input
                  className="field-input text-center"
                  placeholder="회원 이름 입력"
                  value={createForm.emp_id}
                  onChange={(e) => setCreateForm((p) => ({ ...p, emp_id: e.target.value }))}
                />
                <p className="field-hint">입력한 이름이 회원 식별값으로 사용됩니다.</p>
              </div>
              <div>
                <label className="field-label text-center">권한</label>
                <select
                  className="field-select text-center"
                  value={createForm.role}
                  onChange={(e) => setCreateForm((p) => ({ ...p, role: e.target.value }))}
                >
                  {creatableRoles.map((roleOption) => (
                    <option key={roleOption} value={roleOption}>{roleLabel[roleOption]}</option>
                  ))}
                </select>
              </div>
              <label className="inline-flex items-center justify-center gap-2 text-sm text-gray-700 w-full">
                <input
                  type="checkbox"
                  checked={createForm.is_vip}
                  onChange={(e) => setCreateForm((p) => ({ ...p, is_vip: e.target.checked }))}
                />
                관리자 권한 부여
              </label>
            </div>
            <div className="modal-footer">
              <button
                className="btn-secondary btn"
                disabled={creating}
                onClick={() => setShowCreate(false)}
              >
                취소
              </button>
              <button
                className="btn-primary btn"
                disabled={creating}
                onClick={handleCreateUser}
              >
                {creating ? "생성 중..." : "생성"}
              </button>
            </div>
          </div>
        </div>
      )}

      {tempPwInfo && (
        <div className="modal-overlay" onClick={() => setTempPwInfo(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">임시 비밀번호 발급 완료</h3>
            </div>
            <div className="modal-body space-y-3 text-center">
              <p className="text-sm text-gray-600">
                아래 임시 비밀번호는 발급과 동시에 클립보드에 복사되었습니다. 바로 전달하면 됩니다.
              </p>
              <div className="card p-4">
                <p className="text-xs text-gray-500 mb-1">이름</p>
                <p className="font-semibold text-gray-800">{tempPwInfo.emp_id}</p>
                <p className="text-xs text-gray-500 mt-3 mb-1">임시 비밀번호</p>
                <p className="font-mono text-lg font-bold text-blue-700">{tempPwInfo.temp_password}</p>
              </div>
              <button className="btn-secondary btn w-full" onClick={() => copyText(tempPwInfo.temp_password)}>
                임시 비밀번호 다시 복사
              </button>
              <p className="text-xs text-gray-400">
                해당 사용자는 다음 로그인 시 비밀번호 변경이 강제됩니다.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-primary btn" onClick={() => setTempPwInfo(null)}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      {auditUserId && (
        <div className="modal-overlay" onClick={() => setAuditUserId("")}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">변경 이력: {auditUserId}</h3>
            </div>
            <div className="modal-body text-center">
              <div className="mb-3 flex items-center justify-between gap-3">
                <p className="text-xs text-gray-500">최근 30건 기준</p>
                <select
                  className="field-select text-center"
                  style={{ width: 180 }}
                  value={auditActionFilter}
                  onChange={(e) => setAuditActionFilter(e.target.value)}
                >
                  <option value="ALL">전체 작업</option>
                  <option value="create_user">회원 생성</option>
                  <option value="update_profile">회원 정보 수정</option>
                  <option value="update_status">회원 상태 변경</option>
                  <option value="issue_temp_password">임시 비밀번호 발급</option>
                </select>
              </div>

              {auditLoading ? (
                <div className="py-6"><span className="spinner" /></div>
              ) : filteredAuditRows.length === 0 ? (
                <div className="empty-state py-8">
                  <p className="empty-state-text">표시할 이력이 없습니다.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="!text-center">시각</th>
                        <th className="!text-center">작업</th>
                        <th className="!text-center">수행자</th>
                        <th className="!text-center">상세</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAuditRows.map((row) => (
                        <tr key={row.id}>
                          <td className="text-center">{formatDateTime(row.created_at)}</td>
                          <td className="text-center">{actionLabel[row.action] || row.action}</td>
                          <td className="text-center">{row.actor_emp_id}</td>
                          <td className="text-center">
                            <span className="text-xs text-gray-500 break-all">
                              {JSON.stringify(row.details || {})}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-primary btn" onClick={() => setAuditUserId("")}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmState.open && (
        <div className="modal-overlay" onClick={() => setConfirmState({ open: false, type: "", user: null })}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title w-full text-center">작업 확인</h3>
            </div>
            <div className="modal-body space-y-2 text-center">
              {confirmState.type === "toggle_status" && (
                <p className="text-sm text-gray-700">
                  <b>{confirmState.user?.emp_id}</b> 계정 상태를 변경하시겠습니까?
                </p>
              )}
              {confirmState.type === "issue_temp_password" && (
                <p className="text-sm text-gray-700">
                  <b>{confirmState.user?.emp_id}</b> 계정의 임시 비밀번호를 새로 발급하시겠습니까?
                </p>
              )}
              <p className="text-xs text-gray-400">이 작업은 감사 이력에 기록됩니다.</p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-secondary btn"
                onClick={() => setConfirmState({ open: false, type: "", user: null })}
              >
                취소
              </button>
              <button className="btn-primary btn" onClick={executeConfirmedAction}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      {showBulkDeleteConfirm && (
        <div className="modal-overlay" onClick={() => !bulkDeleting && setShowBulkDeleteConfirm(false)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header border-b-2 border-red-200 bg-red-50">
              <h3 className="modal-title w-full text-center text-red-700">⚠ 회원 일괄 삭제</h3>
            </div>
            <div className="modal-body space-y-4 text-center">
              <div className="rounded-lg bg-red-50 border border-red-300 p-4">
                <p className="text-lg font-bold text-red-700 mb-2">{selectedIds.size}명</p>
                <p className="text-sm text-red-600">선택한 회원을 모두 삭제하시겠습니까?</p>
                <p className="text-xs text-red-500 mt-2">삭제된 데이터는 복구할 수 없습니다.</p>
              </div>
              <div className="text-xs text-gray-500 max-h-28 overflow-y-auto text-left px-1">
                {[...selectedIds].map((id) => {
                  const u = data.items.find((x) => x.emp_id === id);
                  return <div key={id}>{u ? u.emp_id : id}</div>;
                })}
              </div>
              <p className="text-xs text-gray-400">이 작업은 감사 이력에 기록됩니다.</p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-secondary btn"
                disabled={bulkDeleting}
                onClick={() => setShowBulkDeleteConfirm(false)}
              >
                취소
              </button>
              <button
                className="btn-danger btn"
                disabled={bulkDeleting}
                onClick={handleBulkDelete}
              >
                {bulkDeleting ? "삭제 중..." : "삭제 확인"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
