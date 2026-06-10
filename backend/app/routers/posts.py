"""
EcoQuest Posts Router
GET  /posts                  — Paginated community feed with optional category filter
POST /posts                  — Create a new community post
POST /posts/{id}/like        — Toggle like on a post (idempotent)
GET  /posts/upload-url       — Request signed GCS upload URL
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from google.cloud import storage

from app.config import get_settings
from app.database import (
    Collections,
    firestore_transaction,
    get_document,
    get_firestore,
    paginated_query,
    set_document,
)
from app.models import (
    CreatePostRequest,
    LikeResponse,
    Post,
    PostActionType,
    PostListResponse,
    SignedUploadUrlRequest,
    SignedUploadUrlResponse,
)
from app.services.carbon_calc import (
    DIET_EMISSION_KG_MONTH,
    SHOPPING_EMISSION_KG_MONTH,
    TRANSPORT_EMISSION_FACTORS,
    MeatFrequency,
    ShoppingFrequency,
    TransportMode,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posts", tags=["posts"])

# ── Action type → estimated CO₂ savings mapping ───────────────────────────────
ACTION_CO2_MAP: dict[PostActionType, float] = {
    PostActionType.TRANSPORT: 2.1,   # No-car day estimate
    PostActionType.FOOD:      1.5,   # Plant-based meal
    PostActionType.ENERGY:    0.8,   # Standby device unplugging
    PostActionType.SHOPPING:  0.4,   # Reusable bag
    PostActionType.LIFESTYLE: 0.5,   # General lifestyle action
}


@router.get(
    "/upload-url",
    response_model=SignedUploadUrlResponse,
    summary="Get signed GCS URL for direct client image upload",
)
async def get_upload_url(
    user_id: str = Query(..., max_length=128),
    filename: str = Query(..., max_length=255),
    content_type: str = Query(..., max_length=100),
) -> SignedUploadUrlResponse:
    # Validate via Pydantic model
    req = SignedUploadUrlRequest(
        user_id=user_id, filename=filename, content_type=content_type
    )
    settings = get_settings()
    safe_name = f"posts/{req.user_id}/{uuid.uuid4().hex}_{req.filename}"

    gcs_client = storage.Client(project=settings.gcp_project_id)
    bucket = gcs_client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(safe_name)

    expiry = timedelta(seconds=settings.gcs_signed_url_expiry_seconds)
    upload_url = blob.generate_signed_url(
        version="v4",
        expiration=expiry,
        method="PUT",
        content_type=req.content_type,
    )

    return SignedUploadUrlResponse(
        upload_url=upload_url,
        object_path=safe_name,
        expires_in_seconds=settings.gcs_signed_url_expiry_seconds,
    )


@router.get(
    "",
    response_model=PostListResponse,
    summary="Paginated community feed with optional category filter",
)
async def list_posts(
    request: Request,
    category: Optional[PostActionType] = Query(default=None),
    cursor: Optional[str] = Query(default=None, max_length=512),
    limit: int = Query(default=20, ge=1, le=50),
) -> PostListResponse:
    filters = []
    if category:
        filters.append(("action_type", "==", category.value))

    # Resolve cursor to Firestore snapshot
    start_after_snap = None
    if cursor:
        db = get_firestore()
        cursor_ref = db.collection(Collections.POSTS).document(cursor)
        cursor_snap = await cursor_ref.get()
        if cursor_snap.exists:
            start_after_snap = cursor_snap

    docs, last_snap = await paginated_query(
        collection=Collections.POSTS,
        filters=filters,
        order_by="created_at",
        descending=True,
        limit=limit + 1,
        start_after=start_after_snap,
    )

    has_more = len(docs) > limit
    docs = docs[:limit]

    posts = []
    settings = get_settings()
    for doc in docs:
        image_url = None
        if doc.get("image_object_path"):
            image_url = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{doc['image_object_path']}"
        likes: list = doc.get("likes", [])
        posts.append(
            Post(
                id=doc["id"],
                user_id=doc.get("user_id", ""),
                display_name=doc.get("display_name", ""),
                avatar_emoji=doc.get("avatar_emoji", "🌱"),
                city=doc.get("city", ""),
                action_type=PostActionType(doc.get("action_type", "lifestyle")),
                note=doc.get("note", ""),
                co2_saved_kg=doc.get("co2_saved_kg", 0.0),
                image_url=image_url,
                likes=likes,
                likes_count=len(likes),
                club_tag=doc.get("club_tag"),
                created_at=doc.get("created_at", datetime.utcnow()),
                verified=doc.get("verified", False),
            )
        )

    next_cursor = docs[-1]["id"] if has_more and docs else None
    return PostListResponse(posts=posts, next_cursor=next_cursor, has_more=has_more)


@router.post(
    "",
    response_model=Post,
    status_code=status.HTTP_201_CREATED,
    summary="Create a community post",
)
async def create_post(payload: CreatePostRequest, request: Request) -> Post:
    settings = get_settings()
    post_id = str(uuid.uuid4())
    now = datetime.utcnow()
    co2_saved = ACTION_CO2_MAP.get(payload.action_type, 0.5)

    image_url = None
    if payload.image_object_path:
        image_url = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{payload.image_object_path}"

    doc = {
        "user_id": payload.user_id,
        "display_name": payload.display_name,
        "avatar_emoji": payload.avatar_emoji,
        "city": payload.city,
        "action_type": payload.action_type.value,
        "note": payload.note,
        "co2_saved_kg": co2_saved,
        "image_object_path": payload.image_object_path or "",
        "likes": [],
        "club_tag": payload.club_tag or "",
        "created_at": now,
        "verified": False,
    }

    await set_document(Collections.POSTS, post_id, doc)
    logger.info("Post created: id=%s user=%s", post_id, payload.user_id)

    return Post(
        id=post_id,
        user_id=payload.user_id,
        display_name=payload.display_name,
        avatar_emoji=payload.avatar_emoji,
        city=payload.city,
        action_type=payload.action_type,
        note=payload.note,
        co2_saved_kg=co2_saved,
        image_url=image_url,
        likes=[],
        likes_count=0,
        club_tag=payload.club_tag,
        created_at=now,
        verified=False,
    )


@router.post(
    "/{post_id}/like",
    response_model=LikeResponse,
    summary="Toggle like on a post (idempotent)",
)
async def toggle_like(
    post_id: str,
    user_id: str = Query(..., max_length=128),
    request: Request = None,
) -> LikeResponse:
    if len(post_id) > 128:
        raise HTTPException(status_code=400, detail="post_id too long.")

    db = get_firestore()
    post_ref = db.collection(Collections.POSTS).document(post_id)

    @db.transaction  # type: ignore[arg-type]
    async def _toggle(transaction, ref):  # type: ignore[no-untyped-def]
        snap = await ref.get(transaction=transaction)
        if not snap.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found."
            )
        data = snap.to_dict()
        likes: list = data.get("likes", [])
        liked = user_id in likes
        if liked:
            likes = [uid for uid in likes if uid != user_id]
        else:
            likes.append(user_id)
        transaction.update(ref, {"likes": likes})
        return likes, not liked

    likes, now_liked = await _toggle(post_ref)
    return LikeResponse(post_id=post_id, liked=now_liked, likes_count=len(likes))
