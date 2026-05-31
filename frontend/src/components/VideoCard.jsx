import { useState } from 'react'
import { download, downloadAudio, getThumbnailUrl, isYouTubeUrl } from '../api'

function formatDuration(secs) {
  if (!secs) return null
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSize(bytes) {
  if (!bytes) return null
  if (bytes > 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  return `${(bytes / 1_000).toFixed(0)} KB`
}

function qualityLabel(fmt) {
  if (fmt.height) return `${fmt.height}p`
  return fmt.format_id
}

export default function VideoCard({ info }) {
  const [downloading, setDownloading] = useState(null)
  const [error, setError] = useState(null)
  const sourceUrl = info.url
  const isYT = isYouTubeUrl(sourceUrl || '')

  const handleDownload = async (formatId, formatType = 'video') => {
    setDownloading(formatId)
    setError(null)
    try {
      await download(sourceUrl, formatId, formatType)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloading(null)
    }
  }

  const handleAudioDownload = async () => {
    setDownloading('audio')
    setError(null)
    try {
      await downloadAudio(sourceUrl)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="w-full border-3 border-black bg-white">
      <div className="flex gap-4 p-6">
        {info.thumbnail && (
          <img
            src={getThumbnailUrl(sourceUrl)}
            alt="thumbnail"
            className="h-24 w-24 object-cover shrink-0"
          />
        )}
        <div className="flex flex-col justify-center gap-2 min-w-0">
          <p className="font-black text-black truncate text-sm">{info.title}</p>
          {info.uploader && (
            <p className="text-xs text-black/60">@{info.uploader}</p>
          )}
          {info.duration && (
            <p className="font-mono text-xs text-black/50">{formatDuration(info.duration)}</p>
          )}
        </div>
      </div>

      <div className="border-t-3 border-black"></div>

      <div className="px-6 py-4">
        <p className="mb-3 text-xs font-black text-black uppercase tracking-widest">Formats</p>

        {error && (
          <div className="mb-3 border-3 border-red-600 bg-white px-3 py-2 text-xs text-red-600 font-semibold">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {isYT && (
            <button
              onClick={handleAudioDownload}
              disabled={downloading !== null}
              className="border-3 border-black bg-black text-white px-3 py-2 text-xs font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition"
            >
              {downloading === 'audio' ? 'Downloading…' : 'Download MP3'}
            </button>
          )}
          {info.formats && info.formats.length > 0 ? (
            info.formats.map((fmt) => (
              <button
                key={fmt.format_id}
                onClick={() => handleDownload(fmt.format_id, 'video')}
                disabled={downloading !== null}
                className="border-3 border-black bg-black text-white px-3 py-2 text-xs font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition"
              >
                {downloading === fmt.format_id ? (
                  <span>Downloading…</span>
                ) : (
                  <>
                    <span>{qualityLabel(fmt)}</span>
                    {fmt.filesize && (
                      <span className="text-white/70 text-xs"> · {formatSize(fmt.filesize)}</span>
                    )}
                  </>
                )}
              </button>
            ))
          ) : (
            <button
              onClick={() => handleDownload('best', 'video')}
              disabled={downloading !== null}
              className="border-3 border-black bg-black text-white px-4 py-2 text-xs font-black uppercase tracking-wide hover:bg-white hover:text-black transition disabled:opacity-50"
            >
              {downloading ? 'Downloading…' : 'Best Quality'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
