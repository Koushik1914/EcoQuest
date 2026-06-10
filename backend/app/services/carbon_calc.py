"""
EcoQuest Carbon Calculation Service
Pure functions using IPCC AR6 + India MoEFCC emission factors.
All functions are side-effect free and fully typed.
"""
from __future__ import annotations

from app.models import (
    EnergyBill,
    FootprintBreakdown,
    MeatFrequency,
    QuizDiet,
    QuizEnergy,
    QuizLifestyle,
    QuizProfile,
    QuizTransport,
    RatingLevel,
    ShoppingFrequency,
    TransportMode,
)

# ── Emission Factor Constants (IPCC AR6 WG III + India MoEFCC NIR) ────────────
# Units: kg CO₂e per km (transport), kg CO₂e per month (diet/energy/shopping)

TRANSPORT_EMISSION_FACTORS: dict[TransportMode, float] = {
    TransportMode.CAR_PETROL:       0.192,   # kg CO₂/km — IPCC AR6 Table 10.SM.7
    TransportMode.CAR_DIESEL:       0.171,   # kg CO₂/km — IPCC AR6 Table 10.SM.7
    TransportMode.CAR_EV:           0.053,   # kg CO₂/km — India grid intensity 0.708 kgCO₂/kWh × 0.075kWh/km
    TransportMode.PUBLIC_TRANSPORT: 0.041,   # kg CO₂/km — MoEFCC NIR 2020 (bus average)
    TransportMode.BIKE:             0.0,
    TransportMode.WALK:             0.0,
    TransportMode.WFH:              0.0,
}

DIET_EMISSION_KG_MONTH: dict[MeatFrequency, float] = {
    MeatFrequency.DAILY:      58.0,   # kg CO₂e/month — IPCC AR6 Ch.7 high meat
    MeatFrequency.FEW_TIMES:  36.0,   # kg CO₂e/month — moderate meat
    MeatFrequency.RARELY:     16.0,   # kg CO₂e/month — low meat
    MeatFrequency.NEVER:       5.0,   # kg CO₂e/month — vegan/vegetarian baseline
}

ENERGY_EMISSION_KG_MONTH: dict[EnergyBill, float] = {
    EnergyBill.LOW:       12.0,   # < ₹500  — ~200 kWh @ India grid
    EnergyBill.MEDIUM:    32.0,   # ₹500–1500
    EnergyBill.HIGH:      62.0,   # ₹1500–3000
    EnergyBill.VERY_HIGH: 98.0,   # > ₹3000
}

SHOPPING_EMISSION_KG_MONTH: dict[ShoppingFrequency, float] = {
    ShoppingFrequency.WEEKLY:  22.0,   # kg CO₂e/month — fast fashion + goods
    ShoppingFrequency.MONTHLY:  9.0,
    ShoppingFrequency.RARELY:   2.0,
}

INDIA_NATIONAL_AVERAGE_KG_MONTH: float = 158.0  # MoEFCC NIR 2023 average per capita


# ── Rating thresholds ─────────────────────────────────────────────────────────
RATING_GREEN_MAX: float = 100.0
RATING_YELLOW_MAX: float = 200.0


def calculate_transport_kg(transport: QuizTransport) -> float:
    """
    Calculate monthly transport CO₂ (kg) from weekly distance and mode.

    Formula: weekly_km × 4 weeks × emission_factor_per_km
    Zero-emission modes (bike, walk, wfh) always return 0.0.
    """
    factor = TRANSPORT_EMISSION_FACTORS[transport.mode]
    monthly_km = transport.weekly_km * 4.0
    return round(monthly_km * factor, 3)


def calculate_diet_kg(diet: QuizDiet) -> float:
    """
    Return monthly food-related CO₂ (kg) from meat frequency.
    Source: IPCC AR6 Chapter 7 food system emissions.
    """
    return DIET_EMISSION_KG_MONTH[diet.meat_frequency]


def calculate_energy_kg(energy: QuizEnergy) -> float:
    """
    Return monthly home-energy CO₂ (kg) from electricity bill bracket.
    Based on India grid emission intensity (0.708 kgCO₂/kWh, MoEFCC 2023).
    """
    return ENERGY_EMISSION_KG_MONTH[energy.monthly_bill_inr]


def calculate_shopping_kg(lifestyle: QuizLifestyle) -> float:
    """
    Return monthly shopping / lifestyle CO₂ (kg).
    Recycling habit is accounted for as a percentage offset.
    """
    base = SHOPPING_EMISSION_KG_MONTH[lifestyle.shopping_frequency]
    recycling_offsets = {
        "always":    0.15,   # 15% reduction
        "sometimes": 0.07,
        "never":     0.0,
    }
    offset_pct = recycling_offsets.get(lifestyle.recycling.value, 0.0)
    return round(base * (1.0 - offset_pct), 3)


def calculate_total_footprint(
    transport_kg: float,
    diet_kg: float,
    energy_kg: float,
    shopping_kg: float,
) -> float:
    """Sum all category emissions and round to 2 decimal places."""
    return round(transport_kg + diet_kg + energy_kg + shopping_kg, 2)


