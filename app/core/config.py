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
    groq_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 45.0

    # Data and Persistence Paths
    database_path: str = "./data/support_tickets.db"
    csv_path: str = "./data/support_tickets.csv"

    # Server Settings
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Anomaly Detection Parameters
    anomaly_response_percentile: float = 95.0
    anomaly_resolution_iqr_multiplier: float = 1.5

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
