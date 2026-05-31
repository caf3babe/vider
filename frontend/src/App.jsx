import { useState } from 'react'
import UrlForm from './components/UrlForm'
import VideoGrid from './components/VideoGrid'
import DownloadOptions from './components/DownloadOptions'
import { fetchBatchInfo, fetchInfo } from './api'

export default function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [infoResults, setInfoResults] = useState([])
  const [sourceUrls, setSourceUrls] = useState([])

  const handleSubmitBatch = async (urls) => {
    setLoading(true)
    setError(null)
    setInfoResults([])

    try {
      if (urls.length === 1) {
        const data = await fetchInfo(urls[0])
        setInfoResults([{ success: true, url: urls[0], ...data }])
      } else {
        const response = await fetchBatchInfo(urls)
        const resultsWithUrls = response.results.map((result, idx) => ({
          ...result,
          url: urls[idx]
        }))
        setInfoResults(resultsWithUrls)
      }
      setSourceUrls(urls)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-white text-black flex flex-col items-center px-4 py-16">
      <div className="mb-10 text-center">
        <h1 className="text-5xl font-black tracking-tight">vider</h1>
        <p className="mt-2 text-black/60 text-sm">Download Instagram videos & YouTube audio</p>
      </div>

      <div className="w-full max-w-2xl flex flex-col gap-6">
        <UrlForm onSubmit={handleSubmitBatch} loading={loading} />

        {error && (
          <div className="border-3 border-red-600 bg-white px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex justify-center py-8">
            <div className="h-8 w-8 border-3 border-black border-t-transparent animate-spin" />
          </div>
        )}

        {infoResults.length > 0 && (
          <>
            <VideoGrid results={infoResults} />
            <DownloadOptions sourceUrls={sourceUrls} infoResults={infoResults} />
          </>
        )}
      </div>

      <p className="mt-auto pt-16 text-xs text-black/40">
        Supports Instagram posts, reels, IGTV · YouTube videos & shorts (MP3)
      </p>
    </div>
  )
}
