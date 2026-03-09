import { useState } from 'react'
import UrlForm from './components/UrlForm'
import VideoCard from './components/VideoCard'
import { fetchInfo } from './api'

export default function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [sourceUrl, setSourceUrl] = useState('')

  const handleSubmit = async (url) => {
    setLoading(true)
    setError(null)
    setInfo(null)
    try {
      const data = await fetchInfo(url)
      setInfo(data)
      setSourceUrl(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0e0e10] text-white flex flex-col items-center px-4 py-16">
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
          vider
        </h1>
        <p className="mt-2 text-white/40 text-sm">Download Instagram videos & YouTube audio</p>
      </div>

      <div className="w-full max-w-lg flex flex-col gap-4">
        <UrlForm
          onSubmit={handleSubmit}
          loading={loading}
          hasResult={!!info || !!error}
          onClear={() => { setInfo(null); setError(null) }}
        />

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex justify-center py-8">
            <div className="h-8 w-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
          </div>
        )}

        {info && <VideoCard info={info} sourceUrl={sourceUrl} />}
      </div>

      <p className="mt-auto pt-16 text-xs text-white/20">
        Supports Instagram posts, reels, IGTV · YouTube videos & shorts (MP3)
      </p>
    </div>
  )
}
