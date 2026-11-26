const TIMEOUT_MS = 90_000
// Empty when the backend serves this page; set VITE_API_BASE when the page is hosted elsewhere (GitHub Pages).
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

async function request(path, options) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  let res
  try {
    res = await fetch(API_BASE + path, { ...options, signal: ctrl.signal })
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('The check took too long. Try a smaller screenshot or try again.')
    }
    throw new Error("Can't reach the checker. Check your internet connection and try again.")
  } finally {
    clearTimeout(timer)
  }
  let body = null
  try {
    body = await res.json()
  } catch {
    // non-JSON error page (proxy, server crash)
  }
  if (!res.ok) {
    const detail = body && typeof body.detail === 'string' ? body.detail : null
    throw new Error(detail || `Something went wrong on the server (${res.status}). Try again in a moment.`)
  }
  return body
}

export function checkImage(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/api/check/image', { method: 'POST', body: form })
}

export function checkLink(url) {
  return request('/api/check/link', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
}
