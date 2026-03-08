"""Vider backend — Instagram video info & download proxy."""

import re
import tempfile
import urllib.parse
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Vider API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

INSTAGRAM_RE = re.compile(
    r"https?://(www\.)?instagram\.com/(p|reel|tv)/[\w-]+"
)


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str | None
    duration: float | None
    uploader: str | None
    formats: list[dict]


def _validate_instagram_url(url: str) -> str:
    url = url.strip()
    if not INSTAGRAM_RE.match(url):
        raise HTTPException(status_code=400, detail="Not a valid Instagram URL")
    return url


@app.get("/api/info", response_model=VideoInfo)
def get_info(url: str = Query(..., description="Instagram post/reel URL")):
    url = _validate_instagram_url(url)

    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    formats = [
        {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "height": f.get("height"),
            "width": f.get("width"),
            "filesize": f.get("filesize"),
            "url": f.get("url"),
        }
        for f in (info.get("formats") or [])
        if f.get("url") and f.get("vcodec") not in (None, "none")
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


@app.get("/api/download")
def download(
    url: str = Query(...),
    format_id: str = Query("best"),
):
    url = _validate_instagram_url(url)

    tmp_dir = tempfile.mkdtemp()
    out_path: list[Path] = []

    def hook(d: dict) -> None:
        if d["status"] == "finished":
            out_path.append(Path(d["filename"]))

    fmt = (
        f"{format_id}+bestaudio/best"
        if format_id != "best"
        else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    )

    ydl_opts = {
        "outtmpl": str(Path(tmp_dir) / "%(uploader)s_%(id)s.%(ext)s"),
        "format": fmt,
        "progress_hooks": [hook],
        "quiet": True,
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not out_path:
        raise HTTPException(status_code=500, detail="Download produced no file")

    file = out_path[0]
    return FileResponse(
        path=file,
        media_type="video/mp4",
        filename=file.name,
        headers={"Content-Disposition": f'attachment; filename="{file.name}"'},
    )
