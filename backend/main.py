"""Vider backend — Instagram video info & download proxy."""

import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

import httpx
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Vider API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Serve compiled frontend when present (production / Docker)
_STATIC = Path(__file__).parent / "static"
if _STATIC.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

INSTAGRAM_RE = re.compile(
    r"https?://(www\.)?instagram\.com/(p|reel|tv)/[\w-]+"
)
YOUTUBE_RE = re.compile(
    r"https?://(www\.)?(youtube\.com/(watch\?[^#]*v=[\w-]+|shorts/[\w-]+)|youtu\.be/[\w-]+)"
)


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str | None
    duration: float | None
    uploader: str | None
    formats: list[dict]


def _content_disposition(filename: str) -> str:
    """Return a Content-Disposition value that works on iOS Safari / Brave.

    Provides an ASCII fallback (spaces → underscores) plus an RFC 5987
    ``filename*`` parameter so browsers that support it get the real name.
    """
    ascii_fallback = re.sub(r"[^\x20-\x7e]", "_", filename).replace(" ", "_").replace('"', "_")
    encoded = quote(filename, safe=".-_~")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _validate_url(url: str) -> tuple[str, str]:
    url = url.strip()
    if INSTAGRAM_RE.match(url):
        return url, "instagram"
    if YOUTUBE_RE.match(url):
        return url, "youtube"
    raise HTTPException(status_code=400, detail="Not a valid Instagram or YouTube URL")


@app.get("/api/info", response_model=VideoInfo)
def get_info(url: str = Query(..., description="Instagram or YouTube URL")):
    url, _ = _validate_url(url)

    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # iOS supports H.264 (avc1), HEVC (hvc1/hev1), and AV1 (av01).
    # VP8/VP9 are not supported and will appear as audio-only on iOS.
    _IOS_VCODECS = ("avc1", "hvc1", "hev1", "av01", "mp4v")

    def _is_video(f: dict) -> bool:
        # Only combined formats (video+audio in one stream) — excludes DASH video-only tracks.
        return (
            bool(f.get("url"))
            and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        )

    def _is_ios_compat(f: dict) -> bool:
        return any(f.get("vcodec", "").startswith(c) for c in _IOS_VCODECS)

    raw = [f for f in (info.get("formats") or []) if _is_video(f)]
    ios_formats = [f for f in raw if _is_ios_compat(f)]
    # Prefer iOS-compatible codecs; fall back to all video formats if none found.
    source_formats = ios_formats or raw

    formats = [
        {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "height": f.get("height"),
            "width": f.get("width"),
            "filesize": f.get("filesize"),
            "url": f.get("url"),
        }
        for f in source_formats
    ]

    # Deduplicate by height, keep best bitrate per resolution
    seen: dict[int | None, dict] = {}
    for fmt in formats:
        h = fmt["height"]
        if h not in seen or (fmt.get("filesize") or 0) > (seen[h].get("filesize") or 0):
            seen[h] = fmt
    formats = sorted(seen.values(), key=lambda f: f["height"] or 0, reverse=True)

    return VideoInfo(
        id=info.get("id", ""),
        title=info.get("title") or info.get("description") or "Instagram Video",
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        formats=formats,
    )


@app.get("/api/thumbnail")
async def thumbnail_proxy(url: str = Query(...)):
    """Proxy thumbnail to avoid CORS issues."""
    url, _ = _validate_url(url)

    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    thumbnail_url = info.get("thumbnail")
    if not thumbnail_url:
        raise HTTPException(status_code=404, detail="No thumbnail available")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(thumbnail_url, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            return StreamingResponse(
                iter([response.content]),
                media_type=response.headers.get("content-type", "image/jpeg"),
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch thumbnail: {exc}") from exc


@app.get("/api/audio")
def download_audio(url: str = Query(...)):
    url, source = _validate_url(url)
    if source != "youtube":
        raise HTTPException(status_code=400, detail="Audio download is only supported for YouTube URLs")

    tmp_dir = tempfile.mkdtemp()
    ydl_opts = {
        "outtmpl": str(Path(tmp_dir) / "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base_path = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
    except yt_dlp.utils.DownloadError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not base_path.exists():
        files = list(Path(tmp_dir).glob("*.mp3"))
        if not files:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Audio file not found after download")
        base_path = files[0]

    def iterfile():
        try:
            with open(base_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        iterfile(),
        media_type="audio/mpeg",
        headers={"Content-Disposition": _content_disposition(base_path.name)},
    )


@app.get("/api/download")
def download(
    url: str = Query(...),
    format_id: str = Query("best"),
):
    url, _ = _validate_url(url)

    tmp_dir = tempfile.mkdtemp()
    
    # Format selection: prioritize H.264 + AAC for macOS QuickTime compatibility
    if format_id != "best":
        # Instagram formats are combined (video+audio in one stream).
        # Just download the selected format directly — no merge needed.
        fmt = format_id
    else:
        # Prefer H.264 + AAC for widest device compatibility (QuickTime, iOS).
        # For YouTube DASH the bestvideo+bestaudio combos apply.
        # For Instagram combined streams, best[vcodec^=avc1] matches directly.
        fmt = (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec=aac][ext=m4a]/"
            "bestvideo[vcodec^=avc1]+bestaudio[acodec=aac]/"
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "best[vcodec^=avc1][ext=mp4]/"
            "best[vcodec^=avc1]/"
            "best[ext=mp4]/"
            "best"
        )

    ydl_opts = {
        "outtmpl": str(Path(tmp_dir) / "%(title)s.%(ext)s"),
        "format": fmt,
        "quiet": False,
        "no_warnings": False,
        "merge_output_format": "mp4",
        # Stream-copy: already selecting H.264+AAC so no re-encoding needed.
        # This is dramatically faster than transcoding.
        "postprocessor_args": ["-c", "copy"],
        "prefer_ffmpeg": True,
        "ffmpeg_location": None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            file_path = Path(filename)
    except yt_dlp.utils.DownloadError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Download error: {str(exc)}") from exc

    if not file_path.exists():
        # List what files are in the directory for debugging
        files_in_dir = list(Path(tmp_dir).glob("*"))
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Downloaded file not found: {file_path.name} (found: {[f.name for f in files_in_dir]})"
        )

    def iterfile():
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 1024):  # 1MB chunks
                    yield chunk
        finally:
            # Cleanup after serving
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        iterfile(),
        media_type="video/mp4",
        headers={"Content-Disposition": _content_disposition(file_path.name)},
    )


# SPA fallback — must be last
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    index = _STATIC / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse("<h1>Vider API</h1><p>Run the frontend separately in dev mode.</p>")
