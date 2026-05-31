"""Vider backend — video info & download proxy."""

import asyncio
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("vider")

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

URL_RE = re.compile(
    r"https?://(www\.)?instagram\.com/(p|reel|tv)/[\w-]+"
    r"|"
    r"https?://(www\.)?(youtube\.com/(watch\?[^#]*v=[\w-]+|shorts/[\w-]+)|youtu\.be/[\w-]+)"
)


def _extract_time_param(url: str) -> int | None:
    match = re.search(r'[?&]t=(\d+)', url)
    return int(match.group(1)) if match else None


def _content_disposition(filename: str) -> str:
    ascii_fallback = re.sub(r"[^\x20-\x7e]", "_", filename).replace(" ", "_").replace('"', "_")
    encoded = quote(filename, safe=".-_~")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _validate_url(url: str) -> tuple[str, str]:
    url = url.strip()
    if not URL_RE.search(url):
        raise HTTPException(status_code=400, detail="Not a valid Instagram or YouTube URL")
    if "instagram.com" in url:
        return url, "instagram"
    return url, "youtube"


def _run_ffmpeg_audio(input_path: Path, tmp_dir: str, time_offset: int | None = None) -> Path:
    """Extract audio to MP3 via ffmpeg, returning the output path."""
    mp3_path = input_path.with_suffix(".mp3")
    base = ["ffmpeg", "-nostdin", "-loglevel", "error", "-fflags", "+genpts"]
    audio_filter = "-af", "aresample=async=1:min_comp=0.001"
    if time_offset is not None:
        cmd = [*base, "-ss", str(time_offset), "-i", str(input_path),
               "-vn", *audio_filter, "-acodec", "libmp3lame", "-ab", "192k"]
    else:
        cmd = [*base, "-i", str(input_path), "-vn", *audio_filter,
               "-acodec", "libmp3lame", "-ab", "192k"]
    cmd.extend(["-y", str(mp3_path)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise Exception("Audio conversion timed out after 300s")
    if result.returncode != 0:
        stderr = result.stderr
        logger.error("ffmpeg failed (exit code %d)", result.returncode)
        logger.error("ffmpeg stderr:\n%s", stderr)
        raise Exception(f"Audio conversion failed:\n{stderr[:2000]}")
    if not mp3_path.exists():
        raise Exception("ffmpeg did not produce output file")
    return mp3_path


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str | None
    duration: float | None
    uploader: str | None
    formats: list[dict]


class BatchInfoRequest(BaseModel):
    urls: list[str]


class BatchInfoResponse(BaseModel):
    results: list[dict]


class DownloadZipRequest(BaseModel):
    urls: list[str]
    format: str = "video"
    format_id: str | None = None


@app.get("/api/info", response_model=VideoInfo)
def get_info(url: str = Query(..., description="Instagram or YouTube URL")):
    url, _ = _validate_url(url)

    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _IOS_VCODECS = ("avc1", "hvc1", "hev1", "av01", "mp4v")

    def _is_video(f: dict) -> bool:
        return (
            bool(f.get("url"))
            and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        )

    def _is_ios_compat(f: dict) -> bool:
        return any(f.get("vcodec", "").startswith(c) for c in _IOS_VCODECS)

    raw = [f for f in (info.get("formats") or []) if _is_video(f)]
    ios_formats = [f for f in raw if _is_ios_compat(f)]
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

    seen: dict[int | None, dict] = {}
    for fmt in formats:
        h = fmt["height"]
        if h not in seen or (fmt.get("filesize") or 0) > (seen[h].get("filesize") or 0):
            seen[h] = fmt
    formats = sorted(seen.values(), key=lambda f: f["height"] or 0, reverse=True)

    return VideoInfo(
        id=info.get("id", ""),
        title=info.get("title") or info.get("description") or "Video",
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
        "format": "best[ext=mp4]/bestvideo+bestaudio/best",
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = Path(ydl.prepare_filename(info))
        if not video_path.exists():
            files = list(Path(tmp_dir).glob("*"))
            if not files:
                raise Exception("No file found after download")
            video_path = files[0]
        mp3_path = _run_ffmpeg_audio(video_path, tmp_dir)
    except yt_dlp.utils.DownloadError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def iterfile():
        try:
            with open(mp3_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        iterfile(),
        media_type="audio/mpeg",
        headers={"Content-Disposition": _content_disposition(mp3_path.name)},
    )


@app.get("/api/download")
def download(
    url: str = Query(...),
    format_id: str = Query("best"),
    format_type: str = Query("video"),
):
    url, _ = _validate_url(url)

    tmp_dir = tempfile.mkdtemp()
    time_offset = _extract_time_param(url)

    ydl_opts: dict = {
        "outtmpl": str(Path(tmp_dir) / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    if format_type == "audio":
        ydl_opts["format"] = "best[ext=mp4]/bestvideo+bestaudio/best"
        media_type = "audio/mpeg"
    elif format_id != "best":
        ydl_opts["format"] = f"{format_id}+bestaudio/best"
        output_ext = "mp4"
        ydl_opts["merge_output_format"] = "mp4"
        postprocessor_args = ["-c", "copy"]
        if time_offset is not None:
            postprocessor_args = ["-ss", str(time_offset)] + postprocessor_args
        ydl_opts["postprocessor_args"] = postprocessor_args
        media_type = "video/mp4"
    else:
        ydl_opts["format"] = (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec=aac][ext=m4a]/"
            "bestvideo[vcodec^=avc1]+bestaudio[acodec=aac]/"
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "best[vcodec^=avc1][ext=mp4]/"
            "best[vcodec^=avc1]/"
            "best[ext=mp4]/"
            "bestvideo+bestaudio/"
            "best"
        )
        output_ext = "mp4"
        ydl_opts["merge_output_format"] = "mp4"
        postprocessor_args = ["-c", "copy"]
        if time_offset is not None:
            postprocessor_args = ["-ss", str(time_offset)] + postprocessor_args
        ydl_opts["postprocessor_args"] = postprocessor_args
        media_type = "video/mp4"

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

    if format_type == "audio":
        try:
            file_path = _run_ffmpeg_audio(file_path, tmp_dir, time_offset)
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        if not file_path.exists():
            file_path = file_path.with_suffix(f".{output_ext}")

        if not file_path.exists():
            files_in_dir = list(Path(tmp_dir).glob("*"))
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail=f"Downloaded file not found: {file_path.name} (found: {[f.name for f in files_in_dir]})"
            )

    def iterfile():
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(file_path.name)},
    )


async def _process_single_url(url: str) -> dict:
    async with _BATCH_SEMAPHORE:
        try:
            url, _ = _validate_url(url)
            ydl_opts = {"quiet": True, "skip_download": True, "socket_timeout": 30}

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _extract)

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

            seen: dict[int | None, dict] = {}
            for fmt in formats:
                h = fmt["height"]
                if h not in seen or (fmt.get("filesize") or 0) > (seen[h].get("filesize") or 0):
                    seen[h] = fmt
            formats = sorted(seen.values(), key=lambda f: f["height"] or 0, reverse=True)

            return {
                "success": True,
                "id": info.get("id", ""),
                "title": info.get("title") or info.get("description") or "Video",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader") or info.get("channel"),
                "formats": formats,
            }
        except HTTPException as exc:
            return {"success": False, "error": exc.detail, "status_code": exc.status_code}
        except yt_dlp.utils.DownloadError as exc:
            return {"success": False, "error": str(exc), "status_code": 422}
        except Exception as exc:
            return {"success": False, "error": str(exc), "status_code": 500}


