/**
 * Admin "View as Employee" toggle components.
 *
 * Usage pattern:
 *   1. In admin view:    <PreviewToggleButton onPreview={() => setPreviewMode(true)} />
 *   2. In employee view: <PreviewModeBanner onReturn={() => setPreviewMode(false)} />
 *   3. Gate admin-only UI with: const isAdmin = !previewMode && user?.role === "ADMIN"
 */

/** Button shown inside the admin view to enter preview mode */
export function PreviewToggleButton({ onPreview }) {
  return (
    <div className="flex justify-end mb-3">
      <button
        onClick={onPreview}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                   bg-amber-50 text-amber-700 border border-amber-200 rounded-full
                   hover:bg-amber-100 active:scale-95 transition-all shadow-sm"
      >
        <span>👁️</span> 일반 회원 화면으로 보기
      </button>
    </div>
  );
}

/** Sticky banner shown at top of page when preview mode is active */
export function PreviewModeBanner({ onReturn }) {
  return (
    <div className="sticky top-0 z-50 flex items-center justify-between gap-3
                    bg-amber-500 text-white px-4 py-2.5 shadow-md">
      <span className="flex items-center gap-2 text-sm font-medium">
        <span className="text-lg">👁️</span>
        <strong>일반 회원 미리보기 모드</strong>
        <span className="hidden sm:inline"> - 관리자 기능이 숨겨져 있습니다.</span>
      </span>
      <button
        onClick={onReturn}
        className="shrink-0 inline-flex items-center gap-1.5 px-4 py-1.5
                   bg-white text-amber-700 rounded-full text-sm font-semibold
                   hover:bg-amber-50 active:scale-95 transition-all shadow-sm"
      >
        ← 관리자 화면으로 돌아가기
      </button>
    </div>
  );
}
