import { useEffect, useState } from 'react'

function isInStandaloneMode() {
  return window.matchMedia('(display-mode: standalone)').matches || !!navigator.standalone
}
function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream
}
function isSamsungBrowser() {
  return /SamsungBrowser/i.test(navigator.userAgent)
}
function isAndroid() {
  return /Android/i.test(navigator.userAgent)
}

const SESSION_KEY = 'pwa-install-hidden'

export default function InstallBanner() {
  const [visible, setVisible] = useState(false)
  const [mode, setMode] = useState(null)
  // 'samsung-manual' | 'chrome-guide' | 'android-prompt' | 'android-manual' | 'ios'
  const [deferredPrompt, setDeferredPrompt] = useState(null)

  useEffect(() => {
    if (isInStandaloneMode()) return
    if (sessionStorage.getItem(SESSION_KEY)) return

    if (isIOS()) {
      setMode('ios'); setVisible(true); return
    }

    if (!isAndroid()) return // 데스크탑 제외

    if (isSamsungBrowser()) {
      // 삼성 인터넷: 메뉴 바로가기 방식 안내 (WebAPK 아님 → Play Protect 없음)
      setMode('samsung-manual'); setVisible(true); return
    }

    // Chrome / 기타 Android 브라우저
    // beforeinstallprompt 캡처는 하되, prompt() 는 Samsung Internet 유도 후 마지막 수단으로만 사용
    let timer
    function onBeforeInstall(e) {
      e.preventDefault()
      clearTimeout(timer)
      setDeferredPrompt(e)
      setMode('chrome-guide')
      setVisible(true)
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    timer = setTimeout(() => {
      if (!deferredPrompt) { setMode('android-manual'); setVisible(true) }
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

  async function handleChromeInstall() {
    // Chrome WebAPK 방식 — Play Protect 경고가 뜰 수 있음을 인지한 상태에서 시도
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    setDeferredPrompt(null)
    if (outcome === 'accepted') setVisible(false)
  }

  if (!visible) return null

  // ── 삼성 인터넷: 홈 화면에 추가 ──────────────────────────────────────────
  if (mode === 'samsung-manual') {
    return (
      <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
        <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-4">
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <img src="/icon-192.png" alt="" className="w-7 h-7 object-contain shrink-0" />
              <p className="text-sm font-bold">홈 화면에 앱 추가하기</p>
            </div>
            <button onClick={dismiss} className="text-gray-400 hover:text-white text-xl leading-none shrink-0 -mt-0.5">✕</button>
          </div>

          {/* Step 1 */}
          <div className="flex gap-2.5 mb-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">1</span>
            <p className="text-xs text-gray-300 leading-relaxed">
              화면 <span className="text-white font-semibold">맨 아래 오른쪽</span>{' '}
              <span className="bg-gray-700 text-white text-xs px-1.5 py-0.5 rounded font-mono">⋮</span>{' '}
              버튼 탭
            </p>
          </div>

          {/* Step 2 */}
          <div className="flex gap-2.5 mb-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">2</span>
            <p className="text-xs text-gray-300 leading-relaxed">
              메뉴에서{' '}
              <span className="text-white font-semibold">"페이지 추가"</span> 탭
            </p>
          </div>

          {/* Step 3 */}
          <div className="flex gap-2.5">
            <span className="shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">3</span>
            <p className="text-xs text-gray-300 leading-relaxed">
              <span className="text-white font-semibold">"홈 화면"</span>{' '}
              선택 → <span className="text-white font-semibold">"추가"</span> 탭
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Chrome: 삼성 인터넷 경유 권장 ─────────────────────────────────────────
  if (mode === 'chrome-guide') {
    return (
      <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-sm">
        <div className="bg-gray-900 text-white rounded-2xl shadow-2xl px-4 py-4">
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <img src="/icon-192.png" alt="" className="w-7 h-7 object-contain shrink-0" />
              <p className="text-sm font-bold">홈 화면에 앱 추가하기</p>
            </div>
            <button onClick={dismiss} className="text-gray-400 hover:text-white text-lg leading-none shrink-0">✕</button>
          </div>

          {/* 권장: 삼성 인터넷 */}
          <div className="bg-blue-800 rounded-xl px-3 py-2.5 mb-2">
            <p className="text-xs font-bold text-blue-200 mb-1">✅ 권장 방법 (Play Protect 없음)</p>
            <p className="text-xs text-white leading-relaxed">
              <span className="font-semibold">삼성 인터넷</span> 앱으로 접속 →{' '}
              하단 <span className="font-semibold">⋮</span> →{' '}
              페이지 추가 → <span className="font-semibold">홈 화면</span>
            </p>
          </div>

          {/* 대안: 크롬 직접 설치 */}
          <div className="flex items-center justify-between gap-2 mt-2">
            <p className="text-xs text-gray-400">크롬으로 직접 설치 (Play Protect 경고 가능)</p>
            <button
              onClick={handleChromeInstall}
              className="shrink-0 bg-white text-gray-900 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              그래도 설치
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Android 수동 (beforeinstallprompt 없음) ───────────────────────────────
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
            <span className="text-white font-semibold">삼성 인터넷</span> 앱으로 접속 →{' '}
            하단 <span className="text-white font-semibold">≡</span> → 추가 →{' '}
            <span className="text-white font-semibold">홈 화면</span> 선택
          </p>
        </div>
      </div>
    )
  }

  // ── iOS Safari ─────────────────────────────────────────────────────────────
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
