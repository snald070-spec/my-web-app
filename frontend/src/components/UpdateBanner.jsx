import { useEffect, useState } from 'react'
import { updateSW } from '../main'

export default function UpdateBanner() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    function onUpdate() { setShow(true) }
    window.addEventListener('pwa-update-available', onUpdate)
    return () => window.removeEventListener('pwa-update-available', onUpdate)
  }, [])

  if (!show) return null

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
      <div className="bg-blue-600 text-white rounded-2xl shadow-xl px-4 py-3 flex items-center justify-between gap-3">
        <span className="text-sm font-medium">🚀 새 버전이 있습니다</span>
        <button
          onClick={() => updateSW(true)}
          className="shrink-0 bg-white text-blue-600 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors"
        >
          지금 업데이트
        </button>
      </div>
    </div>
  )
}
