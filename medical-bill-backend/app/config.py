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
    EXTRACTION_SERVICE_ENABLED: bool = True
    # When True, extraction failures raise instead of falling back to mock.
    # Only safe in production when Member 2 is guaranteed available.
    EXTRACTION_STRICT_MODE: bool = False

    # Document text extraction / OCR
    OCR_PROVIDER: str = "tesseract"  # "tesseract" | "textract" | "docai"
    # Google Document AI settings (only used when OCR_PROVIDER=docai)
    DOCAI_PROJECT_ID: str | None = None
    DOCAI_LOCATION: str = "us"
    DOCAI_PROCESSOR_ID: str | None = None

    # LLM letter generation settings
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "gpt-4o"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 1

    # Auth settings
    AUTH_ENABLED: bool = True
    # Static bearer token for simple API protection (dev-friendly).
    # In production, set a strong random value or switch to JWT.
    AUTH_TOKEN: str = "dev-token-change-me"
    # Optional JWT settings (used when a JWT is presented as a bearer token)
    JWT_SECRET: str = "change-me-too"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24  # 24 hours


settings = Settings()