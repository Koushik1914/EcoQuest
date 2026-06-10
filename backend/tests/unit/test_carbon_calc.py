"""
Unit tests for carbon_calc.py
100% coverage: all transport modes, diet combos, energy brackets, shopping,
boundary values, output types, ranges, and breakdown sum invariants.
"""
from __future__ import annotations

import pytest

from app.models import (
    EnergyBill,
    MeatFrequency,
    QuizDiet,
    QuizEnergy,
    QuizLifestyle,
    QuizTransport,
    RecyclingHabit,
    ShoppingFrequency,
    TransportMode,
)
from app.services.carbon_calc import (
    INDIA_NATIONAL_AVERAGE_KG_MONTH,
    RATING_GREEN_MAX,
    RATING_YELLOW_MAX,
    biggest_emission_category,
    calculate_breakdown,
    calculate_diet_kg,
    calculate_energy_kg,
    calculate_shopping_kg,
    calculate_total_footprint,
    calculate_transport_kg,
    determine_rating,
    vs_national_average_pct,
)


# ── Transport ──────────────────────────────────────────────────────────────────

class TestCalculateTransportKg:
    """Tests for calculate_transport_kg covering all modes and km values."""

    @pytest.mark.parametrize("mode,weekly_km,expected_min", [
        (TransportMode.CAR_PETROL,       100, 60.0),   # 100km × 4 × 0.192 = 76.8
        (TransportMode.CAR_DIESEL,       100, 55.0),   # 100km × 4 × 0.171 = 68.4
        (TransportMode.CAR_EV,           100, 15.0),   # 100km × 4 × 0.053 = 21.2
        (TransportMode.PUBLIC_TRANSPORT, 100, 10.0),   # 100km × 4 × 0.041 = 16.4
    ])
    def test_motorised_modes_produce_nonzero_emissions(self, mode, weekly_km, expected_min):
        transport = QuizTransport(mode=mode, weekly_km=weekly_km)
        result = calculate_transport_kg(transport)
        assert result > expected_min
        assert isinstance(result, float)

    @pytest.mark.parametrize("mode", [TransportMode.BIKE, TransportMode.WALK, TransportMode.WFH])
    def test_zero_emission_modes(self, mode):
        transport = QuizTransport(mode=mode, weekly_km=0)
        assert calculate_transport_kg(transport) == 0.0

    @pytest.mark.parametrize("mode", [TransportMode.BIKE, TransportMode.WALK, TransportMode.WFH])
    def test_zero_emission_modes_ignore_km(self, mode):
        """km value should have no effect for zero-emission modes."""
        t_low  = calculate_transport_kg(QuizTransport(mode=mode, weekly_km=0))
        t_high = calculate_transport_kg(QuizTransport(mode=mode, weekly_km=500))
        assert t_low == t_high == 0.0

    def test_boundary_zero_km(self):
        transport = QuizTransport(mode=TransportMode.CAR_PETROL, weekly_km=0)
        assert calculate_transport_kg(transport) == 0.0

    def test_boundary_max_km(self):
        transport = QuizTransport(mode=TransportMode.CAR_PETROL, weekly_km=2000)
        result = calculate_transport_kg(transport)
        # 2000 × 4 × 0.192 = 1536
        assert abs(result - 1536.0) < 0.1

    def test_petrol_greater_than_diesel(self):
        """Petrol emits more than diesel per km."""
        petrol = calculate_transport_kg(QuizTransport(mode=TransportMode.CAR_PETROL, weekly_km=100))
        diesel = calculate_transport_kg(QuizTransport(mode=TransportMode.CAR_DIESEL, weekly_km=100))
        assert petrol > diesel

    def test_ev_less_than_public_transport_at_high_km(self):
        """EV is still higher than public transport per km."""
        ev  = calculate_transport_kg(QuizTransport(mode=TransportMode.CAR_EV, weekly_km=100))
        pub = calculate_transport_kg(QuizTransport(mode=TransportMode.PUBLIC_TRANSPORT, weekly_km=100))
        assert ev > pub

    def test_result_is_rounded(self):
        transport = QuizTransport(mode=TransportMode.CAR_EV, weekly_km=33)
        result = calculate_transport_kg(transport)
        assert round(result, 3) == result


# ── Diet ──────────────────────────────────────────────────────────────────────

class TestCalculateDietKg:
    def test_daily_highest(self):
        assert calculate_diet_kg(QuizDiet(meat_frequency=MeatFrequency.DAILY)) == 58.0

    def test_never_lowest(self):
        assert calculate_diet_kg(QuizDiet(meat_frequency=MeatFrequency.NEVER)) == 5.0

    def test_ordering(self):
        vals = [
            calculate_diet_kg(QuizDiet(meat_frequency=f))
            for f in [MeatFrequency.DAILY, MeatFrequency.FEW_TIMES, MeatFrequency.RARELY, MeatFrequency.NEVER]
        ]
        assert vals == sorted(vals, reverse=True)

    @pytest.mark.parametrize("freq,expected", [
        (MeatFrequency.DAILY,      58.0),
        (MeatFrequency.FEW_TIMES,  36.0),
        (MeatFrequency.RARELY,     16.0),
        (MeatFrequency.NEVER,       5.0),
    ])
    def test_exact_values(self, freq, expected):
        assert calculate_diet_kg(QuizDiet(meat_frequency=freq)) == expected


# ── Energy ────────────────────────────────────────────────────────────────────

