"""
Unit tests for leaderboard_engine.py
Fairness assertions, exclusion logic, tie-breaking, normalization, sticky row.
"""
from __future__ import annotations

import pytest

from app.services.leaderboard_engine import (
    build_individual_leaderboard,
    calculate_improvement_pct,
    calculate_rank_score,
    determine_rank_tier,
    is_eligible_for_leaderboard,
)


# ── Eligibility ───────────────────────────────────────────────────────────────

class TestEligibility:
    def test_eligible_user(self):
        user = {"baseline_kg": 200, "completed_challenges_count": 5}
        assert is_eligible_for_leaderboard(user) is True

    def test_no_baseline_excluded(self):
        user = {"baseline_kg": None, "completed_challenges_count": 5}
        assert is_eligible_for_leaderboard(user) is False

    def test_missing_baseline_key_excluded(self):
        user = {"completed_challenges_count": 10}
        assert is_eligible_for_leaderboard(user) is False

    def test_too_few_actions_excluded(self):
        user = {"baseline_kg": 200, "completed_challenges_count": 2}
        assert is_eligible_for_leaderboard(user) is False

    def test_exactly_three_actions_eligible(self):
        user = {"baseline_kg": 200, "completed_challenges_count": 3}
        assert is_eligible_for_leaderboard(user) is True

    def test_zero_actions_excluded(self):
        user = {"baseline_kg": 150, "completed_challenges_count": 0}
        assert is_eligible_for_leaderboard(user) is False


# ── Improvement percentage ────────────────────────────────────────────────────

class TestCalculateImprovementPct:
    def test_50_percent_improvement(self):
        result = calculate_improvement_pct(baseline_kg=200, current_kg=100)
        assert result == 50.0

    def test_zero_improvement_clamped(self):
        """Footprint increase should clamp to 0, not go negative."""
        result = calculate_improvement_pct(baseline_kg=100, current_kg=150)
        assert result == 0.0

    def test_100_percent_improvement_clamped(self):
        """Cannot exceed 100%."""
        result = calculate_improvement_pct(baseline_kg=100, current_kg=0)
        assert result == 100.0

    def test_zero_baseline_returns_zero(self):
        result = calculate_improvement_pct(baseline_kg=0, current_kg=50)
        assert result == 0.0

    def test_no_change_returns_zero(self):
        result = calculate_improvement_pct(baseline_kg=150, current_kg=150)
        assert result == 0.0

    def test_result_clamped_between_0_and_100(self):
        for baseline, current in [(100, 200), (100, 0), (100, 100), (50, 10)]:
            r = calculate_improvement_pct(baseline, current)
            assert 0.0 <= r <= 100.0


# ── Rank score ────────────────────────────────────────────────────────────────

class TestCalculateRankScore:
    def test_formula_correct(self):
        """rank_score = improvement_pct × 0.6 + normalized_pts × 0.4"""
        result = calculate_rank_score(
            improvement_pct=50.0,
            user_total_points=100,
            max_points_in_cohort=200,
        )
        # improvement: 50 × 0.6 = 30; normalized: (100/200)×100 × 0.4 = 20
        assert abs(result - 50.0) < 0.01

    def test_zero_max_points_no_crash(self):
        """Single-user cohort where max_points=0."""
        result = calculate_rank_score(50.0, 0, 0)
        assert result == 50.0 * 0.6  # improvement component only

    def test_higher_improvement_wins(self):
        score_a = calculate_rank_score(80.0, 50, 100)
        score_b = calculate_rank_score(20.0, 90, 100)
        assert score_a > score_b  # improvement weighted more heavily

    def test_score_is_non_negative(self):
        for imp, pts, max_pts in [(0,0,100), (100,100,100), (50,50,50)]:
            assert calculate_rank_score(imp, pts, max_pts) >= 0.0


# ── Rank tiers ────────────────────────────────────────────────────────────────

