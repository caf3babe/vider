import VideoCard from './VideoCard'

export default function VideoGrid({ results }) {
  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {results.map((result, idx) => {
        if (!result.success) {
          return (
            <div key={idx} className="border-3 border-red-600 bg-white px-6 py-6 text-center">
              <p className="text-red-600 text-sm font-black uppercase">{result.error || 'Failed to load'}</p>
            </div>
          )
        }
        return (
          <div key={idx}>
            <VideoCard info={result} />
          </div>
        )
      })}
    </div>
  )
}
