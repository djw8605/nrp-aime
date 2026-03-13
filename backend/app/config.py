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

    # App
    app_name: str = "NRP AIME Allocation Manager"
    debug: bool = False
    allowed_origins: list[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
