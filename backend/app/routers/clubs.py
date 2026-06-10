"""
EcoQuest Clubs Router
GET  /clubs           — List all clubs
POST /clubs/{id}/join — Join a club (atomic member_count increment)
GET  /clubs/{id}      — Get single club details
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.database import (
    Collections,
    atomic_increment,
    get_document,
    paginated_query,
    set_document,
)
from app.models import (
    Club,
    ClubListResponse,
    ClubType,
    JoinClubRequest,
    JoinClubResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get(
    "",
    response_model=ClubListResponse,
    summary="List all eco clubs sorted by collective impact",
)
async def list_clubs(request: Request) -> ClubListResponse:
    docs, _ = await paginated_query(
        collection=Collections.CLUBS,
        order_by="total_co2_saved",
        descending=True,
        limit=100,
    )

    clubs = []
    for doc in docs:
        try:
            clubs.append(
                Club(
                    id=doc["id"],
                    name=doc["name"],
                    club_type=ClubType(doc.get("club_type", "college")),
                    description=doc.get("description", ""),
                    member_count=doc.get("member_count", 0),
                    total_co2_saved=doc.get("total_co2_saved", 0.0),
                    total_action_points=doc.get("total_action_points", 0),
                    national_rank=doc.get("national_rank"),
                    created_at=doc.get("created_at", datetime.utcnow()),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed club doc '%s': %s", doc.get("id"), exc)

    return ClubListResponse(clubs=clubs, total=len(clubs))


@router.get(
    "/{club_id}",
    response_model=Club,
    summary="Get club details by ID",
)
async def get_club(club_id: str, request: Request) -> Club:
    if len(club_id) > 128:
        raise HTTPException(status_code=400, detail="club_id too long.")

    doc = await get_document(Collections.CLUBS, club_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club not found.",
        )

    return Club(
        id=doc["id"],
        name=doc["name"],
        club_type=ClubType(doc.get("club_type", "college")),
        description=doc.get("description", ""),
        member_count=doc.get("member_count", 0),
        total_co2_saved=doc.get("total_co2_saved", 0.0),
        total_action_points=doc.get("total_action_points", 0),
        national_rank=doc.get("national_rank"),
        created_at=doc.get("created_at", datetime.utcnow()),
    )


@router.post(
    "/{club_id}/join",
    response_model=JoinClubResponse,
    status_code=status.HTTP_200_OK,
    summary="Join a club — atomic member_count increment",
)
async def join_club(
    club_id: str,
    payload: JoinClubRequest,
    request: Request,
) -> JoinClubResponse:
    if len(club_id) > 128:
        raise HTTPException(status_code=400, detail="club_id too long.")

    # Verify club exists
    club = await get_document(Collections.CLUBS, club_id)
    if club is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club not found.",
        )

    # Check if user already in this club
    user = await get_document(Collections.USERS, payload.user_id)
    if user and user.get("club_id") == club_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this club.",
        )

    now = datetime.utcnow()

    # Atomically increment member count
    await atomic_increment(Collections.CLUBS, club_id, "member_count", 1)

    # Update user's club_id
    await set_document(
        Collections.USERS,
        payload.user_id,
        {"club_id": club_id, "club_joined_at": now},
        merge=True,
    )

    # Record membership
    membership_id = f"{payload.user_id}_{club_id}"
    await set_document(
        Collections.CLUB_MEMBERS,
        membership_id,
        {
            "user_id": payload.user_id,
            "club_id": club_id,
            "joined_at": now,
        },
        merge=False,
    )

    new_member_count = club.get("member_count", 0) + 1
    logger.info("User %s joined club %s (new count=%d)", payload.user_id, club_id, new_member_count)

    return JoinClubResponse(
        club_id=club_id,
        user_id=payload.user_id,
        new_member_count=new_member_count,
        joined_at=now,
    )
