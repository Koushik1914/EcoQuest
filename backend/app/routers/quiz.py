"""
EcoQuest Quiz Router
POST /quiz/submit  — Submit full quiz, calculate footprint, store in Firestore
GET  /quiz/result/{user_id} — Retrieve the latest footprint result for a user
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.database import (
    Collections,
    batch_write,
    get_document,
    get_firestore,
    set_document,
)
from app.models import FootprintBreakdown, QuizResult, QuizSubmission, RatingLevel
from app.services.carbon_calc import (
    biggest_emission_category,
    calculate_breakdown,
    calculate_diet_kg,
    calculate_energy_kg,
    calculate_shopping_kg,
    calculate_total_footprint,
    calculate_transport_kg,
    determine_rating,
    personalized_recommendations,
    vs_national_average_pct,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post(
    "/submit",
    response_model=QuizResult,
    status_code=status.HTTP_200_OK,
    summary="Submit carbon footprint quiz",
    description=(
        "Accepts a full 5-step quiz submission, computes the monthly CO₂ footprint "
        "using IPCC AR6 + MoEFCC emission factors, stores the result in Firestore, "
        "and returns the breakdown with comparison to India's national average."
    ),
)
async def submit_quiz(payload: QuizSubmission, request: Request) -> QuizResult:
    request_id = request.state.request_id

    # ── Calculate each category ───────────────────────────────────────────────
    transport_kg = calculate_transport_kg(payload.transport)
    diet_kg = calculate_diet_kg(payload.diet)
    energy_kg = calculate_energy_kg(payload.energy)
    shopping_kg = calculate_shopping_kg(payload.lifestyle)

    total_kg = calculate_total_footprint(transport_kg, diet_kg, energy_kg, shopping_kg)
    breakdown = calculate_breakdown(transport_kg, diet_kg, energy_kg, shopping_kg)
    rating = determine_rating(total_kg)
    national_diff = vs_national_average_pct(total_kg)
    biggest_cat = biggest_emission_category(transport_kg, diet_kg, energy_kg, shopping_kg)

    now = datetime.utcnow()

    # ── Determine baseline status ─────────────────────────────────────────────
    existing_user = await get_document(Collections.USERS, payload.user_id)
    is_baseline = existing_user is None or existing_user.get("baseline_kg") is None

    # ── Build snapshot document ───────────────────────────────────────────────
    snapshot_id = f"{payload.user_id}_{now.strftime('%Y%m')}"
    snapshot_doc = {
        "user_id": payload.user_id,
        "total_monthly_kg": total_kg,
        "transport_kg": transport_kg,
        "food_kg": diet_kg,
        "energy_kg": energy_kg,
        "shopping_kg": shopping_kg,
        "transport_pct": breakdown.transport_pct,
        "food_pct": breakdown.food_pct,
        "energy_pct": breakdown.energy_pct,
        "shopping_pct": breakdown.shopping_pct,
        "rating": rating.value,
        "calculated_at": now,
        "quiz_inputs": {
            "transport_mode": payload.transport.mode.value,
            "weekly_km": payload.transport.weekly_km,
            "meat_frequency": payload.diet.meat_frequency.value,
            "energy_bill": payload.energy.monthly_bill_inr.value,
            "recycling": payload.lifestyle.recycling.value,
            "shopping_frequency": payload.lifestyle.shopping_frequency.value,
        },
    }

    # ── Build user profile upsert ─────────────────────────────────────────────
    user_update: dict = {
        "user_id": payload.user_id,
        "display_name": payload.display_name,
        "city": payload.profile.city,
        "user_type": payload.profile.user_type.value,
        "current_monthly_kg": total_kg,
        "biggest_emission_category": biggest_cat,
        "last_quiz_at": now,
    }
    if is_baseline:
        user_update["baseline_kg"] = total_kg
        user_update["joined_at"] = now
        user_update["total_points"] = 0
        user_update["current_streak"] = 0
        user_update["longest_streak"] = 0
        user_update["rank_tier"] = "seedling"
        user_update["completed_challenges_count"] = 0
        user_update["total_co2_saved_kg"] = 0.0
        user_update["avatar_emoji"] = "🌱"

    # ── Batch write snapshot + user update ────────────────────────────────────
    ops = [
        {
            "type": "set",
            "collection": Collections.FOOTPRINT_SNAPSHOTS,
            "doc_id": snapshot_id,
            "data": snapshot_doc,
            "merge": False,
        },
        {
            "type": "set",
            "collection": Collections.USERS,
            "doc_id": payload.user_id,
            "data": user_update,
            "merge": True,
        },
    ]
    await batch_write(ops)

    logger.info(
        "Quiz submitted: user=%s total=%.2f kg is_baseline=%s request_id=%s",
        payload.user_id,
        total_kg,
        is_baseline,
        request_id,
    )

    return QuizResult(
        user_id=payload.user_id,
        total_monthly_kg=total_kg,
        breakdown=breakdown,
        transport_kg=transport_kg,
        food_kg=diet_kg,
        energy_kg=energy_kg,
        shopping_kg=shopping_kg,
        vs_national_avg_pct=national_diff,
        rating=rating,
        is_baseline=is_baseline,
        calculated_at=now,
    )


@router.get(
    "/result/{user_id}",
    response_model=QuizResult,
    summary="Get latest quiz result for user",
)
async def get_quiz_result(user_id: str, request: Request) -> QuizResult:
    if len(user_id) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id exceeds maximum length.",
        )

    user = await get_document(Collections.USERS, user_id)
    if user is None or user.get("current_monthly_kg") is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No quiz result found for this user.",
        )

    # Find latest monthly snapshot
    db = get_firestore()
    snapshots_ref = (
        db.collection(Collections.FOOTPRINT_SNAPSHOTS)
        .where("user_id", "==", user_id)
        .order_by("calculated_at", direction="DESCENDING")
        .limit(1)
    )
    snaps = [s async for s in snapshots_ref.stream()]
    if not snaps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No footprint snapshot found for this user.",
        )

    snap = snaps[0].to_dict()
    breakdown = FootprintBreakdown(
        transport_pct=snap.get("transport_pct", 0.0),
        food_pct=snap.get("food_pct", 0.0),
        energy_pct=snap.get("energy_pct", 0.0),
        shopping_pct=snap.get("shopping_pct", 0.0),
    )

    total_kg = snap.get("total_monthly_kg", 0.0)

    return QuizResult(
        user_id=user_id,
        total_monthly_kg=total_kg,
        breakdown=breakdown,
        transport_kg=snap.get("transport_kg", 0.0),
        food_kg=snap.get("food_kg", 0.0),
        energy_kg=snap.get("energy_kg", 0.0),
        shopping_kg=snap.get("shopping_kg", 0.0),
        vs_national_avg_pct=vs_national_average_pct(total_kg),
        rating=RatingLevel(snap.get("rating", "green")),
        is_baseline=False,
        calculated_at=snap.get("calculated_at", datetime.utcnow()),
    )
