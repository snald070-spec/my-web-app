import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App.jsx'

// Service Worker 등록 — autoUpdate 모드로 백그라운드 업데이트
// updateSW 함수는 UpdateBanner 컴포넌트에서 사용
export const updateSW = registerSW({
  onNeedRefresh() {
    // 새 버전 감지 → window 이벤트로 전파 (UpdateBanner 가 수신)
    window.dispatchEvent(new CustomEvent('pwa-update-available'))
  },
  onOfflineReady() {
    console.log('[PWA] 오프라인 준비 완료')
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
