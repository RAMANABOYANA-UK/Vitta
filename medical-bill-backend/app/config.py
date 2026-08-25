from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    STORAGE_TYPE: str = "local"  # "local" or "s3"
    LOCAL_STORAGE_PATH: str = "./uploads"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str | None = None
    ENVIRONMENT: str = "development"

    # Pipeline settings
    PIPELINE_DELAY_SECONDS: float = 3.0
    MOCK_PIPELINE: bool = True

    # Rust rules engine settings
    RULES_ENGINE_URL: str = "http://localhost:3001"
    RULES_ENGINE_TIMEOUT_SECONDS: float = 5.0
    RULES_ENGINE_ENABLED: bool = True

    # Member 2 – Extraction + XGBoost scoring service
    EXTRACTION_SERVICE_URL: str = "http://localhost:8001"
    EXTRACTION_SERVICE_TIMEOUT_SECONDS: float = 30.0
    EXTRACTION_SERVICE_ENABLED: bool = False

    # LLM letter generation settings
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "gpt-4o"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 1

    # Authentication / session settings
    # Opaque session tokens are hashed (SHA-256) before storage; only the hash is
    # persisted. Tokens expire after this many hours.
    AUTH_TOKEN_TTL_HOURS: int = 24
    # Per-user fixed-window rate limit on uploads (requests per minute). In-process
    # only; a multi-worker or multi-instance deployment needs a shared store (Redis).
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 20

    # Email verification — required step toward the full PHI gate.
    # When True, a freshly-registered account is NOT considered verified until its
    # email is confirmed (login is refused with a "email_not_verified" 403), and the
    # verify/resend endpoints become load-bearing. Default False keeps the existing
    # dev/demo registration flow working unchanged; flip it (and supply a real email
    # sender) before touching real patient data.
    EMAIL_VERIFICATION_REQUIRED: bool = False
    # How long a verification token is valid.
    EMAIL_VERIFICATION_TTL_HOURS: int = 24

    # Ingestion / OCR.
    # Default False on purpose: the ingestion path only ever claims to have read a
    # real document when it actually did. A text-layer PDF needs no OCR; image and
    # scanned-PDF bills require OCR, which needs pytesseract + a tesseract binary.
    OCR_ENABLED: bool = False

    # CORS: an explicit allowlist of browser origins. A wildcard ("*") is invalid
    # together with allow_credentials=True, so we never use one. Comma-separated.
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://localhost:8080,http://127.0.0.1:5500"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed, de-duplicated CORS origins (order preserved)."""
        seen: dict[str, None] = {}
        for origin in self.CORS_ALLOWED_ORIGINS.split(","):
            cleaned = origin.strip()
            if cleaned:
                seen.setdefault(cleaned, None)
        return list(seen)


settings = Settings()