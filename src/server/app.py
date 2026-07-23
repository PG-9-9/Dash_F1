"""FastAPI application for the headless F1 dashboard."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect
import os
from pathlib import Path
import time
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.server.replay import HeadlessReplayController, ReplayDataset, load_fastf1_dataset
from src.server.sessions import SUPPORTED_SESSIONS, load_event_catalog


STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass(frozen=True)
class ServerConfig:
    year: int
    round_number: int
    session_type: str = "R"
    refresh: bool = False
    autoplay: bool = True


def create_app(
    controller: HeadlessReplayController | None = None,
    config: ServerConfig | None = None,
    dataset_loader: Callable[..., ReplayDataset] = load_fastf1_dataset,
    catalog_loader: Callable[[int], dict[str, Any]] = load_event_catalog,
) -> FastAPI:
    replay = controller or HeadlessReplayController()
    background_tasks: list[asyncio.Task] = []
    session_load_task: asyncio.Task | None = None

    async def load_session(year: int, round_number: int, session_type: str, refresh: bool, autoplay: bool) -> None:
        try:
            def progress_callback(progress: float, message: str) -> None:
                replay.set_loading_progress(progress, message)
            dataset = await asyncio.to_thread(
                _load_dataset_with_progress,
                dataset_loader,
                year,
                round_number,
                session_type,
                refresh,
                progress_callback,
            )
            replay.set_dataset(dataset, autoplay=autoplay)
        except Exception as exc:
            replay.set_error(str(exc))

    def schedule_session(
        year: int,
        round_number: int,
        session_type: str,
        refresh: bool = False,
        autoplay: bool = True,
    ) -> asyncio.Task:
        nonlocal session_load_task
        if session_load_task is not None and not session_load_task.done():
            raise RuntimeError("Another race session is already loading")
        replay.set_loading()
        session_load_task = asyncio.create_task(
            load_session(year, round_number, session_type, refresh, autoplay)
        )
        background_tasks.append(session_load_task)
        return session_load_task

    async def replay_clock() -> None:
        previous = time.monotonic()
        while True:
            await asyncio.sleep(0.04)
            now = time.monotonic()
            replay.advance(now - previous)
            previous = now

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        background_tasks.append(asyncio.create_task(replay_clock()))
        if config is not None and not replay.loaded:
            schedule_session(
                config.year,
                config.round_number,
                config.session_type,
                config.refresh,
                config.autoplay,
            )
        yield
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)

    app = FastAPI(
        title="F1 Race Replay Server",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.replay = replay
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health():
        state = replay.core_state()
        return {
            "status": "loading" if state.get("loading") else "ready" if state.get("ready") else "error",
            "ready": state.get("ready", False),
            "progress": state.get("loading_progress", 0.0),
            "message": state.get("loading_message", ""),
            "error": state.get("error"),
        }

    @app.get("/api/catalog")
    async def catalog(year: int = Query(ge=1950, le=2100)):
        try:
            return await asyncio.to_thread(catalog_loader, year)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Unable to load the {year} race calendar: {exc}") from exc

    @app.post("/api/session")
    async def change_session(request: dict[str, Any]):
        try:
            year = int(request.get("year", 0))
            round_number = int(request.get("round_number", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Year and round number must be integers") from exc
        session_type = str(request.get("session_type", "R")).upper()
        if not 1950 <= year <= 2100:
            raise HTTPException(status_code=400, detail="Year must be between 1950 and 2100")
        if not 1 <= round_number <= 40:
            raise HTTPException(status_code=400, detail="Round number must be between 1 and 40")
        if session_type not in SUPPORTED_SESSIONS:
            raise HTTPException(status_code=400, detail="Unsupported session type")
        try:
            schedule_session(
                year,
                round_number,
                session_type,
                bool(request.get("refresh", False)),
                bool(request.get("autoplay", True)),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "loading", "year": year, "round_number": round_number, "session_type": session_type}

    @app.get("/api/bootstrap")
    async def bootstrap():
        return replay.bootstrap()

    @app.get("/api/state")
    async def state():
        return replay.core_state()

    @app.get("/api/analyses")
    async def analyses(
        primary: str = Query(default="", max_length=10),
        comparison: str = Query(default="", max_length=10),
        risk: float = Query(default=0.5, ge=0.0, le=1.0),
    ):
        if not replay.loaded or replay.loading:
            raise HTTPException(status_code=503, detail="Replay session is still loading")
        return replay.analyses(primary, comparison, risk)

    @app.post("/api/control")
    async def control(command: dict[str, Any]):
        action = str(command.get("action", ""))
        try:
            return replay.control(action, command.get("value"))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket_stream(
        websocket: WebSocket,
        primary: str = "",
        comparison: str = "",
        risk: float = 0.5,
    ):
        await websocket.accept()
        counter = 0
        try:
            while True:
                state_payload = replay.core_state()
                message: dict[str, Any] = {"type": "state", "state": state_payload}
                if state_payload.get("ready") and not state_payload.get("loading") and counter % 4 == 0:
                    message["type"] = "dashboard"
                    message["analyses"] = replay.analyses(primary, comparison, max(0.0, min(1.0, risk)))
                await websocket.send_json(message)
                counter += 1
                await asyncio.sleep(0.25)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app


def _load_dataset_with_progress(
    dataset_loader: Callable[..., ReplayDataset],
    year: int,
    round_number: int,
    session_type: str,
    refresh: bool,
    progress_callback: Callable[[float, str], None],
) -> ReplayDataset:
    parameters = inspect.signature(dataset_loader).parameters
    accepts_progress = any(
        parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD) or name == "progress_callback"
        for name, parameter in parameters.items()
    )
    if accepts_progress:
        return dataset_loader(year, round_number, session_type, refresh, progress_callback)
    try:
        return dataset_loader(year, round_number, session_type, refresh, progress_callback)
    except TypeError as exc:
        if "positional" not in str(exc) and "keyword" not in str(exc):
            raise
        return dataset_loader(year, round_number, session_type, refresh)


def run_server(
    year: int,
    round_number: int,
    session_type: str = "R",
    host: str = "127.0.0.1",
    port: int = 8000,
    refresh: bool = False,
    autoplay: bool = True,
) -> None:
    import uvicorn

    config = ServerConfig(year, round_number, session_type, refresh, autoplay)
    uvicorn.run(create_app(config=config), host=host, port=port, log_level="info")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run F1 Race Replay as a headless web dashboard")
    parser.add_argument("--year", type=int, default=int(os.getenv("F1_YEAR", "2025")))
    parser.add_argument("--round", dest="round_number", type=int, default=int(os.getenv("F1_ROUND", "12")))
    parser.add_argument("--session", default=os.getenv("F1_SESSION", "R"))
    parser.add_argument("--host", default=os.getenv("F1_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("F1_PORT", "8000")))
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--paused", action="store_true", help="Load the replay without starting playback")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_server(
        year=args.year,
        round_number=args.round_number,
        session_type=args.session,
        host=args.host,
        port=args.port,
        refresh=args.refresh_data,
        autoplay=not args.paused,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
