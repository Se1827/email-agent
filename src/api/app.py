"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.logging import setup_logging
from src.config import get_settings
from src.observability import setup_telemetry
from src.storage import init_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup / shutdown."""
    setup_logging(get_settings().log_level)
    init_storage()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Intelligent Email Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    setup_telemetry(app, settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app
