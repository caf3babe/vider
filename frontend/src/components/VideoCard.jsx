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

export default function VideoCard({ info, sourceUrl }) {
  const [downloading, setDownloading] = useState(null)
  const [error, setError] = useState(null)
  const isYT = isYouTubeUrl(sourceUrl)

  const handleDownload = async (formatId) => {
    setDownloading(formatId)
    setError(null)
    try {
      await download(sourceUrl, formatId)
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
    <div className="w-full rounded-2xl border border-white/10 bg-white/5 overflow-hidden">
      <div className="flex gap-4 p-4">
        {info.thumbnail && (
          <img
            src={getThumbnailUrl(sourceUrl)}
            alt="thumbnail"
            className="h-24 w-24 rounded-xl object-cover shrink-0"
          />
        )}
        <div className="flex flex-col justify-center gap-1 min-w-0">
          <p className="font-semibold text-white truncate">{info.title}</p>
          {info.uploader && (
            <p className="text-sm text-white/50">@{info.uploader}</p>
          )}
          {info.duration && (
            <p className="text-xs text-white/40">{formatDuration(info.duration)}</p>
          )}
        </div>
      </div>

      <div className="border-t border-white/10 px-4 py-3">
        <p className="mb-2 text-xs font-medium text-white/40 uppercase tracking-wider">Download</p>
        
        {error && (
          <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            {error}
          </div>
        )}
        
        <div className="flex flex-wrap gap-2">
          {isYT ? (
            <button
              onClick={handleAudioDownload}
              disabled={downloading !== null}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-1.5 text-sm font-semibold text-white hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {downloading === 'audio' ? (
                <>
                  <span className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  <span>Downloading…</span>
                </>
              ) : (
                'Download MP3'
              )}
            </button>
          ) : info.formats.length > 0 ? (
            info.formats.map((fmt) => (
              <button
                key={fmt.format_id}
                onClick={() => handleDownload(fmt.format_id)}
                disabled={downloading !== null}
                className="flex items-center gap-1.5 rounded-lg bg-white/10 hover:bg-purple-600 px-3 py-1.5 text-sm font-medium text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {downloading === fmt.format_id ? (
                  <>
                    <span className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>Downloading…</span>
                  </>
                ) : (
                  <>
                    <span>{qualityLabel(fmt)}</span>
                    {fmt.filesize && (
                      <span className="text-white/50 text-xs">· {formatSize(fmt.filesize)}</span>
                    )}
                  </>
                )}
              </button>
            ))
          ) : (
            <button
              onClick={() => handleDownload('best')}
              disabled={downloading !== null}
              className="rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-1.5 text-sm font-semibold text-white hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {downloading ? 'Downloading…' : 'Best quality'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
