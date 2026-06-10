"""
EcoQuest FastAPI Application Entry Point
Wires together middleware, lifespan, routers, and global exception handling.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings
from app.database import close_firestore, init_firestore
from app.models import ErrorResponse, HealthResponse
from app.routers import challenges, chat, clubs, leaderboard, posts, quiz
from app.services.ai_agent import init_vertex_ai

# ── Logging configuration ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan: startup & shutdown ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup: load secrets → init Firestore → init Vertex AI.
    Shutdown: close Firestore connection gracefully.
    """
    settings = get_settings()
    logger.info("EcoQuest %s starting in %s mode...", settings.app_version, settings.environment)

    # Load all secrets from Secret Manager before accepting traffic
    settings.load_secrets()

    # Initialise async Firestore client
    await init_firestore()

    # Initialise Vertex AI SDK
    init_vertex_ai()

    logger.info("EcoQuest startup complete. Ready to serve requests.")
    yield

    # Graceful shutdown
    await close_firestore()
    logger.info("EcoQuest shutdown complete.")


# ── Request ID middleware ─────────────────────────────────────────────────────
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique UUID to every request for traceability in Cloud Logging."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ── Security headers middleware ───────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers on every response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data: https://storage.googleapis.com; "
            "connect-src 'self'"
        )
        return response


# ── FastAPI application factory ───────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="EcoQuest API",
        description=(
            "Production-grade Carbon Footprint Awareness Platform. "
            "Powered by Vertex AI Gemini 2.5 Flash, Firestore, and Cloud Run."
        ),
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost applied last) ───────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin] if settings.frontend_origin != "*" else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(
            "Unhandled exception request_id=%s path=%s: %s",
            request_id,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                detail="An internal server error occurred. Please try again.",
                request_id=request_id,
            ).model_dump(),
        )

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Health check — used by Cloud Run and load balancer",
    )
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="healthy",
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            environment=settings.environment,
        )

    # ── Register routers ──────────────────────────────────────────────────────
    app.include_router(quiz.router)
    app.include_router(challenges.router)
    app.include_router(leaderboard.router)
    app.include_router(chat.router)
    app.include_router(posts.router)
    app.include_router(clubs.router)

    return app


app = create_app()
