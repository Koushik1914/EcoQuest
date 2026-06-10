"""
EcoQuest Database Module
Async Firestore client with collection helpers, batch writers, and transactions.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from google.cloud.firestore_v1 import AsyncClient, AsyncTransaction
from google.cloud.firestore_v1.async_batch import AsyncWriteBatch
from google.cloud.firestore_v1.base_query import BaseQuery

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Singleton async Firestore client ─────────────────────────────────────────
_firestore_client: Optional[AsyncClient] = None


def get_firestore() -> AsyncClient:
    """Return the singleton AsyncClient, raising if not initialised."""
    if _firestore_client is None:
        raise RuntimeError(
            "Firestore client not initialised. Ensure lifespan startup ran."
        )
    return _firestore_client


async def init_firestore() -> None:
    """Initialise the async Firestore client (called during FastAPI lifespan)."""
    global _firestore_client  # noqa: PLW0603
    settings = get_settings()
    _firestore_client = AsyncClient(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )
    logger.info(
        "Firestore AsyncClient initialised (project=%s, db=%s)",
        settings.gcp_project_id,
        settings.firestore_database,
    )


async def close_firestore() -> None:
    """Close the Firestore client gracefully (called during FastAPI lifespan shutdown)."""
    global _firestore_client  # noqa: PLW0603
    if _firestore_client is not None:
        await _firestore_client.close()
        _firestore_client = None
        logger.info("Firestore client closed.")


# ── Collection name constants ─────────────────────────────────────────────────
class Collections:
    USERS = "users"
    FOOTPRINT_SNAPSHOTS = "footprint_snapshots"
    CHALLENGES = "challenges"
    USER_CHALLENGES = "user_challenges"
    LEADERBOARD = "leaderboard"
    POSTS = "posts"
    CLUBS = "clubs"
    CLUB_MEMBERS = "club_members"
    CHAT_HISTORY = "chat_history"
    AI_FALLBACK_TIPS = "ai_fallback_tips"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_document(collection: str, doc_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch a single document by ID.
    Returns the document data dict or None if not found.
    """
    db = get_firestore()
    ref = db.collection(collection).document(doc_id)
    snap = await ref.get()
    if snap.exists:
        return {**snap.to_dict(), "id": snap.id}
    return None


async def set_document(
    collection: str,
    doc_id: str,
    data: dict[str, Any],
    merge: bool = False,
) -> None:
    """
    Write or merge a document.
    Use merge=True for partial updates to avoid overwriting fields.
    """
    db = get_firestore()
    ref = db.collection(collection).document(doc_id)
    await ref.set(data, merge=merge)


async def update_document(
    collection: str,
    doc_id: str,
    data: dict[str, Any],
) -> None:
    """Update specific fields of an existing document."""
    db = get_firestore()
    ref = db.collection(collection).document(doc_id)
    await ref.update(data)


async def delete_document(collection: str, doc_id: str) -> None:
    """Delete a document by ID."""
    db = get_firestore()
    ref = db.collection(collection).document(doc_id)
    await ref.delete()


async def batch_write(operations: list[dict[str, Any]]) -> None:
    """
    Execute multiple write operations in a single Firestore batch.

    Each operation dict must have:
      - 'type': 'set' | 'update' | 'delete'
      - 'collection': str
      - 'doc_id': str
      - 'data': dict (for set/update)
      - 'merge': bool (optional, for set)
    """
    db = get_firestore()
    batch: AsyncWriteBatch = db.batch()

    for op in operations:
        ref = db.collection(op["collection"]).document(op["doc_id"])
        op_type = op["type"]
        if op_type == "set":
            batch.set(ref, op["data"], merge=op.get("merge", False))
        elif op_type == "update":
            batch.update(ref, op["data"])
        elif op_type == "delete":
            batch.delete(ref)
        else:
            raise ValueError(f"Unknown batch operation type: '{op_type}'")

    await batch.commit()
    logger.debug("Batch committed with %d operations.", len(operations))


@asynccontextmanager
async def firestore_transaction() -> AsyncGenerator[AsyncTransaction, None]:
    """
    Async context manager that yields a Firestore transaction.
    Commits on successful exit; rolls back on exception.
    """
    db = get_firestore()
    transaction: AsyncTransaction = db.transaction()
    try:
        async with transaction:
            yield transaction
    except Exception:
        logger.exception("Firestore transaction rolled back due to exception.")
        raise


async def paginated_query(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int = 20,
    start_after: Any = None,
) -> tuple[list[dict[str, Any]], Any]:
    """
    Execute a paginated Firestore query.

    Returns:
        (list of document dicts, last_document_snapshot for next page cursor)
    """
    db = get_firestore()
    query: BaseQuery = db.collection(collection)

    if filters:
        for field, op, value in filters:
            query = query.where(field, op, value)

    if order_by:
        direction = "DESCENDING" if descending else "ASCENDING"
        query = query.order_by(order_by, direction=direction)

    if start_after is not None:
        query = query.start_after(start_after)

    query = query.limit(limit)
    docs = [snap async for snap in query.stream()]

    results = [{**snap.to_dict(), "id": snap.id} for snap in docs]
    last_snap = docs[-1] if docs else None
    return results, last_snap


async def atomic_increment(
    collection: str, doc_id: str, field: str, delta: int | float = 1
) -> None:
    """
    Atomically increment a numeric field using Firestore SERVER_TIMESTAMP-free increment.
    Uses a transaction to guarantee consistency.
    """
    from google.cloud.firestore_v1 import Increment  # noqa: PLC0415

    db = get_firestore()
    ref = db.collection(collection).document(doc_id)
    await ref.update({field: Increment(delta)})
