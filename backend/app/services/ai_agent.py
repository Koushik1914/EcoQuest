"""
EcoQuest AI Agent Service
Vertex AI Gemini 2.5 Flash client with streaming SSE, context injection,
fallback handling, and Firestore chat history persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, AsyncGenerator

import vertexai
from vertexai.generative_models import (
    Content,
    GenerationConfig,
    GenerativeModel,
    Part,
    SafetySetting,
    HarmCategory,
    HarmBlockThreshold,
)

from app.config import get_settings
from app.database import (
    Collections,
    get_document,
    get_firestore,
    paginated_query,
    set_document,
)

logger = logging.getLogger(__name__)

# ── Safety settings — balanced for sustainability coaching ────────────────────
SAFETY_SETTINGS = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

GENERATION_CONFIG = GenerationConfig(
    temperature=0.7,
    top_p=0.9,
    max_output_tokens=512,
)

MAX_HISTORY_MESSAGES: int = 20

SYSTEM_PROMPT = """You are EcoBuddy, a hyper-personalized sustainability coach inside EcoQuest. Your advice must be:

— Tailored to the user's exact profile (never generic)
— Financially realistic (no expensive solutions for students)
— Quantified (include estimated monthly CO₂ savings for every tip)
— Encouraging without being preachy
— Under 180 words unless the user explicitly requests detail

If the user already performs well, coach them toward community leadership and club engagement.

Format all responses with emoji headers and bullet points.
End every response with one actionable next step."""


def _build_system_context(user_profile: dict[str, Any]) -> str:
    """Inject user profile data into the system context for personalisation."""
    return f"""
User Profile Context:
- User type: {user_profile.get('user_type', 'unknown')}
- City: {user_profile.get('city', 'India')}
- Monthly carbon footprint: {user_profile.get('current_monthly_kg', 'unknown')} kg CO₂
- Biggest emission category: {user_profile.get('biggest_emission_category', 'unknown')}
- Completed challenges: {user_profile.get('completed_challenges_count', 0)}
- Current streak: {user_profile.get('current_streak', 0)} days
- Rank tier: {user_profile.get('rank_tier', 'seedling')}
- Total CO₂ saved: {user_profile.get('total_co2_saved_kg', 0)} kg

{SYSTEM_PROMPT}
"""


def init_vertex_ai() -> None:
    """Initialise Vertex AI SDK with project and region from settings."""
    settings = get_settings()
    vertexai.init(
        project=settings.gcp_project_id,
        location=settings.vertex_ai_location,
    )
    logger.info(
        "Vertex AI initialised (project=%s, location=%s, model=%s)",
        settings.gcp_project_id,
        settings.vertex_ai_location,
        settings.vertex_ai_model,
    )


async def get_chat_history(user_id: str) -> list[dict[str, Any]]:
    """Retrieve the last MAX_HISTORY_MESSAGES messages for a user."""
    docs, _ = await paginated_query(
        collection=Collections.CHAT_HISTORY,
        filters=[("user_id", "==", user_id)],
        order_by="timestamp",
        descending=True,
        limit=MAX_HISTORY_MESSAGES,
    )
    # Reverse so oldest-first for Gemini conversation history
    return list(reversed(docs))


async def save_message(
    user_id: str,
    role: str,
    content: str,
    timestamp: datetime,
) -> None:
    """Persist a single chat message to Firestore."""
    db = get_firestore()
    msg_ref = db.collection(Collections.CHAT_HISTORY).document()
    await msg_ref.set(
        {
            "user_id": user_id,
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }
    )

    # Prune: keep only the latest MAX_HISTORY_MESSAGES per user
    all_msgs, _ = await paginated_query(
        collection=Collections.CHAT_HISTORY,
        filters=[("user_id", "==", user_id)],
        order_by="timestamp",
        descending=True,
        limit=MAX_HISTORY_MESSAGES + 10,
    )
    if len(all_msgs) > MAX_HISTORY_MESSAGES:
        for old_msg in all_msgs[MAX_HISTORY_MESSAGES:]:
            ref = db.collection(Collections.CHAT_HISTORY).document(old_msg["id"])
            await ref.delete()


async def get_fallback_tip() -> str:
    """
    Return a pre-cached sustainability tip from Firestore when
    Vertex AI quota is exceeded or unavailable.
    """
    try:
        docs, _ = await paginated_query(
            collection=Collections.AI_FALLBACK_TIPS,
            limit=1,
        )
        if docs:
            return docs[0].get(
                "content",
                "🌱 **Quick Tip:** Try going car-free one day this week to save ~2 kg CO₂!",
            )
    except Exception:  # noqa: BLE001
        pass

    return (
        "🌱 **Quick Tip:** Small actions compound into big impact.\n\n"
        "• 🚌 Take public transport once this week → saves ~2 kg CO₂\n"
        "• 🥗 Choose a plant-based lunch today → saves ~1.5 kg CO₂\n"
        "• 🔌 Unplug chargers when not in use → saves ~0.8 kg CO₂/month\n\n"
        "**Next step:** Complete your first challenge on the Challenges page!"
    )


async def stream_ai_response(
    user_id: str,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream an AI response via Vertex AI Gemini with SSE-compatible chunks.
    Falls back to a cached tip if Vertex AI is unavailable.

    Yields:
        String chunks of the assistant's response as they are generated.
    """
    settings = get_settings()

    # Load user profile for context injection
    user_profile = await get_document(Collections.USERS, user_id) or {}

    # Load conversation history
    history_docs = await get_chat_history(user_id)
    history: list[Content] = []
    for msg in history_docs:
        role = "user" if msg.get("role") == "user" else "model"
        history.append(
            Content(role=role, parts=[Part.from_text(msg.get("content", ""))])
        )

    # Persist user message before streaming
    now = datetime.utcnow()
    await save_message(user_id, "user", user_message, now)

    try:
        model = GenerativeModel(
            model_name=settings.vertex_ai_model,
            system_instruction=_build_system_context(user_profile),
            safety_settings=SAFETY_SETTINGS,
            generation_config=GENERATION_CONFIG,
        )

        chat = model.start_chat(history=history)
        full_response: list[str] = []

        async for chunk in await chat.send_message_async(
            user_message, stream=True
        ):
            text = chunk.text
            if text:
                full_response.append(text)
                yield text

        # Persist assistant response
        assistant_content = "".join(full_response)
        await save_message(user_id, "assistant", assistant_content, datetime.utcnow())

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Vertex AI streaming failed for user=%s: %s. Returning fallback tip.",
            user_id,
            exc,
        )
        fallback = await get_fallback_tip()
        await save_message(user_id, "assistant", fallback, datetime.utcnow())
        yield fallback
