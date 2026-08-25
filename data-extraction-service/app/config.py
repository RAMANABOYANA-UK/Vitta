"""Application configuration using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Service identity ---
    app_name: str = "medbills-data-extraction"
    environment: str = "development"

    # --- LLM extraction (Instructor + OpenAI-compatible) ---
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None  # for OpenAI-compatible proxies
    llm_temperature: float = 0.0
    llm_max_retries: int = 3

    # --- Extraction thresholds ---
    low_confidence_threshold: float = 0.6
    extraction_confidence_threshold: float = 0.7

    # --- Validation ---
    reference_data_dir: str = "data/reference"
    amount_tolerance: float = 0.01  # dollars

    # --- ML models ---
    models_dir: str = "models"
    anomaly_threshold: float = 0.7
    appeal_threshold_strong: float = 0.7
    appeal_threshold_moderate: float = 0.5

    # --- Database (Neon/Supabase-compatible PostgreSQL) ---
    database_url: Optional[str] = None
    db_echo: bool = False

    # --- Synthetic data generation ---
    synthetic_seed: int = 42
    synthetic_n_samples: int = 20000

    # --- Scoring feature fallbacks ---
    # Used only when a real value cannot be derived from the bill (so the
    # hardcoded-feature gap is closed: geography/provider-type/payer are now
    # derived from the document where possible, and these are the honest
    # fallbacks otherwise).
    default_geography: str = "NY"
    default_provider_type: str = "primary_care"
    default_payer: str = "payer_a"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()