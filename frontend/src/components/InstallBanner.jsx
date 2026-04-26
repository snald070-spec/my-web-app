import { useEffect, useState } from 'react'

function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream
}

function isInStandaloneMode() {
  return window.matchMedia('(display-mode: standalone)').matches || !!navigator.standalone
}

// 이번 세션에서만 숨기기 (재방문 시 다시 표시)
const SESSION_KEY = 'pwa-install-hidden'

export default function InstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState(null)
  const [visible, setVisible] = useState(false)
  const [mode, setMode] = useState(null) // 'android-prompt' | 'android-manual' | 'ios'

  useEffect(() => {
    if (isInStandaloneMode()) return
    if (sessionStorage.getItem(SESSION_KEY)) return

    if (isIOS()) {
      setMode('ios')
      setVisible(true)
      return
    }

    // Android/Chrome: beforeinstallprompt 이벤트 대기 (최대 3초)
    let timer
    function onBeforeInstall(e) {
      e.preventDefault()
      clearTimeout(timer)
      setDeferredPrompt(e)
      setMode('android-prompt')
      setVisible(true)
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)

    // 3초 내 이벤트 없으면 수동 설치 안내
    timer = setTimeout(() => {
      if (!deferredPrompt) {
        setMode('android-manual')
        setVisible(true)
      }
    }, 3000)

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      clearTimeout(timer)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function dismiss() {
    sessionStorage.setItem(SESSION_KEY, '1')
    setVisible(false)
  }

  async function handleInstall() {
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    setDeferredPrompt(null)
    if (outcome === 'accepted') setVisible(false)
  }

  if (!visible) return null

  if (mode === 'android-prompt') {
    return (
      <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
        <div className="bg-blue-900 text-white rounded-2xl shadow-2xl px-4 py-3 flex items-center gap-3">
          <img src="/icon-192.png" alt="" className="w-8 h-8 object-contain shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold leading-tight">앱으로 설치하기</p>
            <p className="text-xs text-blue-200 mt-0.5">알림 · 빠른 실행 · 오프라인 지원</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={dismiss} className="text-xs text-blue-300 hover:text-white px-1 py-1 transition-colors">
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

  if (mode === 'android-manual') {
    return (
      <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
        <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-3.5">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2">
              <img src="/icon-192.png" alt="" className="w-7 h-7 object-contain shrink-0" />
              <p className="text-sm font-bold">홈 화면에 앱 추가하기</p>
            </div>
            <button onClick={dismiss} className="text-gray-400 hover:text-white text-lg leading-none shrink-0">✕</button>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            브라우저 우측 상단 <span className="text-white font-semibold">⋮ 메뉴</span> 탭 →{' '}
            <span className="text-white font-semibold">"홈 화면에 추가"</span> 또는{' '}
            <span className="text-white font-semibold">"앱 설치"</span> 선택
          </p>
        </div>
      </div>
    )
  }

  // iOS
  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
      <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-3.5">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <img src="/icon-192.png" alt="" className="w-7 h-7 object-contain shrink-0" />
            <p className="text-sm font-bold">홈 화면에 앱 추가하기</p>
          </div>
          <button onClick={dismiss} className="text-gray-400 hover:text-white text-lg leading-none shrink-0">✕</button>
        </div>
        <p className="text-xs text-gray-300 leading-relaxed">
          Safari 하단 <span className="text-white font-semibold">공유 버튼 (□↑)</span> 탭 →{' '}
          <span className="text-white font-semibold">홈 화면에 추가</span> 선택
        </p>
      </div>
    </div>
  )
}
