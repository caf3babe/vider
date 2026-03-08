const BASE = '/api'

export async function fetchInfo(url) {
  const res = await fetch(`${BASE}/info?url=${encodeURIComponent(url)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to fetch video info')
  return data
}

export function downloadUrl(url, formatId) {
  return `${BASE}/download?url=${encodeURIComponent(url)}&format_id=${encodeURIComponent(formatId)}`
}
