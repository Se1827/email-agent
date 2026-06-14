"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.api.auth_routes import router as auth_router
from src.api.graph_routes import router as graph_router
from src.auth import AuthError, auth_configured, require_request_auth, use_auth_token
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

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        public_path = (
            path.startswith("/api/auth/")
            or path in {"/docs", "/redoc", "/openapi.json"}
        )
        if request.method == "OPTIONS" or public_path:
            return await call_next(request)
        if not auth_configured():
            return JSONResponse(
                status_code=428,
                content={"detail": "Authentication setup is required"},
            )
        try:
            token = require_request_auth(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        with use_auth_token(token):
            try:
                return await call_next(request)
            except (AuthError, ValueError) as exc:
                return JSONResponse(status_code=401, content={"detail": str(exc)})

    app.include_router(auth_router, prefix="/api")
    app.include_router(router, prefix="/api")
    app.include_router(graph_router, prefix="/api/graph")
    return app
