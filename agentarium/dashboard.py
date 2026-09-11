"""Packaged local dashboard for Agentarium event files."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from .events import AgentEvent


_dashboard_lock = threading.Lock()
_dashboards: dict[str, tuple[uvicorn.Server, str]] = {}


def _asset_directory() -> Path:
    """Return the dashboard files bundled with the package."""

    required = (
        "index.html",
        "styles.css",
        "run_metrics.js",
        "run_story.js",
        "script.js",
    )
    directory = Path(__file__).resolve().parent / "static"
    if all((directory / name).is_file() for name in required):
        return directory
    raise RuntimeError("Agentarium dashboard assets are missing from this installation.")


def _event_file() -> Path:
    configured = os.environ.get("AGENTARIUM_EVENT_FILE")
    return Path(configured) if configured else Path.cwd() / ".agentarium" / "events.jsonl"


def create_app(event_path: Path | str | None = None) -> FastAPI:
    """Create a dashboard that follows one local Agentarium event file."""

    app = FastAPI()
    asset_directory = _asset_directory()
    event_file = Path(event_path) if event_path else _event_file()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(asset_directory / "index.html")

    @app.get("/styles.css")
    async def styles() -> FileResponse:
        return FileResponse(asset_directory / "styles.css")

    @app.get("/script.js")
    async def script() -> FileResponse:
        return FileResponse(asset_directory / "script.js")

    @app.get("/run_metrics.js")
    async def run_metrics() -> FileResponse:
        return FileResponse(asset_directory / "run_metrics.js")

    @app.get("/run_story.js")
    async def run_story() -> FileResponse:
        return FileResponse(asset_directory / "run_story.js")

    async def stream_live_events():
        sent: set[str] = set()
        while True:
            if event_file.exists():
                try:
                    lines = event_file.read_text(encoding="utf-8").splitlines()
                except OSError:
                    lines = []
                for line in lines:
                    try:
                        event = AgentEvent.from_json(line)
                    except (ValueError, json.JSONDecodeError):
                        continue
                    if event.event_id in sent:
                        continue
                    sent.add(event.event_id)
                    yield (
                        f"id: {event.event_id}\n"
                        f"event: {event.type.value}\n"
                        f"data: {event.to_json()}\n\n"
                    )
            await asyncio.sleep(0.2)

    @app.get("/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(
            stream_live_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


def _available_port(preferred_port: int = 8765) -> int:
    for port in range(preferred_port, preferred_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Agentarium could not find a free local dashboard port.")


def start_dashboard(
    event_path: Path | str,
    *,
    port: int | None = None,
    open_browser: bool = True,
) -> str:
    """Start one local dashboard and optionally open it in the default browser."""

    resolved_event_path = str(Path(event_path).resolve())
    with _dashboard_lock:
        existing = _dashboards.get(resolved_event_path)
        if existing and existing[0].started:
            url = existing[1]
        else:
            selected_port = port or _available_port()
            url = f"http://127.0.0.1:{selected_port}/"
            server = uvicorn.Server(
                uvicorn.Config(
                    create_app(resolved_event_path),
                    host="127.0.0.1",
                    port=selected_port,
                    log_level="warning",
                )
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            if not server.started:
                raise RuntimeError("Agentarium dashboard did not start.")
            _dashboards[resolved_event_path] = (server, url)

    if open_browser:
        webbrowser.open(url, new=2)
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the local Agentarium dashboard.")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000).")
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
