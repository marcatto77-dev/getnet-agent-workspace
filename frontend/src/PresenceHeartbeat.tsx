import { useEffect } from 'react'
import { api } from './api'

// Each tab has its own lease; closing one must not disconnect another tab.
export function PresenceHeartbeat() {
  useEffect(() => {
    if (['/login', '/change-password'].includes(location.pathname)) return
    const sessionId = crypto.randomUUID()
    let stopped = false
    const heartbeat = () => {
      if (!stopped) void api('/auth/presence', { method: 'POST', body: JSON.stringify({ session_id: sessionId, active: true }) }).catch(() => undefined)
    }
    const close = () => {
      navigator.sendBeacon('/api/auth/presence', new Blob([JSON.stringify({ session_id: sessionId, active: false })], { type: 'application/json' }))
    }
    const resume = () => heartbeat()
    const visible = () => { if (document.visibilityState === 'visible') heartbeat() }
    const initial = window.setTimeout(heartbeat, 0)
    const timer = window.setInterval(heartbeat, 30_000)
    window.addEventListener('pagehide', close)
    window.addEventListener('pageshow', resume)
    window.addEventListener('focus', resume)
    document.addEventListener('visibilitychange', visible)
    return () => {
      stopped = true
      clearTimeout(initial)
      clearInterval(timer)
      window.removeEventListener('pagehide', close)
      window.removeEventListener('pageshow', resume)
      window.removeEventListener('focus', resume)
      document.removeEventListener('visibilitychange', visible)
      close()
    }
  }, [])
  return null
}