class TestDetermineRankTier:
    from app.models import RankTier

    def test_zero_points_seedling(self):
        from app.models import RankTier
        assert determine_rank_tier(0) == RankTier.SEEDLING

    def test_50_points_seedling(self):
        from app.models import RankTier
        assert determine_rank_tier(50) == RankTier.SEEDLING

    def test_51_points_eco_explorer(self):
        from app.models import RankTier
        assert determine_rank_tier(51) == RankTier.ECO_EXPLORER

    def test_151_points_climate_champion(self):
        from app.models import RankTier
        assert determine_rank_tier(151) == RankTier.CLIMATE_CHAMPION

    def test_300_points_planet_protector(self):
        from app.models import RankTier
        assert determine_rank_tier(300) == RankTier.PLANET_PROTECTOR

    def test_large_points_planet_protector(self):
        from app.models import RankTier
        assert determine_rank_tier(9999) == RankTier.PLANET_PROTECTOR


# ── Build individual leaderboard ──────────────────────────────────────────────

def _make_user(uid, baseline, current, points, actions):
    return {
        "user_id":                  uid,
        "display_name":             uid,
        "avatar_emoji":             "🌱",
        "city":                     "Mumbai",
        "baseline_kg":              baseline,
        "current_monthly_kg":       current,
        "total_points":             points,
        "completed_challenges_count": actions,
        "total_co2_saved_kg":       5.0,
    }


class TestBuildIndividualLeaderboard:
    def test_empty_users_returns_empty(self):
        result = build_individual_leaderboard([], requesting_user_id=None)
        assert result.entries == []
        assert result.total_eligible_users == 0

    def test_users_without_baselines_excluded(self):
        users = [
            _make_user("u1", None, 100, 200, 5),   # no baseline — excluded
            _make_user("u2", 200, 100, 150, 5),    # eligible
        ]
        result = build_individual_leaderboard(users)
        ids = [e.user_id for e in result.entries]
        assert "u1" not in ids
        assert "u2" in ids
        assert result.total_eligible_users == 1

    def test_users_with_too_few_actions_excluded(self):
        users = [
            _make_user("u1", 200, 100, 200, 2),   # only 2 actions — excluded
            _make_user("u2", 200, 100, 150, 3),   # exactly 3 — eligible
        ]
        result = build_individual_leaderboard(users)
        ids = [e.user_id for e in result.entries]
        assert "u1" not in ids
        assert "u2" in ids

    def test_improvement_based_scoring(self):
        """Higher improver should rank above high-baseline user."""
        users = [
            _make_user("improver", 200, 80,  100, 5),  # 60% improvement
            _make_user("highbase", 200, 180, 500, 5),  # 10% improvement but more points
        ]
        result = build_individual_leaderboard(users)
        assert result.entries[0].user_id == "improver"

    def test_tie_breaking_by_points(self):
        """Equal improvement → higher points wins."""
        users = [
            _make_user("low_pts",  200, 100, 50,  5),
            _make_user("high_pts", 200, 100, 200, 5),
        ]
        result = build_individual_leaderboard(users)
        assert result.entries[0].user_id == "high_pts"

    def test_current_user_is_marked(self):
        users = [
            _make_user("u1", 200, 100, 100, 5),
            _make_user("u2", 200, 120, 80,  5),
        ]
        result = build_individual_leaderboard(users, requesting_user_id="u2")
        current = [e for e in result.entries if e.is_current_user]
        assert len(current) == 1
        assert current[0].user_id == "u2"

    def test_single_user_cohort_no_crash(self):
        """max_points=0 case should not raise."""
        users = [_make_user("solo", 200, 100, 0, 5)]
        result = build_individual_leaderboard(users)
        assert len(result.entries) == 1

    def test_top_n_limit(self):
        users = [_make_user(f"u{i}", 200, 100, 100, 5) for i in range(60)]
        result = build_individual_leaderboard(users, top_n=50)
        assert len([e for e in result.entries if not e.is_current_user]) <= 50
