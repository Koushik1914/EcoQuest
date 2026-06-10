"""
EcoQuest Challenges Router
GET  /challenges                       — List all active challenges
POST /challenges/{id}/complete         — Mark a challenge complete for a user
POST /internal/challenges/rotate       — Cloud Scheduler: rotate weekly challenges
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.database import (
    Collections,
    atomic_increment,
    batch_write,
    get_document,
    get_firestore,
    paginated_query,
    set_document,
)
from app.models import (
    Challenge,
    ChallengeCompletionRequest,
    ChallengeCompletionResponse,
)
from app.services.challenge_engine import (
    PREDEFINED_CHALLENGES,
    STREAK_BONUS_POINTS,
    build_rotated_challenges,
    calculate_new_streak,
    calculate_points_for_completion,
    is_duplicate_completion,
    is_milestone_reached,
)
from app.services.leaderboard_engine import determine_rank_tier

logger = logging.getLogger(__name__)
router = APIRouter(tags=["challenges"])
security = HTTPBearer()


# ── Internal auth dependency ──────────────────────────────────────────────────
async def verify_internal_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    settings = get_settings()
    expected = settings.internal_auth_token
    if not expected or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal authentication token.",
        )
    return credentials.credentials


# ── List active challenges ─────────────────────────────────────────────────────
@router.get(
    "/challenges",
    response_model=list[Challenge],
    summary="List all active challenges",
)
async def list_challenges(request: Request) -> list[Challenge]:
    docs, _ = await paginated_query(
        collection=Collections.CHALLENGES,
        filters=[("is_active", "==", True)],
        order_by="difficulty",
        limit=50,
    )

    challenges = []
    for doc in docs:
        try:
            challenges.append(
                Challenge(
                    id=doc["id"],
                    title=doc["title"],
                    description=doc["description"],
                    category=doc["category"],
                    difficulty=doc["difficulty"],
                    points=doc["points"],
                    co2_savings_kg=doc["co2_savings_kg"],
                    frequency=doc["frequency"],
                    active_from=datetime.fromisoformat(str(doc["active_from"])),
                    active_until=datetime.fromisoformat(str(doc["active_until"])),
                    is_active=doc.get("is_active", True),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed challenge doc '%s': %s", doc.get("id"), exc)

    return challenges


# ── Complete a challenge ──────────────────────────────────────────────────────
@router.post(
    "/challenges/{challenge_id}/complete",
    response_model=ChallengeCompletionResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark a challenge as complete for a user",
)
async def complete_challenge(
    challenge_id: str,
    payload: ChallengeCompletionRequest,
    request: Request,
) -> ChallengeCompletionResponse:
    if len(challenge_id) > 128:
        raise HTTPException(status_code=400, detail="challenge_id too long.")

    # Load challenge
    challenge = await get_document(Collections.CHALLENGES, challenge_id)
    if challenge is None or not challenge.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found or inactive.",
        )

    # Load user
    user = await get_document(Collections.USERS, payload.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Complete the quiz first.",
        )

    # Load this user's completions for this challenge
    db = get_firestore()
    uc_ref = (
        db.collection(Collections.USER_CHALLENGES)
        .where("user_id", "==", payload.user_id)
        .where("challenge_id", "==", challenge_id)
    )
    completions = [snap.to_dict() async for snap in uc_ref.stream()]
    completion_dates: list[datetime] = [
        datetime.fromisoformat(str(c["completed_at"])) for c in completions
        if c.get("completed_at")
    ]

    # Deduplication check
    if is_duplicate_completion(completion_dates, challenge.get("frequency", "daily")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge already completed within its frequency window.",
        )

    # Compute points + streak
    base_points, bonus_points = calculate_points_for_completion(challenge)
    total_awarded = base_points + bonus_points

    now = datetime.utcnow()
    last_completed = user.get("last_challenge_completed_at")
    if isinstance(last_completed, str):
        last_completed = datetime.fromisoformat(last_completed)

    new_streak = calculate_new_streak(
        current_streak=user.get("current_streak", 0),
        last_completed_at=last_completed,
    )
    milestone_hit = is_milestone_reached(new_streak)
    streak_bonus = STREAK_BONUS_POINTS if milestone_hit else 0
    total_awarded += streak_bonus

    new_total_points = user.get("total_points", 0) + total_awarded
    new_co2_saved = user.get("total_co2_saved_kg", 0.0) + challenge.get("co2_savings_kg", 0.0)
    new_longest = max(user.get("longest_streak", 0), new_streak)

    # ── Batch write: user update + completion record ───────────────────────────
    completion_doc_id = f"{payload.user_id}_{challenge_id}_{now.strftime('%Y%m%d%H%M%S')}"
    ops = [
        {
            "type": "set",
            "collection": Collections.USER_CHALLENGES,
            "doc_id": completion_doc_id,
            "data": {
                "user_id": payload.user_id,
                "challenge_id": challenge_id,
                "completed_at": now,
                "points_earned": total_awarded,
                "co2_saved_kg": challenge.get("co2_savings_kg", 0.0),
                "streak_at_completion": new_streak,
                "note": payload.note or "",
            },
            "merge": False,
        },
        {
            "type": "set",
            "collection": Collections.USERS,
            "doc_id": payload.user_id,
            "data": {
                "total_points": new_total_points,
                "current_streak": new_streak,
                "longest_streak": new_longest,
                "total_co2_saved_kg": new_co2_saved,
                "completed_challenges_count": user.get("completed_challenges_count", 0) + 1,
                "rank_tier": determine_rank_tier(new_total_points).value,
                "last_challenge_completed_at": now,
            },
            "merge": True,
        },
    ]
    await batch_write(ops)

    logger.info(
        "Challenge completed: user=%s challenge=%s points=%d streak=%d",
        payload.user_id,
        challenge_id,
        total_awarded,
        new_streak,
    )

    return ChallengeCompletionResponse(
        challenge_id=challenge_id,
        user_id=payload.user_id,
        points_awarded=base_points + bonus_points,
        streak_bonus=streak_bonus,
        new_total_points=new_total_points,
        new_streak=new_streak,
        milestone_reached=milestone_hit,
        co2_saved_kg=challenge.get("co2_savings_kg", 0.0),
        completed_at=now,
    )


# ── Internal: rotate challenges ───────────────────────────────────────────────
@router.post(
    "/internal/challenges/rotate",
    status_code=status.HTTP_200_OK,
    summary="Rotate weekly challenges (Cloud Scheduler only)",
    include_in_schema=False,
)
async def rotate_challenges(
    request: Request,
    _token: str = Depends(verify_internal_token),
) -> dict:
    now = datetime.utcnow()
    rotated = build_rotated_challenges(rotation_start=now)

    # Mark all existing challenges inactive
    db = get_firestore()
    active_snaps = [
        snap async for snap in db.collection(Collections.CHALLENGES)
        .where("is_active", "==", True)
        .stream()
    ]
    deactivate_ops = [
        {
            "type": "update",
            "collection": Collections.CHALLENGES,
            "doc_id": snap.id,
            "data": {"is_active": False},
        }
        for snap in active_snaps
    ]
    if deactivate_ops:
        await batch_write(deactivate_ops)

    # Write new challenges
    new_ops = [
        {
            "type": "set",
            "collection": Collections.CHALLENGES,
            "doc_id": ch["id"],
            "data": {**ch, "is_active": True},
            "merge": False,
        }
        for ch in rotated
    ]
    await batch_write(new_ops)

    logger.info("Challenge rotation complete: %d challenges activated.", len(rotated))
    return {"rotated": len(rotated), "rotated_at": now.isoformat()}
