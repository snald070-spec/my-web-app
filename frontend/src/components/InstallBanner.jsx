import { useEffect, useState } from 'react'

function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream
}

function isInStandaloneMode() {
  return window.matchMedia('(display-mode: standalone)').matches || !!navigator.standalone
}

const DISMISSED_KEY = 'pwa-install-dismissed'

export default function InstallBanner() {
  const [mode, setMode] = useState(null) // null | 'android' | 'ios'
  const [deferredPrompt, setDeferredPrompt] = useState(null)

  useEffect(() => {
    if (isInStandaloneMode()) return
    if (localStorage.getItem(DISMISSED_KEY)) return

    if (isIOS()) {
      setMode('ios')
      return
    }

    function onBeforeInstall(e) {
      e.preventDefault()
      setDeferredPrompt(e)
      setMode('android')
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    return () => window.removeEventListener('beforeinstallprompt', onBeforeInstall)
  }, [])

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, '1')
    setMode(null)
    setDeferredPrompt(null)
  }

  async function handleInstall() {
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    setDeferredPrompt(null)
    if (outcome === 'accepted') dismiss()
    else setMode(null)
  }

  if (!mode) return null

  if (mode === 'android') {
    return (
      <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm pointer-events-auto">
        <div className="bg-blue-900 text-white rounded-2xl shadow-2xl px-4 py-3 flex items-center gap-3">
          <span className="text-2xl shrink-0">🏀</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold leading-tight">Draw Basketball Team 설치</p>
            <p className="text-xs text-blue-200 mt-0.5">앱으로 설치하면 알림 · 빠른 실행이 가능합니다</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={dismiss}
              className="text-xs text-blue-300 hover:text-white px-1 py-1 transition-colors"
            >
              나중에
            </button>
            <button
              onClick={handleInstall}
              className="bg-white text-blue-900 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors"
            >
              설치
            </button>
          </div>
        </div>
      </div>
    )
  }

  // iOS
  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm pointer-events-auto">
      <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-bold">🏀 홈 화면에 추가하기 (iPhone)</p>
            <p className="text-xs text-gray-300 mt-1 leading-relaxed">
              Safari 하단 <b className="text-white">공유 버튼 (□↑)</b> 탭 →<br />
              <b className="text-white">홈 화면에 추가</b> 선택
            </p>
          </div>
          <button
            onClick={dismiss}
            className="text-gray-400 hover:text-white text-xl leading-none shrink-0 mt-0.5"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}
