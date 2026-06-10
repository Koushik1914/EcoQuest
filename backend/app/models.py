"""
EcoQuest Pydantic v2 Models
All request bodies, response models, and domain entities with strict validation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


# ── Enumerations ─────────────────────────────────────────────────────────────

class TransportMode(str, Enum):
    CAR_PETROL = "car_petrol"
    CAR_DIESEL = "car_diesel"
    CAR_EV = "car_ev"
    PUBLIC_TRANSPORT = "public_transport"
    BIKE = "bike"
    WALK = "walk"
    WFH = "wfh"


class MeatFrequency(str, Enum):
    DAILY = "daily"
    FEW_TIMES = "few_times"
    RARELY = "rarely"
    NEVER = "never"


class EnergyBill(str, Enum):
    LOW = "lt_500"          # < 500 INR
    MEDIUM = "500_1500"     # 500–1500 INR
    HIGH = "1500_3000"      # 1500–3000 INR
    VERY_HIGH = "gt_3000"   # > 3000 INR


class RecyclingHabit(str, Enum):
    ALWAYS = "always"
    SOMETIMES = "sometimes"
    NEVER = "never"


class ShoppingFrequency(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    RARELY = "rarely"


class UserType(str, Enum):
    STUDENT = "student"
    PROFESSIONAL = "professional"
    FAMILY = "family"


class ChallengeCategory(str, Enum):
    TRANSPORT = "transport"
    FOOD = "food"
    ENERGY = "energy"
    SHOPPING = "shopping"
    LIFESTYLE = "lifestyle"


class ChallengeDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ChallengeFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class RatingLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class RankTier(str, Enum):
    SEEDLING = "seedling"
    ECO_EXPLORER = "eco_explorer"
    CLIMATE_CHAMPION = "climate_champion"
    PLANET_PROTECTOR = "planet_protector"


class ClubType(str, Enum):
    COLLEGE = "college"
    OFFICE = "office"
    CITY = "city"


class PostActionType(str, Enum):
    TRANSPORT = "transport"
    FOOD = "food"
    ENERGY = "energy"
    SHOPPING = "shopping"
    LIFESTYLE = "lifestyle"


# ── Quiz / Carbon Calculation Models ──────────────────────────────────────────

class QuizTransport(BaseModel):
    mode: TransportMode
    weekly_km: float = Field(ge=0, le=2000, description="Weekly kilometres travelled")

    @field_validator("weekly_km")
    @classmethod
    def zero_km_for_zero_emission(cls, v: float, info: Any) -> float:
        """Zero km is valid for walk/bike/wfh modes."""
        return round(v, 2)


class QuizDiet(BaseModel):
    meat_frequency: MeatFrequency


class QuizEnergy(BaseModel):
    monthly_bill_inr: EnergyBill


class QuizLifestyle(BaseModel):
    recycling: RecyclingHabit
    shopping_frequency: ShoppingFrequency


class QuizProfile(BaseModel):
    user_type: UserType
    city: str = Field(min_length=2, max_length=100, description="User's city")

    @field_validator("city")
    @classmethod
    def sanitize_city(cls, v: str) -> str:
        return v.strip().title()


class QuizSubmission(BaseModel):
    """Complete quiz submission payload — all 5 steps."""

    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    transport: QuizTransport
    diet: QuizDiet
    energy: QuizEnergy
    lifestyle: QuizLifestyle
    profile: QuizProfile


class FootprintBreakdown(BaseModel):
    transport_pct: float = Field(ge=0, le=100)
    food_pct: float = Field(ge=0, le=100)
    energy_pct: float = Field(ge=0, le=100)
    shopping_pct: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def percentages_sum_to_100(self) -> "FootprintBreakdown":
        total = (
            self.transport_pct
            + self.food_pct
            + self.energy_pct
            + self.shopping_pct
        )
        # Allow minor floating-point drift
        if abs(total - 100.0) > 1.0 and total > 0:
            raise ValueError(f"Breakdown percentages sum to {total:.2f}, expected ~100")
        return self


class QuizResult(BaseModel):
    """Response returned after quiz submission."""

    user_id: str
    total_monthly_kg: float
    breakdown: FootprintBreakdown
    transport_kg: float
    food_kg: float
    energy_kg: float
    shopping_kg: float
    vs_national_avg_pct: float  # positive = above average, negative = below
    rating: RatingLevel
    is_baseline: bool  # True if this is the first submission
    calculated_at: datetime


# ── User Profile ──────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: str
    display_name: str
    avatar_emoji: str = "🌱"
    city: str
    user_type: UserType
    baseline_kg: Optional[float] = None
    current_monthly_kg: Optional[float] = None
    biggest_emission_category: Optional[str] = None
    total_points: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    rank_tier: RankTier = RankTier.SEEDLING
    completed_challenges_count: int = 0
    total_co2_saved_kg: float = 0.0
    club_id: Optional[str] = None
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_challenge_completed_at: Optional[datetime] = None


# ── Challenges ────────────────────────────────────────────────────────────────

class Challenge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=500)
    category: ChallengeCategory
    difficulty: ChallengeDifficulty
    points: int = Field(gt=0)
    co2_savings_kg: float = Field(gt=0)
    frequency: ChallengeFrequency
    active_from: datetime
    active_until: datetime
    is_active: bool = True


class ChallengeCompletionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    note: Optional[str] = Field(default=None, max_length=300)


class ChallengeCompletionResponse(BaseModel):
    challenge_id: str
    user_id: str
    points_awarded: int
    streak_bonus: int
    new_total_points: int
    new_streak: int
    milestone_reached: bool
    co2_saved_kg: float
    completed_at: datetime


class UserChallenge(BaseModel):
    user_id: str
    challenge_id: str
    completed_at: datetime
    points_earned: int
    co2_saved_kg: float
    streak_at_completion: int


# ── Leaderboard ───────────────────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    display_name: str
    avatar_emoji: str
    city: str
    rank_tier: RankTier
    improvement_pct: float
    total_points: int
    rank_score: float
    total_co2_saved_kg: float
    is_current_user: bool = False


class ClubLeaderboardEntry(BaseModel):
    rank: int
    club_id: str
    name: str
    club_type: ClubType
    member_count: int
    total_co2_saved: float
    total_action_points: int
    score: float


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    current_user_rank: Optional[int] = None
    total_eligible_users: int
    generated_at: datetime


class ClubLeaderboardResponse(BaseModel):
    entries: list[ClubLeaderboardEntry]
    total_clubs: int
    generated_at: datetime


# ── Chat / AI ─────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)


class ChatHistoryResponse(BaseModel):
    user_id: str
    messages: list[ChatMessage]
    total_messages: int


# ── Community Posts ───────────────────────────────────────────────────────────

class CreatePostRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    avatar_emoji: str = Field(default="🌱", max_length=8)
    city: str = Field(min_length=2, max_length=100)
    action_type: PostActionType
    note: str = Field(min_length=5, max_length=500)
    club_tag: Optional[str] = Field(default=None, max_length=60)
    image_object_path: Optional[str] = Field(
        default=None,
        max_length=512,
        description="GCS object path (not full URL) set after client upload",
    )

    @field_validator("note")
    @classmethod
    def sanitize_note(cls, v: str) -> str:
        return v.strip()


class Post(BaseModel):
    id: str
    user_id: str
    display_name: str
    avatar_emoji: str
    city: str
    action_type: PostActionType
    note: str
    co2_saved_kg: float
    image_url: Optional[str] = None
    likes: list[str] = Field(default_factory=list)  # set of user_ids
    likes_count: int = 0
    club_tag: Optional[str] = None
    created_at: datetime
    verified: bool = False


class PostListResponse(BaseModel):
    posts: list[Post]
    next_cursor: Optional[str] = None
    has_more: bool


class LikeResponse(BaseModel):
    post_id: str
    liked: bool
    likes_count: int


class SignedUploadUrlRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=5, max_length=100)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed_prefixes = ("image/jpeg", "image/png", "image/webp", "image/gif")
        if not any(v.startswith(p) for p in allowed_prefixes):
            raise ValueError(
                f"Unsupported content_type '{v}'. Must be an image (jpeg, png, webp, gif)."
            )
        return v


class SignedUploadUrlResponse(BaseModel):
    upload_url: str
    object_path: str
    expires_in_seconds: int


# ── Clubs ─────────────────────────────────────────────────────────────────────

class Club(BaseModel):
    id: str
    name: str = Field(min_length=3, max_length=100)
    club_type: ClubType
    description: str = Field(min_length=10, max_length=400)
    member_count: int = 0
    total_co2_saved: float = 0.0
    total_action_points: int = 0
    national_rank: Optional[int] = None
    created_at: datetime


class JoinClubRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class JoinClubResponse(BaseModel):
    club_id: str
    user_id: str
    new_member_count: int
    joined_at: datetime


class ClubListResponse(BaseModel):
    clubs: list[Club]
    total: int


# ── Health Check ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    environment: str


# ── Internal ──────────────────────────────────────────────────────────────────

class InternalRotateRequest(BaseModel):
    """Used by Cloud Scheduler to trigger challenge rotation."""
    auth_token: str = Field(min_length=8, max_length=256)


class ErrorResponse(BaseModel):
    detail: str
    request_id: Optional[str] = None
