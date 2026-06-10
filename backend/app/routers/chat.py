"""
EcoQuest Chat Router
POST /chat          — Stream AI response via Server-Sent Events (SSE)
GET  /chat/history  — Retrieve last 20 messages for a user
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.database import Collections, paginated_query
from app.models import ChatHistoryResponse, ChatMessage, ChatRequest
from app.services.ai_agent import get_chat_history, stream_ai_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Rate limiting: simple in-memory store (Redis recommended for multi-instance) ──
_request_counts: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW_SECONDS: int = 60


def _check_rate_limit(client_ip: str, limit: int) -> None:
    """
    Sliding-window rate limiter (in-memory).
    Raises HTTP 429 if the client exceeds `limit` requests per 60 seconds.
    """
    import time  # noqa: PLC0415

    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    timestamps = _request_counts.get(client_ip, [])
    # Prune old timestamps
    timestamps = [t for t in timestamps if t > window_start]

    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per minute.",
            headers={"Retry-After": "60"},
        )

    timestamps.append(now)
    _request_counts[client_ip] = timestamps


@router.post(
    "",
    summary="Send a message to EcoBuddy AI (SSE streaming)",
    response_description="Server-Sent Events stream of AI response chunks",
)
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip, settings.chat_rate_limit_per_minute)

    async def event_generator():
        try:
            async for chunk in stream_ai_response(
                user_id=payload.user_id,
                user_message=payload.message,
            ):
                # SSE format: data: <payload>\n\n
                safe_chunk = chunk.replace("\n", "\\n")
                yield f"data: {safe_chunk}\n\n"
                await asyncio.sleep(0)  # yield control to event loop
        except Exception as exc:  # noqa: BLE001
            logger.error("SSE stream error for user=%s: %s", payload.user_id, exc)
            yield "data: [ERROR] An error occurred. Please try again.\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Retrieve chat history for a user",
)
async def chat_history(
    user_id: str,
    request: Request,
) -> ChatHistoryResponse:
    if len(user_id) > 128:
        raise HTTPException(status_code=400, detail="user_id too long.")

    raw_messages = await get_chat_history(user_id)

    messages = [
        ChatMessage(
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            timestamp=msg.get("timestamp"),
        )
        for msg in raw_messages
    ]

    return ChatHistoryResponse(
        user_id=user_id,
        messages=messages,
        total_messages=len(messages),
    )