_BATCH_SEMAPHORE = asyncio.Semaphore(3)


@app.post("/api/batch-info")
async def batch_info(request: BatchInfoRequest):
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    tasks = [_process_single_url(url) for url in request.urls]
    results = await asyncio.gather(*tasks)

    return BatchInfoResponse(results=results)


def _download_file(url: str, format_type: str, format_id: str | None, time_offset: int | None) -> tuple[bytes, str]:
    url, _ = _validate_url(url)
    tmp_dir = tempfile.mkdtemp()

    if format_type == "audio":
        fmt = "best[ext=mp4]/bestvideo+bestaudio/best"
    elif format_type == "highest":
        fmt = "best[ext=mp4]/bestvideo+bestaudio/best"
    elif format_id:
        fmt = f"{format_id}+bestaudio/best"
    else:
        fmt = (
            "bestvideo[vcodec^=avc1][ext=mp4]+"
            "bestaudio[acodec=aac][ext=m4a]/"
            "bestvideo[vcodec^=avc1]+"
            "bestaudio[acodec=aac]/"
            "bestvideo[ext=mp4]+"
            "bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best"
        )

    ydl_opts: dict = {
        "outtmpl": str(Path(tmp_dir) / "%(title)s.%(ext)s"),
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }

    if format_type == "audio":
        pass
    else:
        ydl_opts["merge_output_format"] = "mp4"
        postprocessor_args = [
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-q:a", "5",
        ]
        if time_offset is not None:
            postprocessor_args = ["-ss", str(time_offset)] + postprocessor_args
        ydl_opts["postprocessor_args"] = postprocessor_args

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = Path(ydl.prepare_filename(info))

        if not file_path.exists():
            files = list(Path(tmp_dir).glob("*"))
            if not files:
                raise Exception("No output file found")
            file_path = files[0]

        if format_type == "audio":
            file_path = _run_ffmpeg_audio(file_path, tmp_dir, time_offset)

        with open(file_path, "rb") as f:
            content = f.read()

        return content, file_path.name
    except Exception:
        logger.exception("Download failed")
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/api/download-zip")
async def download_zip(request: DownloadZipRequest):
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    tmp_dir = tempfile.mkdtemp()
    zip_path = Path(tmp_dir) / "vider_downloads.zip"

    try:
        loop = asyncio.get_event_loop()
        name_counts: dict[str, int] = {}

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, url in enumerate(request.urls, 1):
                try:
                    time_offset = _extract_time_param(url)

                    content, filename = await loop.run_in_executor(
                        None,
                        _download_file,
                        url,
                        request.format,
                        request.format_id,
                        time_offset,
                    )

                    base = filename
                    count = name_counts.get(filename, 0)
                    if count:
                        stem, ext = Path(filename).stem, Path(filename).suffix
                        filename = f"{stem} ({count}){ext}"
                    name_counts[base] = count + 1

                    zf.writestr(filename, content)
                except Exception as exc:
                    error_name = f"error_{idx}.txt"
                    zf.writestr(error_name, f"Failed to download: {str(exc)}")

        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad:
                raise Exception(f"Corrupted entry in ZIP: {bad}")

        zip_size = zip_path.stat().st_size

        def iterfile():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="vider_downloads.zip"',
                "Content-Length": str(zip_size),
            },
        )
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"ZIP creation failed: {str(exc)}") from exc


# SPA fallback — must be last
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    index = _STATIC / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse("<h1>Vider API</h1><p>Run the frontend separately in dev mode.</p>")
