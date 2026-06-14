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
        version="1.0.0",
        lifespan=lifespan,
    )
    setup_telemetry(app, settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Public endpoints (no auth required) ─────────────────────────────
    @app.get("/api/health")
    async def health_check():
        """System health check — shows configured features and version."""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "model": settings.groq_model,
            "features": {
                "ai_mode": settings.ai_mode,
                "pii_mode": settings.pii_mode,
                "email_source": settings.email_source,
                "storage_enabled": settings.storage_enabled,
                "otel_enabled": settings.otel_enabled,
                "graph_integration": True,
            },
            "agents": ["supervisor", "calendar", "classification", "draft", "memory", "thread"],
            "evaluation": {
                "golden_dataset_cases": 8,
                "pii_entity_types": [
                    "EMAIL_ADDRESS", "US_SSN", "CREDIT_CARD", "PHONE_NUMBER",
                    "BANK_ACCOUNT", "ROUTING_NUMBER", "API_KEY", "PERSON", "LOCATION",
                ],
            },
        }

    @app.get("/api/architecture")
    async def get_architecture():
        """Return a structured system architecture for demo/documentation."""
        return {
            "name": "Intelligent Email Agent",
            "tagline": "AI-powered email triage with PII protection and calendar awareness",
            "pipeline": [
                {
                    "step": 1, "name": "Email Ingestion",
                    "components": ["IMAP Connector", "Microsoft Graph Connector", "Mock Connector"],
                    "description": "Multi-source email ingestion with IMAP IDLE push notifications and Microsoft Graph API",
                },
                {
                    "step": 2, "name": "Rule Engine Pre-Pass",
                    "components": ["Spam Detection", "VIP Sender Check", "Urgent Keywords"],
                    "description": "Deterministic classification shortcuts — zero LLM calls for obvious spam/newsletters/VIP senders",
                },
                {
                    "step": 3, "name": "PII Masking",
                    "components": ["Regex Scanner", "Presidio Analyzer", "spaCy NER"],
                    "description": "3-tier privacy gateway: regex → lazy semantic → strict Presidio. Masks SSNs, credit cards, bank accounts, API keys, names before LLM",
                },
                {
                    "step": 4, "name": "AI Classification",
                    "components": ["LangChain + Groq (Llama 3.3 70B)", "Calendar Context Injection", "Date Resolution"],
                    "description": "Priority (critical/high/normal/low) + category (meeting/deadline/info/action-required/spam) with calendar conflict awareness",
                },
                {
                    "step": 5, "name": "Draft Generation",
                    "components": ["Quality Tiers (quick/balanced/thorough)", "Availability Injection", "PII Rehydration + Re-scan"],
                    "description": "Context-aware reply drafting with thread history, availability mandates, and hallucinated-PII detection",
                },
                {
                    "step": 6, "name": "User Approval",
                    "components": ["Edit-before-send", "Draft Alternatives", "Approve/Reject Flow"],
                    "description": "Human-in-the-loop: user reviews, edits, and explicitly approves before any email is sent",
                },
            ],
            "ai_modes": {
                "classic": "Single-pass pipeline: rule engine → PII → classify → draft. Fast, cheap (~2 LLM calls/email)",
                "ai_rich": "Multi-agent orchestration: Supervisor → Calendar Agent → Classification Agent → Draft Agent. Higher quality, more LLM calls",
            },
            "integrations": [
                "IMAP/SMTP (any provider)",
                "Microsoft Graph (Outlook/Teams/Calendar)",
                "MCP Server (Claude Desktop/Cursor)",
            ],
            "security": [
                "Password-based auth (PBKDF2)",
                "Encrypted PostgreSQL storage (Fernet)",
                "PII never reaches LLM in raw form",
                "No hardcoded secrets (dotenv + key vault pattern)",
            ],
            "observability": [
                "OpenTelemetry tracing (OTLP export)",
                "Structured JSON logging",
                "Evaluation framework with 8-case golden dataset",
                "Per-case pipeline trace (prompt → LLM → output)",
            ],
        }

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        """Return a clean 401 when encrypted data cannot be read in request context."""
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        public_path = (
            path.startswith("/api/auth/")
            or path.startswith("/api/health")
            or path.startswith("/api/architecture")
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
        # Keep the module-level token fresh so background threads (IDLE, sync)
        # always have an auth context even after the request context is gone.
        from src.api.routes import _set_background_token
        _set_background_token(token)
        with use_auth_token(token):
            return await call_next(request)

    app.include_router(auth_router, prefix="/api")
    app.include_router(router, prefix="/api")
    app.include_router(graph_router, prefix="/api/graph")
    return app
