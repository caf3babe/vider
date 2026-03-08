const BASE = '/api'

export async function fetchInfo(url) {
  const res = await fetch(`${BASE}/info?url=${encodeURIComponent(url)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to fetch video info')
  return data
}

export function getThumbnailUrl(url) {
  return `${BASE}/thumbnail?url=${encodeURIComponent(url)}`
}

export async function download(url, formatId) {
  try {
    const res = await fetch(`${BASE}/download?url=${encodeURIComponent(url)}&format_id=${encodeURIComponent(formatId)}`)
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || 'Download failed')
    }
    
    const blob = await res.blob()
    const contentDisposition = res.headers.get('content-disposition')
    let filename = 'video.mp4'
    
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/)
      if (match) filename = match[1]
    }
    
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
  } catch (err) {
    throw new Error(err.message || 'Download failed')
  }
}
