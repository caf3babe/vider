import { downloadUrl } from '../api'

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
  return (
    <div className="w-full rounded-2xl border border-white/10 bg-white/5 overflow-hidden">
      <div className="flex gap-4 p-4">
        {info.thumbnail && (
          <img
            src={info.thumbnail}
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
        <div className="flex flex-wrap gap-2">
          {info.formats.length > 0 ? (
            info.formats.map((fmt) => (
              <a
                key={fmt.format_id}
                href={downloadUrl(sourceUrl, fmt.format_id)}
                download
                className="flex items-center gap-1.5 rounded-lg bg-white/10 hover:bg-purple-600 px-3 py-1.5 text-sm font-medium text-white transition"
              >
                <span>{qualityLabel(fmt)}</span>
                {fmt.filesize && (
                  <span className="text-white/50 text-xs">· {formatSize(fmt.filesize)}</span>
                )}
              </a>
            ))
          ) : (
            <a
              href={downloadUrl(sourceUrl, 'best')}
              download
              className="rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-1.5 text-sm font-semibold text-white hover:opacity-90 transition"
            >
              Best quality
            </a>
          )}
        </div>
      </div>
    </div>
  )
}
