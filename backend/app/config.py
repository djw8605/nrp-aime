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
    amie_packet_reprocess_max_retries: int = 5
    amie_packet_reprocess_lockout_minutes: int = 30

    # Authentik
    authentik_base_url: str = ""
    authentik_api_token: str = ""
    # Dev-only helper for testing lifecycle transitions without real integration.
    authentik_stub_auto_account_made: bool = False

    # Accounting stub data collection
    accounting_stub_enabled: bool = True
    accounting_stub_cpu_ratio: float = 0.35
    accounting_stub_gpu_ratio: float = 0.20

    # Alerts / webhooks
    alert_webhook_url: str = ""
    alert_slack_webhook_url: str = ""
    alert_email_to: str = ""
    alert_email_from: str = ""
    alert_smtp_host: str = ""
    alert_smtp_port: int = 587
    alert_smtp_username: str = ""
    alert_smtp_password: str = ""
    alert_smtp_use_tls: bool = True
    alert_min_interval_minutes: int = 30
    alert_worker_stale_seconds: int = 300
    alert_parse_failures_threshold: int = 10
    alert_reconcile_stale_minutes: int = 120

    # App
    app_name: str = "NRP AIME Allocation Manager"
    app_secret_key: str = "dev-change-me"
    debug: bool = False
    allowed_origins: list[str] = []
    frontend_base_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"

    # Invite / onboarding
    invite_token_ttl_hours: int = 72
    invite_state_ttl_minutes: int = 30
    invite_require_email_match: bool = True

    # Auth callback / login redirect scaffold
    authentik_authorize_url: str = ""
    authentik_client_id: str = ""
    authentik_scope: str = "openid profile email"
    authentik_redirect_path: str = "/api/v1/invites/callback"
    authentik_stub_login_email: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
