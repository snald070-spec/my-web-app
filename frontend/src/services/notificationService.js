import api from '../api'

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)))
}

export async function requestAndSubscribe() {
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { ok: false, reason: 'unsupported' }
  }

  // 이미 거부된 경우 재요청 불가
  if (Notification.permission === 'denied') {
    return { ok: false, reason: 'denied' }
  }

  // 권한 요청
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    return { ok: false, reason: 'not_granted' }
  }

  try {
    // 서버에서 VAPID public key 가져오기
    const { data } = await api.get('/api/notifications/vapid-public-key')
    const applicationServerKey = _urlBase64ToUint8Array(data.publicKey)

    // Service Worker 등록 완료 대기
    const registration = await navigator.serviceWorker.ready

    // Push 구독
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    })

    const subJson = subscription.toJSON()
    await api.post('/api/notifications/subscribe', {
      endpoint: subJson.endpoint,
      keys: subJson.keys,
    })

    localStorage.setItem('pushSubscribed', '1')
    return { ok: true }
  } catch (e) {
    console.warn('[Push] 구독 실패:', e)
    return { ok: false, reason: 'error', error: e }
  }
}

export async function unsubscribe() {
  try {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (!subscription) return

    await api.delete('/api/notifications/unsubscribe', {
      data: { endpoint: subscription.endpoint },
    })
    await subscription.unsubscribe()
    localStorage.removeItem('pushSubscribed')
  } catch (e) {
    console.warn('[Push] 구독 해제 실패:', e)
  }
}

export function isSubscribed() {
  return localStorage.getItem('pushSubscribed') === '1'
}
