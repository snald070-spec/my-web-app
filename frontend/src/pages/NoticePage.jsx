import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../api";
import { getItems, getTotal } from "../utils/apiHelpers";

export default function NoticePage() {
  const { user } = useAuth();
  const isAdmin = ["MASTER", "ADMIN"].includes(user?.role);

  const [data, setData] = useState({ items: [], total: 0, skip: 0, limit: 10 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [sortDir, setSortDir] = useState("desc");
  const [showEditor, setShowEditor] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ title: "", body: "", is_pinned: false });

  const limit = 10;
  const skip = (page - 1) * limit;

  async function loadNotices() {
    setLoading(true);
    setErr("");
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
      keyword: keyword.trim(),
      sort_dir: sortDir,
    });

    try {
      const { data: payload } = await api.get(`/api/notices?${params.toString()}`);
      setData({
        items: getItems(payload),
        total: getTotal(payload),
        skip: payload?.skip ?? skip,
        limit: payload?.limit ?? limit,
      });
    } catch (e) {
      setErr(e.response?.data?.detail || "공지사항을 불러오지 못했습니다.");
      setData({ items: [], total: 0, skip, limit });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadNotices();
  }, [skip, sortDir, keyword]);

  useEffect(() => {
    if (!successMsg) return undefined;
    const t = setTimeout(() => setSuccessMsg(""), 1800);
    return () => clearTimeout(t);
  }, [successMsg]);

  const totalPages = useMemo(() => {
    const pages = Math.ceil((data.total || 0) / limit);
    return pages > 0 ? pages : 1;
  }, [data.total]);

  function openCreate() {
    setEditing(null);
    setForm({ title: "", body: "", is_pinned: false });
    setShowEditor(true);
  }

  function openEdit(row) {
    setEditing(row);
    setForm({ title: row.title || "", body: row.body || "", is_pinned: !!row.is_pinned });
    setShowEditor(true);
  }

  async function saveNotice() {
    if (!form.title.trim() || !form.body.trim()) {
      setErr("제목과 내용을 입력해주세요.");
      return;
    }

    setSaving(true);
    setErr("");
    try {
      const body = {
        title: form.title.trim(),
        body: form.body.trim(),
        is_pinned: !!form.is_pinned,
      };

      if (editing) {
        await api.patch(`/api/notices/${editing.id}`, body);
        setSuccessMsg("공지사항이 수정되었습니다.");
      } else {
        await api.post("/api/notices", body);
        setSuccessMsg("공지사항이 등록되었습니다.");
      }

      setShowEditor(false);
      await loadNotices();
    } catch (e) {
      setErr(e.response?.data?.detail || "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function removeNotice(row) {
    const ok = window.confirm(`공지사항 \"${row.title}\"을 삭제하시겠습니까?`);
    if (!ok) return;

    setErr("");
    try {
      await api.delete(`/api/notices/${row.id}`);
      setSuccessMsg("공지사항이 삭제되었습니다.");
      await loadNotices();
    } catch (e) {
      setErr(e.response?.data?.detail || "삭제에 실패했습니다.");
    }
  }

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
      hour12: false,
    });
  };

  return (
    <div className="page-container">
      {successMsg && <div className="fixed right-4 top-4 z-[70] alert-success shadow-lg">{successMsg}</div>}

      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="page-title">공지사항</h1>
          <p className="page-subtitle">운영 공지를 확인하고 공유합니다.</p>
        </div>
        {isAdmin && (
          <button className="btn-primary btn btn-sm" onClick={openCreate}>
            공지 등록
          </button>
        )}
      </div>

      {err && <div className="alert-danger">{err}</div>}

      <div className="card p-4">
        <div className="action-bar">
          <input
            className="field-input"
            style={{ maxWidth: 320 }}
            placeholder="제목/내용 검색"
            value={keyword}
            onChange={(e) => { setPage(1); setKeyword(e.target.value); }}
          />
          <select
            className="field-select"
            style={{ width: 120 }}
            value={sortDir}
            onChange={(e) => { setPage(1); setSortDir(e.target.value); }}
          >
            <option value="desc">최신순</option>
            <option value="asc">오래된순</option>
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-6"><span className="spinner" /></div>
        ) : (
          <div className="overflow-x-auto w-full">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 90 }}>고정</th>
                  <th>제목</th>
                  <th>작성자</th>
                  <th>등록일</th>
                  {isAdmin && <th>작업</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 5 : 4}>
                      <div className="empty-state py-10">
                        <p className="empty-state-text">등록된 공지사항이 없습니다.</p>
                      </div>
                    </td>
                  </tr>
                ) : data.items.map((row) => (
                  <tr key={row.id}>
                    <td>{row.is_pinned ? <span className="badge-yellow">고정</span> : <span className="badge-gray">일반</span>}</td>
                    <td>
                      <p className="font-semibold text-gray-800">{row.title}</p>
                      <p className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{row.body}</p>
                    </td>
                    <td>{row.created_by}</td>
                    <td>{formatDateTime(row.created_at)}</td>
                    {isAdmin && (
                      <td>
                        <div className="flex items-center gap-2">
                          <button className="btn-secondary btn btn-sm" onClick={() => openEdit(row)}>수정</button>
                          <button className="btn-danger btn btn-sm" onClick={() => removeNotice(row)}>삭제</button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-gray-400">페이지 {page} / {totalPages}</p>
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

      {showEditor && (
        <div className="modal-overlay" onClick={() => { if (!saving) setShowEditor(false); }}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">{editing ? "공지사항 수정" : "공지사항 등록"}</h3>
            </div>
            <div className="modal-body space-y-3">
              <div>
                <label className="field-label field-required">제목</label>
                <input
                  className="field-input"
                  value={form.title}
                  onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                />
              </div>
              <div>
                <label className="field-label field-required">내용</label>
                <textarea
                  className="field-textarea"
                  rows={6}
                  value={form.body}
                  onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))}
                />
              </div>
              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={form.is_pinned}
                  onChange={(e) => setForm((p) => ({ ...p, is_pinned: e.target.checked }))}
                />
                상단 고정
              </label>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary btn" disabled={saving} onClick={() => setShowEditor(false)}>
                취소
              </button>
              <button className="btn-primary btn" disabled={saving} onClick={saveNotice}>
                {saving ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