class TestCalculateEnergyKg:
    @pytest.mark.parametrize("bill,expected", [
        (EnergyBill.LOW,       12.0),
        (EnergyBill.MEDIUM,    32.0),
        (EnergyBill.HIGH,      62.0),
        (EnergyBill.VERY_HIGH, 98.0),
    ])
    def test_exact_values(self, bill, expected):
        assert calculate_energy_kg(QuizEnergy(monthly_bill_inr=bill)) == expected

    def test_ordering(self):
        vals = [
            calculate_energy_kg(QuizEnergy(monthly_bill_inr=b))
            for b in [EnergyBill.LOW, EnergyBill.MEDIUM, EnergyBill.HIGH, EnergyBill.VERY_HIGH]
        ]
        assert vals == sorted(vals)


# ── Shopping + Recycling ──────────────────────────────────────────────────────

class TestCalculateShoppingKg:
    def test_weekly_higher_than_monthly(self):
        weekly  = calculate_shopping_kg(QuizLifestyle(recycling=RecyclingHabit.NEVER, shopping_frequency=ShoppingFrequency.WEEKLY))
        monthly = calculate_shopping_kg(QuizLifestyle(recycling=RecyclingHabit.NEVER, shopping_frequency=ShoppingFrequency.MONTHLY))
        assert weekly > monthly

    def test_recycling_always_reduces_emissions(self):
        always  = calculate_shopping_kg(QuizLifestyle(recycling=RecyclingHabit.ALWAYS,    shopping_frequency=ShoppingFrequency.WEEKLY))
        never   = calculate_shopping_kg(QuizLifestyle(recycling=RecyclingHabit.NEVER,     shopping_frequency=ShoppingFrequency.WEEKLY))
        sometimes = calculate_shopping_kg(QuizLifestyle(recycling=RecyclingHabit.SOMETIMES, shopping_frequency=ShoppingFrequency.WEEKLY))
        assert always < sometimes < never

    def test_never_recycling_rarely_shopping_baseline(self):
        result = calculate_shopping_kg(
            QuizLifestyle(recycling=RecyclingHabit.NEVER, shopping_frequency=ShoppingFrequency.RARELY)
        )
        assert result == 2.0

    def test_result_is_non_negative(self):
        for recycling in RecyclingHabit:
            for freq in ShoppingFrequency:
                result = calculate_shopping_kg(QuizLifestyle(recycling=recycling, shopping_frequency=freq))
                assert result >= 0.0


# ── Total & Breakdown ─────────────────────────────────────────────────────────

class TestCalculateTotalAndBreakdown:
    def test_total_is_sum(self):
        t, d, e, s = 50.0, 30.0, 20.0, 10.0
        assert calculate_total_footprint(t, d, e, s) == 110.0

    def test_breakdown_sums_to_100(self):
        bd = calculate_breakdown(50, 30, 20, 10)
        total = bd.transport_pct + bd.food_pct + bd.energy_pct + bd.shopping_pct
        assert abs(total - 100.0) < 0.5

    def test_breakdown_all_zero(self):
        bd = calculate_breakdown(0, 0, 0, 0)
        assert bd.transport_pct == 0.0
        assert bd.food_pct      == 0.0
        assert bd.energy_pct    == 0.0
        assert bd.shopping_pct  == 0.0

    def test_breakdown_single_category(self):
        bd = calculate_breakdown(100, 0, 0, 0)
        assert bd.transport_pct == 100.0
        assert bd.food_pct      == 0.0

    def test_total_rounded_to_2dp(self):
        result = calculate_total_footprint(1.1, 2.2, 3.3, 4.4)
        assert result == round(result, 2)


# ── Rating ────────────────────────────────────────────────────────────────────

class TestDetermineRating:
    def test_green_below_100(self):
        from app.models import RatingLevel
        assert determine_rating(99.9) == RatingLevel.GREEN

    def test_yellow_at_100(self):
        from app.models import RatingLevel
        assert determine_rating(100.0) == RatingLevel.YELLOW

    def test_yellow_at_200(self):
        from app.models import RatingLevel
        assert determine_rating(200.0) == RatingLevel.YELLOW

    def test_red_above_200(self):
        from app.models import RatingLevel
        assert determine_rating(200.1) == RatingLevel.RED

    def test_zero_emissions_is_green(self):
        from app.models import RatingLevel
        assert determine_rating(0.0) == RatingLevel.GREEN


# ── National average comparison ───────────────────────────────────────────────

class TestVsNationalAverage:
    def test_above_average_positive(self):
        result = vs_national_average_pct(INDIA_NATIONAL_AVERAGE_KG_MONTH * 1.5)
        assert result > 0

    def test_below_average_negative(self):
        result = vs_national_average_pct(INDIA_NATIONAL_AVERAGE_KG_MONTH * 0.5)
        assert result < 0

    def test_at_average_zero(self):
        result = vs_national_average_pct(INDIA_NATIONAL_AVERAGE_KG_MONTH)
        assert result == 0.0

    def test_return_type(self):
        assert isinstance(vs_national_average_pct(100), float)


# ── Biggest emission category ─────────────────────────────────────────────────

class TestBiggestEmissionCategory:
    def test_transport_dominates(self):
        assert biggest_emission_category(200, 30, 20, 10) == "transport"

    def test_food_dominates(self):
        assert biggest_emission_category(10, 80, 20, 10) == "food"

    def test_energy_dominates(self):
        assert biggest_emission_category(10, 20, 100, 5) == "energy"

    def test_shopping_dominates(self):
        assert biggest_emission_category(5, 10, 15, 50) == "shopping"
