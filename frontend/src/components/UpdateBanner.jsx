import { useEffect, useState } from 'react'
import { updateSW, _updateReady } from '../main'

export default function UpdateBanner() {
  const [show, setShow] = useState(false)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    // React 마운트 전에 이미 업데이트가 감지됐을 경우 처리
    if (_updateReady) {
      setShow(true)
      return
    }
    function onUpdate() { setShow(true) }
    window.addEventListener('pwa-update-available', onUpdate)
    return () => window.removeEventListener('pwa-update-available', onUpdate)
  }, [])

  if (!show) return null

  async function handleUpdate() {
    setUpdating(true)
    await updateSW(true)
  }

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
      <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-3.5 flex items-center gap-3">
        <img src="/icon-192.png" alt="" className="w-8 h-8 object-contain shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold leading-tight">앱 업데이트가 있습니다</p>
          <p className="text-xs text-gray-400 mt-0.5">새 버전으로 업데이트하세요.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShow(false)}
            className="text-xs text-gray-400 hover:text-white px-2 py-1.5 rounded-lg transition-colors"
          >
            나중에
          </button>
          <button
            onClick={handleUpdate}
            disabled={updating}
            className="bg-white text-gray-900 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-60 transition-colors"
          >
            {updating ? '업데이트 중...' : '업데이트'}
          </button>
        </div>
      </div>
    </div>
  )
}
