"""Lightweight FastAPI server to browse replayed frames in a browser."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG = BASE_DIR / "runs" / "video_replay" / "chessgame_log.jsonl"
DEFAULT_FRAMES = BASE_DIR / "runs" / "video_replay" / "report_frames"


@dataclass
class ReplaySettings:
    log_path: Path
    frames_dir: Path
    title: str


settings = ReplaySettings(
    log_path=Path(os.getenv("REPLAY_LOG_PATH", DEFAULT_LOG)).resolve(),
    frames_dir=Path(os.getenv("REPLAY_FRAMES_DIR", DEFAULT_FRAMES)).resolve(),
    title=os.getenv("REPLAY_TITLE", "Video Replay Viewer"),
)

app = FastAPI(title="Replay Viewer")


def resolve_relative(path: Path) -> Path:
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def read_log_entries() -> list[dict[str, Any]]:
    if not settings.log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with settings.log_path.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>__TITLE__</title>
    <style>
        :root {
            color-scheme: light dark;
            font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        }
        body { margin: 0; background: #0d1b3a; color: #f1f5f9; }
        header { padding: 1.5rem 2rem; background: #122752; color: #f8fafc; }
        header h1 { margin: 0 0 0.25rem; font-size: 1.75rem; }
        header p { margin: 0; opacity: 0.8; }
        main { padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
        .toolbar { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }
        button { background: #38bdf8; color: #0b1224; border: none; border-radius: 6px; padding: 0.5rem 1rem; cursor: pointer; font-weight: 600; }
        button:hover { background: #0ea5e9; color: #0b1224; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
        article { background: #122752; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.25); overflow: hidden; display: flex; flex-direction: column; border: 1px solid #1e3a8a; }
        article img { width: 100%; display: block; object-fit: cover; }
        article .content { padding: 1rem; display: flex; flex-direction: column; gap: 0.35rem; color: #e2e8f0; }
        .status-success { color: #22c55e; font-weight: 700; }
        .status-error { color: #f87171; font-weight: 700; }
        code { font-family: 'SFMono-Regular', Consolas, monospace; background: #0b1224; color: #e2e8f0; padding: 0.1rem 0.25rem; border-radius: 4px; display: inline-block; word-break: break-all; border: 1px solid #1e3a8a; }
        footer { text-align: center; padding: 1rem; color: #cbd5f5; }
    </style>
</head>
<body>
    <header>
        <h1>__TITLE__</h1>
        <p>Viewing images from <span id=\"log-path\"></span></p>
    </header>
    <main>
        <div class=\"toolbar\">
            <button id=\"refresh-btn\">Refresh</button>
            <span id=\"frame-count\"></span>
        </div>
        <div class=\"grid\" id=\"frames-grid\"></div>
    </main>
    <footer>ScanMate replay viewer</footer>
    <script>
        async function loadFrames() {
            const res = await fetch('/api/frames');
            const data = await res.json();
            document.getElementById('log-path').textContent = data.log_path;
            document.getElementById('frame-count').textContent = `${data.frames.length} frames`;
            const grid = document.getElementById('frames-grid');
            grid.innerHTML = '';
            data.frames.forEach(frame => {
                const article = document.createElement('article');
                if (frame.image_url) {
                    const img = document.createElement('img');
                    img.src = frame.image_url;
                    img.alt = `Frame ${frame.frame_index}`;
                    article.appendChild(img);
                }
                if (frame.debug_url) {
                    const debugImg = document.createElement('img');
                    debugImg.src = frame.debug_url;
                    debugImg.alt = `Debug visualization for frame ${frame.frame_index}`;
                    article.appendChild(debugImg);
                }
                const content = document.createElement('div');
                content.className = 'content';
                const title = document.createElement('h3');
                title.textContent = `Frame ${frame.frame_index}`;
                const status = document.createElement('p');
                status.className = frame.status === 'success' ? 'status-success' : 'status-error';
                status.textContent = `Status: ${frame.status}`;
                const move = document.createElement('p');
                const moveSan = frame.move_san || frame.move || '—';
                move.innerHTML = `<strong>Move (SAN/desc):</strong> ${moveSan}`;

                const moveUci = document.createElement('p');
                const uciLabel = frame.move_uci || '—';
                moveUci.innerHTML = `<strong>Move (UCI):</strong> ${uciLabel}`;
                const mode = document.createElement('p');
                mode.innerHTML = `<strong>Mode:</strong> ${frame.detection_mode || 'unknown'}`;
                const diff = document.createElement('p');
                if (frame.diff_ready === undefined || frame.diff_ready === null) {
                    diff.innerHTML = '<strong>Diff:</strong> n/a';
                } else {
                    const ready = frame.diff_ready ? '✓ ready' : '⏳ warming';
                    const threshold = frame.diff_threshold !== undefined && frame.diff_threshold !== null
                        ? frame.diff_threshold.toFixed(2)
                        : 'n/a';
                    const maxZ = frame.diff_max_z !== undefined && frame.diff_max_z !== null
                        ? frame.diff_max_z.toFixed(2)
                        : 'n/a';
                    diff.innerHTML = `<strong>Diff:</strong> ${ready} · thresh=${threshold} · trig=${frame.diff_triggered ?? 0} · maxZ=${maxZ}`;
                }
                const timestamp = document.createElement('p');
                const ts = frame.timestamp_seconds ?? 'n/a';
                const pieces = frame.piece_count ?? 0;
                const proc = frame.processing_ms ?? 0;
                timestamp.textContent = `Timestamp: ${ts}s · Pieces: ${pieces} · Processing: ${proc} ms`;
                const fen = document.createElement('p');
                const fenCode = document.createElement('code');
                fenCode.textContent = frame.fen || '—';
                fen.append('FEN: ', fenCode);
                const error = document.createElement('p');
                error.textContent = `Error: ${frame.error || '—'}`;
                content.append(title, status, move, moveUci, mode, diff, timestamp, fen, error);
                article.appendChild(content);
                grid.appendChild(article);
            });
        }
        document.getElementById('refresh-btn').addEventListener('click', loadFrames);
        loadFrames();
        setInterval(loadFrames, 10000);
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(HTML_TEMPLATE.replace("__TITLE__", settings.title))


@app.get("/api/frames")
def list_frames() -> JSONResponse:
    entries = read_log_entries()
    frames: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("status") != "success":
            continue
        frame_index = entry.get("frame_index")
        filename = f"frame_{frame_index:06d}.jpg" if frame_index is not None else None
        image_url: Optional[str] = None
        if filename:
            file_path = settings.frames_dir / filename
            if file_path.exists():
                image_url = f"/frames/{filename}"
        # Check for debug visualization
        debug_url: Optional[str] = None
        if filename:
            debug_filename = f"frame_{frame_index:06d}_debug.jpg"
            debug_path = settings.frames_dir / "debug" / debug_filename
            if debug_path.exists():
                debug_url = f"/frames/debug/{debug_filename}"
        
        frames.append({
            "frame_index": frame_index,
            "timestamp_seconds": entry.get("timestamp_seconds"),
            "processing_ms": entry.get("processing_ms"),
            "status": entry.get("status"),
            "fen": entry.get("fen"),
            "error": entry.get("error"),
            "piece_count": entry.get("piece_count"),
            "move": entry.get("move"),
            "move_uci": entry.get("move_uci"),
            "move_san": entry.get("move_san"),
            "candidate_fen": entry.get("candidate_fen"),
            "detection_mode": entry.get("detection_mode"),
            "diff_ready": entry.get("diff_ready"),
            "diff_threshold": entry.get("diff_threshold"),
            "diff_triggered": entry.get("diff_triggered"),
            "diff_max_z": entry.get("diff_max_z"),
            "image_url": image_url,
            "debug_url": debug_url,
        })
    return JSONResponse(
        {
            "title": settings.title,
            "log_path": str(settings.log_path),
            "frames_dir": str(settings.frames_dir),
            "frames": frames,
        }
    )


@app.get("/frames/{filename}")
def get_frame(filename: str) -> FileResponse:
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = (settings.frames_dir / filename).resolve()
    try:
        target.relative_to(settings.frames_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="File outside frames directory")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(target)


@app.get("/frames/debug/{filename}")
def get_debug_frame(filename: str) -> FileResponse:
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = (settings.frames_dir / "debug" / filename).resolve()
    try:
        target.relative_to(settings.frames_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="File outside frames directory")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Debug frame not found")
    return FileResponse(target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve replay frames via FastAPI")
    parser.add_argument("--log", type=Path, default=None, help="Path to the JSONL log produced by video_replay.py")
    parser.add_argument("--frames", type=Path, default=None, help="Directory containing extracted frame JPEGs")
    parser.add_argument("--title", type=str, default=None, help="Browser page title")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8050, help="Server port")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.log:
        settings.log_path = resolve_relative(args.log)
    if args.frames:
        settings.frames_dir = resolve_relative(args.frames)
    if args.title:
        settings.title = args.title
    uvicorn.run(app, host=args.host, port=args.port)
