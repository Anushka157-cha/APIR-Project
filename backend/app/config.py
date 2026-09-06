from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://apir:apir@localhost:5432/apir"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-local-dev"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0
    embedding_model: str = "text-embedding-3-small"

    otel_endpoint: str = "http://localhost:4318"
    prometheus_url: str = "http://localhost:9090"

    detection_interval_seconds: int = 8
    latency_p95_threshold_ms: float = 800
    error_rate_threshold: float = 0.05
    zscore_threshold: float = 3.0
    traffic_zscore_threshold: float = 3.5
    auto_execute_low_risk: bool = False
    baseline_window_minutes: int = 30
    verification_samples: int = 4
    verification_sample_interval_seconds: float = 5.0

    # Safety controls
    dry_run_mode: bool = False
    remediation_timeout_seconds: int = 60
    enable_rollback: bool = True

    demo_admin_password: str = "admin123"
    demo_sre_password: str = "sre123"
    demo_viewer_password: str = "viewer123"

    knowledge_dir: str = "/knowledge"


settings = Settings()