def calculate_breakdown(
    transport_kg: float,
    diet_kg: float,
    energy_kg: float,
    shopping_kg: float,
) -> FootprintBreakdown:
    """
    Return percentage breakdown of each category.
    If total is 0 (fully zero-emission lifestyle), all percentages are 0.
    """
    total = transport_kg + diet_kg + energy_kg + shopping_kg

    if total == 0.0:
        return FootprintBreakdown(
            transport_pct=0.0,
            food_pct=0.0,
            energy_pct=0.0,
            shopping_pct=0.0,
        )

    def pct(value: float) -> float:
        return round((value / total) * 100.0, 1)

    transport_p = pct(transport_kg)
    food_p = pct(diet_kg)
    energy_p = pct(energy_kg)
    # Assign remainder to shopping to avoid floating-point drift summing to 99.9
    shopping_p = round(100.0 - transport_p - food_p - energy_p, 1)

    return FootprintBreakdown(
        transport_pct=transport_p,
        food_pct=food_p,
        energy_pct=energy_p,
        shopping_pct=shopping_p,
    )


def determine_rating(total_monthly_kg: float) -> RatingLevel:
    """
    Assign a rating tier based on monthly CO₂.
      Green  → < 100 kg/month
      Yellow → 100–200 kg/month
      Red    → > 200 kg/month
    """
    if total_monthly_kg < RATING_GREEN_MAX:
        return RatingLevel.GREEN
    if total_monthly_kg <= RATING_YELLOW_MAX:
        return RatingLevel.YELLOW
    return RatingLevel.RED


def vs_national_average_pct(total_monthly_kg: float) -> float:
    """
    Return the signed percentage difference from India's national average.
    Positive = higher than average. Negative = lower (better).
    """
    return round(
        ((total_monthly_kg - INDIA_NATIONAL_AVERAGE_KG_MONTH)
         / INDIA_NATIONAL_AVERAGE_KG_MONTH)
        * 100.0,
        1,
    )


def biggest_emission_category(
    transport_kg: float,
    diet_kg: float,
    energy_kg: float,
    shopping_kg: float,
) -> str:
    """
    Return the name of the category with the highest monthly emissions.
    Used for AI context injection and personalized recommendations.
    """
    categories = {
        "transport": transport_kg,
        "food":      diet_kg,
        "energy":    energy_kg,
        "shopping":  shopping_kg,
    }
    return max(categories, key=lambda k: categories[k])


def personalized_recommendations(
    transport_kg: float,
    diet_kg: float,
    energy_kg: float,
    shopping_kg: float,
    transport_mode: TransportMode,
) -> list[str]:
    """
    Return 3 specific, quantified recommendation strings based on the
    user's emission profile.  Recommendations target the top 2 categories.
    """
    categories = {
        "transport": transport_kg,
        "food":      diet_kg,
        "energy":    energy_kg,
        "shopping":  shopping_kg,
    }
    sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    top_cat = sorted_cats[0][0]
    recs: list[str] = []

    # Transport recommendations
    if top_cat == "transport":
        if transport_mode in (TransportMode.CAR_PETROL, TransportMode.CAR_DIESEL):
            saving = round(transport_kg * 0.21, 1)  # 2×/week public transit switch
            recs.append(
                f"🚌 Take public transport twice a week to save ~{saving} kg CO₂/month."
            )
            saving_carpool = round(transport_kg * 0.12, 1)
            recs.append(
                f"🚗 Carpool for your existing commute to cut ~{saving_carpool} kg CO₂/month."
            )
            recs.append(
                "🛒 Consolidate errands into one trip per week to reduce short journeys."
            )
        elif transport_mode == TransportMode.CAR_EV:
            recs.append(
                "⚡ Charge your EV during off-peak hours (10 PM–6 AM) using greener grid mix."
            )
            recs.append(
                "🚲 Cycle for trips under 5 km — saves both electricity and wear."
            )
            recs.append(
                "🌱 Your EV already saves vs petrol; consider solar panels to go net-zero."
            )
        else:
            recs.append(
                "🚶 Great job using low-carbon transport! Encourage a friend to switch too."
            )
            recs.append("🚲 Consider cycling for short errands to stay at near-zero transport emissions.")
            recs.append("🌱 Join an Eco Club to multiply your community impact.")

    # Food recommendations
    elif top_cat == "food":
        saving = round(diet_kg * 0.38, 1)
        recs.append(
            f"🥗 One plant-based day per week saves ~{saving} kg CO₂/month."
        )
        saving2 = round(diet_kg * 0.17, 1)
        recs.append(
            f"🌾 Replace red meat with chicken/fish twice a week → ~{saving2} kg CO₂/month saved."
        )
        recs.append(
            "🛒 Buy seasonal, local produce to cut food-mile emissions by up to 10%."
        )

    # Energy recommendations
    elif top_cat == "energy":
        saving = round(energy_kg * 0.20, 1)
        recs.append(
            f"🔌 Unplug all standby devices at night — saves ~{saving} kg CO₂/month."
        )
        saving2 = round(energy_kg * 0.18, 1)
        recs.append(
            f"🌡️ Set AC to 24°C instead of 18°C — saves ~{saving2} kg CO₂/month."
        )
        recs.append(
            "💡 Switch remaining incandescent bulbs to LED — 75% less energy per bulb."
        )

    # Shopping recommendations
    elif top_cat == "shopping":
        saving = round(shopping_kg * 0.45, 1)
        recs.append(
            f"🛍️ Switch to bulk monthly shopping — saves ~{saving} kg CO₂/month in packaging."
        )
        recs.append(
            "♻️ Buy second-hand for 1 clothing item per month — 80% lower carbon per item."
        )
        recs.append(
            "🌿 Choose brands with verified carbon labelling for high-frequency purchases."
        )

    return recs[:3]
