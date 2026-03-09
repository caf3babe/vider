import { useState } from 'react'

export default function UrlForm({ onSubmit, loading }) {
  const [url, setUrl] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (url.trim()) onSubmit(url.trim())
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 w-full">
      <input
        type="text"
        inputMode="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://www.instagram.com/reel/..."
        required
        className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-base text-white placeholder-white/30 outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 transition"
      />
      <button
        type="submit"
        disabled={loading}
        className="rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition cursor-pointer"
      >
        {loading ? 'Fetching…' : 'Fetch'}
      </button>
    </form>
  )
}
