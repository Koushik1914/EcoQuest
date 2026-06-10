"""
Unit tests for challenge_engine.py
Streak logic, milestone detection, duplicate prevention, point calculation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.challenge_engine import (
    STREAK_BONUS_POINTS,
    STREAK_MILESTONE,
    calculate_new_streak,
    calculate_points_for_completion,
    is_duplicate_completion,
    is_milestone_reached,
    is_streak_reset,
    should_update_streak,
)


# ── Streak logic ──────────────────────────────────────────────────────────────

class TestStreakLogic:
    def test_first_completion_starts_streak(self):
        new_streak = calculate_new_streak(current_streak=0, last_completed_at=None)
        assert new_streak == 1

    def test_completion_within_48h_increments(self):
        last = datetime.utcnow() - timedelta(hours=24)
        new_streak = calculate_new_streak(current_streak=3, last_completed_at=last)
        assert new_streak == 4

    def test_completion_after_48h_resets_to_1(self):
        last = datetime.utcnow() - timedelta(hours=49)
        new_streak = calculate_new_streak(current_streak=5, last_completed_at=last)
        assert new_streak == 1

    def test_completion_exactly_at_48h_boundary(self):
        """Exactly at 48h should be treated as reset (gap > 48h condition)."""
        last = datetime.utcnow() - timedelta(hours=48, seconds=1)
        new_streak = calculate_new_streak(current_streak=3, last_completed_at=last)
        assert new_streak == 1

    def test_streak_never_goes_negative(self):
        last = datetime.utcnow() - timedelta(hours=100)
        new_streak = calculate_new_streak(current_streak=10, last_completed_at=last)
        assert new_streak >= 1

    def test_should_update_streak_true_for_none(self):
        assert should_update_streak(None) is True

    def test_should_update_streak_true_within_window(self):
        last = datetime.utcnow() - timedelta(hours=12)
        assert should_update_streak(last) is True

    def test_should_update_streak_false_outside_window(self):
        last = datetime.utcnow() - timedelta(hours=50)
        assert should_update_streak(last) is False

    def test_is_streak_reset_true_beyond_window(self):
        last = datetime.utcnow() - timedelta(hours=50)
        assert is_streak_reset(last) is True

    def test_is_streak_reset_false_within_window(self):
        last = datetime.utcnow() - timedelta(hours=20)
        assert is_streak_reset(last) is False

    def test_is_streak_reset_false_for_none(self):
        assert is_streak_reset(None) is False


# ── Milestone detection ───────────────────────────────────────────────────────

class TestMilestoneDetection:
    def test_7_day_milestone(self):
        assert is_milestone_reached(7) is True

    def test_14_day_milestone(self):
        assert is_milestone_reached(14) is True

    def test_non_milestone_streaks(self):
        for streak in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13]:
            assert is_milestone_reached(streak) is False

    def test_zero_streak_not_milestone(self):
        assert is_milestone_reached(0) is False


# ── Duplicate completion ──────────────────────────────────────────────────────

class TestDuplicateCompletion:
    def test_no_previous_completions_not_duplicate(self):
        assert is_duplicate_completion([], "daily") is False

    def test_same_day_daily_is_duplicate(self):
        today = datetime.utcnow().replace(hour=8, minute=0, second=0)
        assert is_duplicate_completion([today], "daily") is True

    def test_yesterday_daily_not_duplicate(self):
        yesterday = datetime.utcnow() - timedelta(days=1)
        assert is_duplicate_completion([yesterday], "daily") is False

    def test_same_iso_week_weekly_is_duplicate(self):
        this_week = datetime.utcnow()
        assert is_duplicate_completion([this_week], "weekly") is True

    def test_last_week_weekly_not_duplicate(self):
        last_week = datetime.utcnow() - timedelta(days=8)
        assert is_duplicate_completion([last_week], "weekly") is False

    def test_multiple_old_completions_not_duplicate(self):
        old = [datetime.utcnow() - timedelta(days=d) for d in [30, 60, 90]]
        assert is_duplicate_completion(old, "daily") is False

    def test_mixed_old_and_today_is_duplicate(self):
        today   = datetime.utcnow()
        old     = datetime.utcnow() - timedelta(days=30)
        assert is_duplicate_completion([old, today], "daily") is True


# ── Points calculation ────────────────────────────────────────────────────────

class TestPointsCalculation:
    def test_easy_challenge_no_bonus(self):
        challenge = {"points": 10, "difficulty": "easy"}
        base, bonus = calculate_points_for_completion(challenge)
        assert base  == 10
        assert bonus == 0

    def test_medium_challenge_no_bonus(self):
        challenge = {"points": 15, "difficulty": "medium"}
        base, bonus = calculate_points_for_completion(challenge)
        assert base  == 15
        assert bonus == 0

    def test_hard_challenge_receives_bonus(self):
        challenge = {"points": 30, "difficulty": "hard"}
        base, bonus = calculate_points_for_completion(challenge)
        assert base  == 30
        assert bonus == 5

    def test_total_points_correct(self):
        challenge = {"points": 35, "difficulty": "hard"}
        base, bonus = calculate_points_for_completion(challenge)
        assert base + bonus == 40

    def test_streak_bonus_constant(self):
        assert STREAK_BONUS_POINTS == 25

    def test_streak_milestone_constant(self):
        assert STREAK_MILESTONE == 7
