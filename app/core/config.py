from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment and .env."""

    # LLM Configuration
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: float = 45.0

    # Data and Persistence Paths
    database_path: str = "./data/support_tickets.db"
    csv_path: str = "./data/support_tickets.csv"

    # Server & Environment Settings
    environment: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    workers: int = 2
    log_level: str = "INFO"
    docs_enabled: bool = True
    cors_origins: str = "*"

    # Anomaly Detection Parameters
    anomaly_response_percentile: float = 95.0
    anomaly_resolution_iqr_multiplier: float = 1.5

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins or self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return path

    @property
    def resolved_csv_path(self) -> Path:
        primary = Path(self.csv_path)
        if primary.exists():
            return primary
        # Fallback to AI Intern - Assessment if running from alternative workspace root
        fallback = Path("AI Intern - Assessment/support_tickets.csv")
        if fallback.exists():
            return fallback
        return primary


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
