"""Run only with: python -m backend.agents.music.runtime (one worker)."""
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from .backends.home_assistant import HomeAssistantBackend
from .protocol import Frame, Settings
from .session import MusicSession
from .store import music_dir, socket_path


def create_app(session=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.music = session or MusicSession(HomeAssistantBackend())
        shutdown = threading.Event()
        def work():
            while not shutdown.wait(0.1):
                try:
                    app.state.music.tick()
                except Exception:
                    app.state.music.stop("worker_error")
        worker = threading.Thread(target=work, daemon=True, name="music-output")
        worker.start()
        yield
        app.state.music.stop("shutdown")
        shutdown.set()
        worker.join(timeout=10)
        # Any remainder stays in the durable journal for explicit recovery.
        if not worker.is_alive():
            app.state.music.tick()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/status")
    def status():
        return app.state.music.status()

    @app.post("/settings")
    def settings(payload: Settings):
        try:
            return app.state.music.configure(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/frame")
    def frame(payload: Frame):
        try:
            app.state.music.receive(payload)
            return {"ok": True}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/command/{action}")
    def command(action: str, payload: dict):
        music = app.state.music
        try:
            if action == "start":
                return music.start()
            if action == "stop":
                if payload.get("session") and payload["session"] != music.session:
                    return music.status()
                return music.stop(str(payload.get("reason", "manual")))
            if action == "release":
                return music.release(payload.get("entities", []))
            if action == "recover":
                return music.recover()
            raise ValueError("Unbekannte Aktion.")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return app


if __name__ == "__main__":
    import fcntl
    import uvicorn
    directory = music_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    os.umask(0o077)
    with (directory / "runtime.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uvicorn.run(create_app(), uds=socket_path(), workers=1, access_log=False)
