# vider

Download Instagram videos and reels from your browser. Paste a URL, pick a quality, done.

![CI / Release](https://github.com/caf3babe/vider/actions/workflows/release.yml/badge.svg)

## Features

- Supports Instagram posts, reels, and IGTV
- Shows all available resolutions — download the one you want
- Displays title, uploader, thumbnail, and duration before downloading
- Single self-contained Docker image (frontend served by the backend)

## Stack

| Layer | Tech |
|---|---|
| Frontend | React + Vite + Tailwind CSS v4 |
| Backend | FastAPI + yt-dlp |
| Container | Docker (multi-stage, `linux/amd64` + `linux/arm64`) |

## Running with Docker

```bash
docker run -p 8000:8000 ghcr.io/caf3babe/vider:latest
```

Open [http://localhost:8000](http://localhost:8000).

## Running locally (development)

**Prerequisites:** Python 3.12+, Node 18+, ffmpeg, [uv](https://docs.astral.sh/uv/)

```bash
# Backend
cd backend
uv sync
uv run uvicorn main:app --reload
# → http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173  (proxied to backend)
```

## Building the Docker image

```bash
podman build -t vider .
podman run -p 8000:8000 vider
```

## Releasing

Releases are driven by git tags. The [CI / Release](.github/workflows/release.yml) workflow triggers automatically.

```bash
git tag v1.0.0
git push origin v1.0.0
```

This builds multi-arch images, pushes them to GitHub Container Registry, and creates a GitHub Release with auto-generated notes.

### Semver tags published

| Tag | Example |
|---|---|
| Exact version | `ghcr.io/caf3babe/vider:1.0.0` |
| Minor | `ghcr.io/caf3babe/vider:1.0` |
| Major | `ghcr.io/caf3babe/vider:1` |
| Latest (stable only) | `ghcr.io/caf3babe/vider:latest` |

Pre-release tags (`v1.0.0-rc.1`) are published but marked as pre-releases on GitHub — `latest` is never overwritten by them.

## CI

The workflow runs on every push to `main` and on pull requests targeting `main`, **only when files under `backend/`, `frontend/`, `Dockerfile`, or `.dockerignore` change**. It builds the image and runs a smoke test against the running container. No image is pushed outside of tag releases.
