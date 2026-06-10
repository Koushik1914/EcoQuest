"""
EcoQuest Challenge Engine
Challenge generation, completion logic, streak tracking, and bonus point awards.
All state mutations happen via the router — this module contains pure business logic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.models import (
    Challenge,
    ChallengeCategory,
    ChallengeDifficulty,
    ChallengeFrequency,
)

logger = logging.getLogger(__name__)

# ── Streak / bonus constants ───────────────────────────────────────────────────
STREAK_RESET_HOURS: int = 48          # Reset streak if gap > 48h
STREAK_MILESTONE: int = 7             # Award bonus at this streak count
STREAK_BONUS_POINTS: int = 25
HARD_CHALLENGE_BONUS: int = 5

# ── Predefined challenge definitions ─────────────────────────────────────────
# Stored as dicts so they can be seeded into Firestore on first deploy.
PREDEFINED_CHALLENGES: list[dict[str, Any]] = [
    {
        "id": "no-car-monday",
        "title": "No-Car Monday",
        "description": "Skip car usage for the entire Monday. Walk, cycle, or use public transport.",
        "category": ChallengeCategory.TRANSPORT.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 10,
        "co2_savings_kg": 2.1,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
    {
        "id": "cycle-commute-5km",
        "title": "Cycle Commute 5 km",
        "description": "Replace your motorised commute with cycling for at least 5 km today.",
        "category": ChallengeCategory.TRANSPORT.value,
        "difficulty": ChallengeDifficulty.MEDIUM.value,
        "points": 15,
        "co2_savings_kg": 3.2,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "plant-based-meal",
        "title": "Plant-Based Meal",
        "description": "Replace one meat-based meal with a fully plant-based alternative.",
        "category": ChallengeCategory.FOOD.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 10,
        "co2_savings_kg": 1.5,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "zero-meat-day",
        "title": "Zero Meat Day",
        "description": "Go completely meat-free for the entire day.",
        "category": ChallengeCategory.FOOD.value,
        "difficulty": ChallengeDifficulty.MEDIUM.value,
        "points": 18,
        "co2_savings_kg": 2.8,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "unplug-standby",
        "title": "Unplug Standby Devices",
        "description": "Switch off and unplug all devices on standby before bed.",
        "category": ChallengeCategory.ENERGY.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 8,
        "co2_savings_kg": 0.8,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "cold-water-laundry",
        "title": "Cold Water Laundry",
        "description": "Wash your laundry on a cold cycle instead of warm/hot.",
        "category": ChallengeCategory.ENERGY.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 10,
        "co2_savings_kg": 1.2,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
    {
        "id": "reusable-bag-day",
        "title": "Reusable Bag Day",
        "description": "Use only reusable bags for all shopping trips today.",
        "category": ChallengeCategory.SHOPPING.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 8,
        "co2_savings_kg": 0.4,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "zero-plastic-day",
        "title": "Zero Plastic Day",
        "description": "Avoid all single-use plastic for the entire day.",
        "category": ChallengeCategory.LIFESTYLE.value,
        "difficulty": ChallengeDifficulty.MEDIUM.value,
        "points": 12,
        "co2_savings_kg": 0.5,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "5min-shower",
        "title": "5-Minute Shower",
        "description": "Limit your shower to 5 minutes to save water and water-heating energy.",
        "category": ChallengeCategory.ENERGY.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 10,
        "co2_savings_kg": 1.0,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "start-composting",
        "title": "Start Composting",
        "description": "Set up a compost bin for kitchen scraps and commit to it for a week.",
        "category": ChallengeCategory.LIFESTYLE.value,
        "difficulty": ChallengeDifficulty.HARD.value,
        "points": 30,
        "co2_savings_kg": 5.0,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
    {
        "id": "plant-a-sapling",
        "title": "Plant a Sapling",
        "description": "Plant a native tree sapling and document it with a photo.",
        "category": ChallengeCategory.LIFESTYLE.value,
        "difficulty": ChallengeDifficulty.HARD.value,
        "points": 40,
        "co2_savings_kg": 20.0,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
    {
        "id": "carpool-to-work",
        "title": "Carpool to Work",
        "description": "Share your commute with at least one colleague today.",
        "category": ChallengeCategory.TRANSPORT.value,
        "difficulty": ChallengeDifficulty.MEDIUM.value,
        "points": 15,
        "co2_savings_kg": 3.8,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "bulk-grocery-shop",
        "title": "Bulk Grocery Shop",
        "description": "Buy groceries in bulk to reduce packaging waste and delivery trips.",
        "category": ChallengeCategory.SHOPPING.value,
        "difficulty": ChallengeDifficulty.MEDIUM.value,
        "points": 12,
        "co2_savings_kg": 1.8,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
    {
        "id": "digital-detox-hour",
        "title": "Digital Detox Hour",
        "description": "Switch off all screens for 1 hour. No phone, TV, or laptop.",
        "category": ChallengeCategory.ENERGY.value,
        "difficulty": ChallengeDifficulty.EASY.value,
        "points": 8,
        "co2_savings_kg": 0.3,
        "frequency": ChallengeFrequency.DAILY.value,
    },
    {
        "id": "public-transport-week",
        "title": "Public Transport Week",
        "description": "Commit to using only public transport for an entire work week.",
        "category": ChallengeCategory.TRANSPORT.value,
        "difficulty": ChallengeDifficulty.HARD.value,
        "points": 35,
        "co2_savings_kg": 18.0,
        "frequency": ChallengeFrequency.WEEKLY.value,
    },
]


def calculate_points_for_completion(challenge: dict[str, Any]) -> tuple[int, int]:
    """
    Return (base_points, bonus_points) for completing a challenge.
    Hard challenges receive HARD_CHALLENGE_BONUS on top of base points.
    """
    base = challenge.get("points", 0)
    bonus = HARD_CHALLENGE_BONUS if challenge.get("difficulty") == ChallengeDifficulty.HARD.value else 0
    return base, bonus


def should_update_streak(last_completed_at: datetime | None) -> bool:
    """
    Return True if the streak should be incremented (completion is within 48h).
    A streak starts fresh if last_completed_at is None.
    """
    if last_completed_at is None:
        return True
    gap = datetime.utcnow() - last_completed_at
    return gap <= timedelta(hours=STREAK_RESET_HOURS)


def is_streak_reset(last_completed_at: datetime | None) -> bool:
    """
    Return True if the 48-hour window has been missed, meaning
    the streak counter should reset to 1 (not 0) on next completion.
    """
    if last_completed_at is None:
        return False
    gap = datetime.utcnow() - last_completed_at
    return gap > timedelta(hours=STREAK_RESET_HOURS)


def calculate_new_streak(
    current_streak: int,
    last_completed_at: datetime | None,
) -> int:
    """
    Compute the new streak value after a challenge completion:
      - If last completion was within 48h: current_streak + 1
      - If beyond 48h (reset): restart at 1
      - If never completed: start at 1
    """
    if last_completed_at is None or is_streak_reset(last_completed_at):
        return 1
    return current_streak + 1


def is_milestone_reached(new_streak: int) -> bool:
    """Return True if the new streak hits the 7-day bonus milestone."""
    return new_streak > 0 and new_streak % STREAK_MILESTONE == 0


def is_duplicate_completion(
    completed_at_list: list[datetime],
    challenge_frequency: str,
) -> bool:
    """
    Return True if the challenge has already been completed within its
    allowed frequency window (daily = same calendar day, weekly = same ISO week).
    """
    if not completed_at_list:
        return False

    now = datetime.utcnow()
    last = max(completed_at_list)

    if challenge_frequency == ChallengeFrequency.DAILY.value:
        return last.date() == now.date()

    if challenge_frequency == ChallengeFrequency.WEEKLY.value:
        return (
            last.isocalendar()[:2] == now.isocalendar()[:2]  # same ISO year + week
        )

    return False


def get_challenges_for_week(
    all_challenges: list[dict[str, Any]],
    active_from: datetime,
    active_until: datetime,
) -> list[dict[str, Any]]:
    """
    Filter challenges active in the given [active_from, active_until] window.
    Used by the rotation endpoint and display layer.
    """
    return [
        c for c in all_challenges
        if c.get("is_active", True)
        and datetime.fromisoformat(str(c["active_from"])) <= active_until
        and datetime.fromisoformat(str(c["active_until"])) >= active_from
    ]


def build_rotated_challenges(
    rotation_start: datetime,
) -> list[dict[str, Any]]:
    """
    Produce the next week's challenge set for Firestore seeding.
    All 15 predefined challenges are made active for the coming week.
    """
    active_until = rotation_start + timedelta(days=7)
    rotated = []
    for ch in PREDEFINED_CHALLENGES:
        rotated.append(
            {
                **ch,
                "is_active": True,
                "active_from": rotation_start.isoformat(),
                "active_until": active_until.isoformat(),
            }
        )
    return rotated
