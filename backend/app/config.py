"""
EcoQuest Configuration Module
Loads all settings from environment and GCP Secret Manager.
Never reads secrets directly from env vars in routers.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from google.cloud import secretmanager
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment and Secret Manager."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = Field(default="EcoQuest", description="Application name")
    app_version: str = Field(default="1.0.0", description="Semantic version")
    environment: str = Field(default="production", description="Runtime environment")
    debug: bool = Field(default=False, description="Enable debug mode")

    # ── GCP Project ───────────────────────────────────────────────────────────
    gcp_project_id: str = Field(..., description="GCP project ID")
    gcp_region: str = Field(default="asia-south1", description="GCP region")

    # ── Firestore ─────────────────────────────────────────────────────────────
    firestore_database: str = Field(default="(default)", description="Firestore DB name")

    # ── Cloud Storage ─────────────────────────────────────────────────────────
    gcs_bucket_name: str = Field(..., description="GCS bucket for user uploads")
    gcs_signed_url_expiry_seconds: int = Field(
        default=900, description="Signed URL expiration in seconds"
    )

    # ── Vertex AI ─────────────────────────────────────────────────────────────
    vertex_ai_location: str = Field(
        default="asia-south1", description="Vertex AI region"
    )
    vertex_ai_model: str = Field(
        default="gemini-2.5-flash", description="Vertex AI model ID"
    )

    # ── Security ──────────────────────────────────────────────────────────────
    frontend_origin: str = Field(
        default="*", description="Allowed CORS origin for frontend"
    )
    internal_auth_token_secret: str = Field(
        default="ecoquest-internal-token",
        description="Secret Manager key for internal auth token",
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    chat_rate_limit_per_minute: int = Field(
        default=60, description="Max /chat requests per IP per minute"
    )

    # ── Resolved secrets (populated at startup) ───────────────────────────────
    _gemini_api_key: Optional[str] = None
    _internal_auth_token: Optional[str] = None

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    def load_secrets(self) -> None:
        """
        Pull secrets from environment or GCP Secret Manager at application startup.
        Raises RuntimeError if a required secret cannot be fetched.
        """
        client = secretmanager.SecretManagerServiceClient()
        project = self.gcp_project_id

        def _fetch(secret_id: str, required: bool = True) -> Optional[str]:
            name = f"projects/{project}/secrets/{secret_id}/versions/latest"
            try:
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("utf-8").strip()
            except Exception as exc:  # noqa: BLE001
                if required:
                    raise RuntimeError(
                        f"Failed to load required secret '{secret_id}': {exc}"
                    ) from exc
                logger.warning("Optional secret '%s' not found: %s", secret_id, exc)
                return None

        # Try env vars first (injected by Cloud Run --set-secrets), fallback to direct API fetch
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not self._gemini_api_key:
            self._gemini_api_key = _fetch("gemini-api-key", required=True)

        self._internal_auth_token = os.getenv("INTERNAL_AUTH_TOKEN")
        if not self._internal_auth_token:
            self._internal_auth_token = _fetch(
                self.internal_auth_token_secret, required=False
            )

        logger.info("All secrets resolved successfully.")

    @property
    def gemini_api_key(self) -> str:
        if not self._gemini_api_key:
            raise RuntimeError(
                "gemini_api_key not loaded. Call settings.load_secrets() first."
            )
        return self._gemini_api_key

    @property
    def internal_auth_token(self) -> Optional[str]:
        return self._internal_auth_token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()  # type: ignore[call-arg]
