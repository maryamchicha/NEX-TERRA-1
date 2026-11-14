"""NEX TERRA FastAPI application."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import config, models
from . import routes as api
from .simulator import simulator as sim

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

log = logging.getLogger("nex-terra")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NEX TERRA — Rotation Resilience Engine",
        description=(
            "Agricultural decision-support for Moroccan farmers. "
            "Compares crop rotations with a prototype score, illustrative "
            "climate scenarios, and explicit data provenance."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.config = config
    app.state.rotator = sim.Rotator()
    app.state.rotator.fit()  # scikit-learn fallback model (baseline)

    # CORS for the Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- routes ------------------------------------------------------------ #
    app.include_router(api.router, prefix="/api")

    # ---- global exception handler ----------------------------------------- #
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.status_code},
        )

    # ---- root + static frontend --------------------------------------------- #
    @app.get("/health")
    def health(request: Request) -> dict:
        return {"status": "ok", "service": "nex-terra", "engine": "rotation-simulator"}

    @app.get("/")
    def index(request: Request) -> FileResponse:
        frontend = BASE_DIR / ".." / "front" / "dist"
        if frontend.is_dir():
            index_file = frontend / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
        return FileResponse(BASE_DIR / "public" / "index.html")

    # ---- startup ----------------------------------------------------------- #
    @app.on_event("startup")
    async def _startup() -> None:
        log.info("NEX TERRA starting on %s:%s", config.config.host, config.config.port)
        log.info("data dir: %s", DATA_DIR)
        try:
            with open(DATA_DIR / "config.json", encoding="utf-8") as f:
                cfg = json.load(f)
            app.state.field_config = cfg.get("field", {})
            app.state.scenarios = cfg.get("scenarios", app.state.field_config.get(
                "scenarios", []))
        except FileNotFoundError:
            app.state.field_config = {}
            app.state.scenarios = []
        except json.JSONDecodeError as e:
            log.warning("config.json unreadable: %s", e)
            app.state.field_config = {}
            app.state.scenarios = []

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        log.info("NEX TERRA shutting down")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
