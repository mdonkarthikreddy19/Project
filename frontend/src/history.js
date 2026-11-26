// Last few checks, kept in this browser only. Summaries only: no images are saved.
const KEY = 'receiptcheck.history'
const MAX = 6

export function loadHistory() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

export function saveHistory(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch {
    // storage full or blocked (private mode); history just won't persist
  }
}

export function addEntry(list, entry) {
  return [entry, ...list].slice(0, MAX)
}

export function timeAgo(ts) {
  const s = Math.round((Date.now() - ts) / 1000)
  if (s < 60) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
