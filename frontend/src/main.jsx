import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App.jsx'

// Service Worker 등록 — 새 버전 감지 시 UpdateBanner 에 알림
// _updateReady: React 마운트 전에 이벤트가 발화해도 유실되지 않도록 모듈 변수로 보존
export let _updateReady = false

export const updateSW = registerSW({
  onNeedRefresh() {
    _updateReady = true
    window.dispatchEvent(new CustomEvent('pwa-update-available'))
  },
  onOfflineReady() {},
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
