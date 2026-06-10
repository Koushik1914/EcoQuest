"""
EcoQuest Leaderboard Engine
Fair scoring: improvement_pct × 0.6 + normalized_action_pts × 0.4
Excludes users without baselines or fewer than 3 completed actions.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.models import (
    ClubLeaderboardEntry,
    ClubLeaderboardResponse,
    ClubType,
    LeaderboardEntry,
    LeaderboardResponse,
    RankTier,
)

logger = logging.getLogger(__name__)

# ── Scoring constants ─────────────────────────────────────────────────────────
IMPROVEMENT_WEIGHT: float = 0.6
ACTION_WEIGHT: float = 0.4
MIN_ACTIONS_REQUIRED: int = 3

# ── Rank tier point thresholds ────────────────────────────────────────────────
RANK_TIERS: list[tuple[RankTier, int]] = [
    (RankTier.PLANET_PROTECTOR,  300),
    (RankTier.CLIMATE_CHAMPION,  151),
    (RankTier.ECO_EXPLORER,       51),
    (RankTier.SEEDLING,            0),
]


def determine_rank_tier(total_points: int) -> RankTier:
    """Return the rank tier for a given total points value."""
    for tier, threshold in RANK_TIERS:
        if total_points >= threshold:
            return tier
    return RankTier.SEEDLING


def calculate_improvement_pct(baseline_kg: float, current_kg: float) -> float:
    """
    Calculate improvement percentage clamped to [0, 100].
    Negative improvement (footprint increased) is treated as 0.
    Division by zero (baseline=0) returns 0.
    """
    if baseline_kg <= 0:
        return 0.0
    raw = ((baseline_kg - current_kg) / baseline_kg) * 100.0
    return round(max(0.0, min(100.0, raw)), 2)


def calculate_rank_score(
    improvement_pct: float,
    user_total_points: int,
    max_points_in_cohort: int,
) -> float:
    """
    Composite rank score formula:
      rank_score = (improvement_pct × 0.6) + (normalized_action_pts × 0.4)

    normalized_action_pts = (user_total_points / max_points_in_cohort) × 100
    If max_points is 0 (single-user cohort), normalisation returns 0.
    """
    if max_points_in_cohort <= 0:
        normalized = 0.0
    else:
        normalized = (user_total_points / max_points_in_cohort) * 100.0

    score = (improvement_pct * IMPROVEMENT_WEIGHT) + (normalized * ACTION_WEIGHT)
    return round(score, 4)


def is_eligible_for_leaderboard(user: dict[str, Any]) -> bool:
    """
    Return True if the user meets leaderboard eligibility requirements:
      - Has a baseline submission (baseline_kg is not None)
      - Has completed at least MIN_ACTIONS_REQUIRED challenges
    """
    has_baseline = user.get("baseline_kg") is not None
    action_count = user.get("completed_challenges_count", 0)
    return has_baseline and action_count >= MIN_ACTIONS_REQUIRED


def build_individual_leaderboard(
    users: list[dict[str, Any]],
    requesting_user_id: str | None = None,
    top_n: int = 50,
) -> LeaderboardResponse:
    """
    Build the individual leaderboard from a list of raw user dicts.

    Scoring steps:
      1. Filter ineligible users
      2. Calculate improvement_pct for each
      3. Find max_points_in_cohort
      4. Calculate rank_score for each
      5. Sort descending by rank_score, tie-break by total_points then display_name
      6. Return top_n entries + always include requesting_user if present
    """
    eligible = [u for u in users if is_eligible_for_leaderboard(u)]

    if not eligible:
        return LeaderboardResponse(
            entries=[],
            current_user_rank=None,
            total_eligible_users=0,
            generated_at=datetime.utcnow(),
        )

    max_points = max(u.get("total_points", 0) for u in eligible)

    scored: list[dict[str, Any]] = []
    for user in eligible:
        improvement = calculate_improvement_pct(
            baseline_kg=user.get("baseline_kg", 0.0),
            current_kg=user.get("current_monthly_kg", user.get("baseline_kg", 0.0)),
        )
        rank_score = calculate_rank_score(
            improvement_pct=improvement,
            user_total_points=user.get("total_points", 0),
            max_points_in_cohort=max_points,
        )
        scored.append({**user, "_improvement_pct": improvement, "_rank_score": rank_score})

    # Sort: rank_score DESC, total_points DESC, display_name ASC (stable tie-break)
    scored.sort(
        key=lambda u: (-u["_rank_score"], -u.get("total_points", 0), u.get("display_name", ""))
    )

    current_user_rank: int | None = None
    for idx, user in enumerate(scored, start=1):
        if user.get("user_id") == requesting_user_id:
            current_user_rank = idx
            break

    entries: list[LeaderboardEntry] = []
    in_top_n_ids: set[str] = set()

    for rank, user in enumerate(scored[:top_n], start=1):
        uid = user.get("user_id", "")
        in_top_n_ids.add(uid)
        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=uid,
                display_name=user.get("display_name", "Anonymous"),
                avatar_emoji=user.get("avatar_emoji", "🌱"),
                city=user.get("city", "India"),
                rank_tier=determine_rank_tier(user.get("total_points", 0)),
                improvement_pct=user["_improvement_pct"],
                total_points=user.get("total_points", 0),
                rank_score=user["_rank_score"],
                total_co2_saved_kg=user.get("total_co2_saved_kg", 0.0),
                is_current_user=(uid == requesting_user_id),
            )
        )

    # Sticky row: if requesting user is outside top_n, append their entry
    if (
        requesting_user_id is not None
        and requesting_user_id not in in_top_n_ids
        and current_user_rank is not None
    ):
        user = scored[current_user_rank - 1]
        uid = user.get("user_id", "")
        entries.append(
            LeaderboardEntry(
                rank=current_user_rank,
                user_id=uid,
                display_name=user.get("display_name", "Anonymous"),
                avatar_emoji=user.get("avatar_emoji", "🌱"),
                city=user.get("city", "India"),
                rank_tier=determine_rank_tier(user.get("total_points", 0)),
                improvement_pct=user["_improvement_pct"],
                total_points=user.get("total_points", 0),
                rank_score=user["_rank_score"],
                total_co2_saved_kg=user.get("total_co2_saved_kg", 0.0),
                is_current_user=True,
            )
        )

    return LeaderboardResponse(
        entries=entries,
        current_user_rank=current_user_rank,
        total_eligible_users=len(eligible),
        generated_at=datetime.utcnow(),
    )


def build_club_leaderboard(clubs: list[dict[str, Any]]) -> ClubLeaderboardResponse:
    """
    Build the club leaderboard.
    Score = (total_co2_saved × 0.5) + (total_action_points × 0.5 / normalised)
    """
    if not clubs:
        return ClubLeaderboardResponse(
            entries=[],
            total_clubs=0,
            generated_at=datetime.utcnow(),
        )

    max_co2 = max(c.get("total_co2_saved", 0.0) for c in clubs) or 1.0
    max_pts = max(c.get("total_action_points", 0) for c in clubs) or 1

    def club_score(club: dict[str, Any]) -> float:
        co2_norm = (club.get("total_co2_saved", 0.0) / max_co2) * 100.0
        pts_norm = (club.get("total_action_points", 0) / max_pts) * 100.0
        return round(co2_norm * 0.5 + pts_norm * 0.5, 4)

    sorted_clubs = sorted(clubs, key=club_score, reverse=True)

    entries = [
        ClubLeaderboardEntry(
            rank=rank,
            club_id=c.get("id", ""),
            name=c.get("name", ""),
            club_type=ClubType(c.get("club_type", "college")),
            member_count=c.get("member_count", 0),
            total_co2_saved=c.get("total_co2_saved", 0.0),
            total_action_points=c.get("total_action_points", 0),
            score=club_score(c),
        )
        for rank, c in enumerate(sorted_clubs, start=1)
    ]

    return ClubLeaderboardResponse(
        entries=entries,
        total_clubs=len(clubs),
        generated_at=datetime.utcnow(),
    )
