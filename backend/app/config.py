"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://nrp:nrp@localhost:5432/nrp_aime"

    # Prometheus
    prometheus_url: str = "https://prometheus.nrp-nautilus.io"

    # AIME / AMIE
    amie_site_name: str = "NRP"
    amie_api_key: str = ""
    amie_url: str = "https://amieclient.xsede.org/v0.10/"
    amie_processed_client_state: str = "nrp-processed"
    amie_usage_url: str = "https://usage.xsede.org/api/v1"
    amie_usage_interval_minutes: int = 1440
    amie_usage_gpu_charge_factor: float = 1.0
    amie_usage_default_username: str = "nrp-system"
    amie_account_confirmation_enabled: bool = True

    # Authentik
    authentik_base_url: str = ""
    authentik_api_token: str = ""
    # Dev-only helper for testing lifecycle transitions without real integration.
    authentik_stub_auto_account_made: bool = False

    # App
    app_name: str = "NRP AIME Allocation Manager"
    debug: bool = False
    allowed_origins: list[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
