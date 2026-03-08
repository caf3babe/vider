import { useState } from 'react'

export default function UrlForm({ onSubmit, loading }) {
  const [text, setText] = useState('')

  const parseUrls = (text) => {
    return text
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const urls = parseUrls(text)
    if (urls.length > 0) onSubmit(urls)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full">
      <label className="text-xs font-black uppercase tracking-wide">URLs (one per line)</label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="https://www.instagram.com/reel/...&#10;https://youtu.be/...&#10;https://youtube.com/watch?v=..."
        rows={4}
        className="w-full border-3 border-black bg-white px-4 py-3 text-sm text-black placeholder-black/40 outline-none focus:border-5 transition font-mono"
      />
      <button
        type="submit"
        disabled={loading || !text.trim()}
        className="border-3 border-black bg-black text-white px-6 py-3 text-sm font-black uppercase tracking-wide hover:bg-white hover:text-black disabled:opacity-50 transition cursor-pointer"
      >
        {loading ? 'Fetching…' : 'Fetch All'}
      </button>
    </form>
  )
}
