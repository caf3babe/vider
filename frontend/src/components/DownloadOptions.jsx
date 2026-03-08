import { useState } from 'react'
import { downloadZip } from '../api'

export default function DownloadOptions({ sourceUrls, infoResults }) {
  const [downloading, setDownloading] = useState(null)

  const successResults = infoResults.filter(r => r.success)

  if (successResults.length === 0) {
    return null
  }

  const handleDownload = async (format) => {
    if (sourceUrls.length === 0) return

    setDownloading(format)
    try {
      await downloadZip(sourceUrls, format)
    } catch (err) {
      alert(`Download failed: ${err.message}`)
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="w-full border-3 border-black bg-white px-6 py-6">
      <p className="text-sm font-black uppercase tracking-wide mb-4">Batch Download Options</p>

      <div className="flex flex-col gap-3">
        <button
          onClick={() => handleDownload('highest')}
          disabled={downloading !== null}
          className="border-3 border-black bg-black text-white px-4 py-3 text-sm font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition text-left"
        >
          {downloading === 'highest' ? 'Downloading...' : 'Download All (Highest Format + ZIP)'}
        </button>

        <button
          onClick={() => handleDownload('audio')}
          disabled={downloading !== null}
          className="border-3 border-black bg-black text-white px-4 py-3 text-sm font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition text-left"
        >
          {downloading === 'audio' ? 'Downloading...' : 'Download All as Audio (MP3 + ZIP)'}
        </button>

        <button
          onClick={() => handleDownload('video')}
          disabled={downloading !== null}
          className="border-3 border-black bg-black text-white px-4 py-3 text-sm font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition text-left"
        >
          {downloading === 'video' ? 'Downloading...' : 'Download All (Video + ZIP)'}
        </button>
      </div>

      <p className="text-xs text-black/40 mt-4">
        Downloads will be packaged in a ZIP file. Individual format downloads are available on each video card.
      </p>
    </div>
  )
}
