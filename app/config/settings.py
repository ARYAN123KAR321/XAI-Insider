"""Central configuration. All values can be overridden via environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "XAI-Insider"
    environment: str = "lab"

    # --- storage ---
    data_dir: Path = PROJECT_ROOT / "data"
    model_dir: Path = PROJECT_ROOT / "models"
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'xai_insider.db'}"

    # --- auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    token_ttl_hours: int = 8
    demo_admin_password: str = "XAI-Admin-2026!"
    demo_analyst_password: str = "XAI-Analyst-2026!"
    demo_reviewer_password: str = "XAI-Reviewer-2026!"

    # --- UI ---
    api_base_url: str = "http://localhost:8000"

    # --- worker ---
    embedded_worker: bool = True
    worker_poll_seconds: float = 1.5

    # --- windows / detection ---
    window_minutes: int = 60
    stride_minutes: int = 15
    model_seed: int = 42
    iforest_estimators: int = 200
    iforest_contamination: float = 0.03
    alert_threshold: float = 85.0
    high_band: float = 75.0
    medium_band: float = 55.0
    priority_model_weight: float = 0.70
    priority_corroboration_weight: float = 0.30

    # --- baselines / explanation ---
    min_employee_baseline_windows: int = 10
    explanation_top_k: int = 5

    # --- uploads ---
    max_upload_mb: int = 50

    # --- optional capabilities (FR-18 / FR-19) ---
    enable_mlflow: bool = True
    mlflow_tracking_uri: str = f"file://{PROJECT_ROOT / 'data' / 'mlruns'}"
    enable_autoencoder: bool = True

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.model_dir, self.upload_dir,
                  self.generated_dir, self.cases_dir, self.exports_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()