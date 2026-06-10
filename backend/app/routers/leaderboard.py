"""
EcoQuest Leaderboard Router
GET /leaderboard/individual  — Top 50 individual users (current user always visible)
GET /leaderboard/clubs       — Club leaderboard
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.database import Collections, paginated_query
from app.models import ClubLeaderboardResponse, LeaderboardResponse
from app.services.leaderboard_engine import (
    build_club_leaderboard,
    build_individual_leaderboard,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get(
    "/individual",
    response_model=LeaderboardResponse,
    summary="Individual leaderboard — top 50 + current user sticky row",
)
async def individual_leaderboard(
    request: Request,
    user_id: Optional[str] = Query(default=None, max_length=128, description="Requesting user ID for sticky highlight"),
) -> LeaderboardResponse:
    # Fetch all users (leaderboard engine handles filtering / scoring)
    # In production with 10k+ users, this would be paginated with a pre-computed
    # leaderboard collection updated via Cloud Tasks. For hackathon scale, full scan is fine.
    users, _ = await paginated_query(
        collection=Collections.USERS,
        order_by="total_points",
        descending=True,
        limit=500,  # top 500 candidates for scoring
    )

    result = build_individual_leaderboard(
        users=users,
        requesting_user_id=user_id,
        top_n=50,
    )

    logger.info(
        "Leaderboard served: eligible=%d user=%s",
        result.total_eligible_users,
        user_id,
    )
    return result


@router.get(
    "/clubs",
    response_model=ClubLeaderboardResponse,
    summary="Club leaderboard — ranked by collective CO₂ saved + action points",
)
async def club_leaderboard(request: Request) -> ClubLeaderboardResponse:
    clubs, _ = await paginated_query(
        collection=Collections.CLUBS,
        order_by="total_co2_saved",
        descending=True,
        limit=200,
    )
    return build_club_leaderboard(clubs=clubs)
