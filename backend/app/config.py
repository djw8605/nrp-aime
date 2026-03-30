"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://nrp:nrp@localhost:5432/nrp_aime"

    # Prometheus (used for live usage display in the API)
    prometheus_url: str = "https://prometheus.nrp-nautilus.io"

    # ClickHouse accounting database
    clickhouse_host: str = ""
    clickhouse_port: int = 8443
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "access_accounting"
    clickhouse_table: str = "cluster_namespace_usage_daily"
    clickhouse_secure: bool = True

    # GPU resource name sent to AMIE Usage API — must match the resource registered in AMIE.
    # Falls back to Project.resource_type when blank.
    amie_gpu_resource_name: str = ""

    # AIME / AMIE
    amie_site_name: str = "NRP"
    # Optional comma-separated list of AMIE site names for multi-site polling.
    # Example: "NRP,ACCESS"
    amie_site_names: str = ""
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

    # NRP portal RPC integration (namespace + membership provisioning)
    portal_rpc_url: str = "https://portal.nrp.ai/rpc"
    portal_rpc_token: str = ""
    portal_rpc_namespace: str = "access"
    portal_rpc_timeout_seconds: float = 15.0

    # Portal authentication
    auth_dev_bypass: bool = False
    auth_state_ttl_minutes: int = 30
    auth_session_cookie_name: str = "nrp_portal_session"
    auth_session_ttl_minutes: int = 12 * 60
    auth_session_https_only: bool = False
    auth_admin_authorize_url: str = ""
    auth_admin_client_id: str = ""
    auth_admin_client_secret: str = ""
    auth_admin_oidc_configuration_url: str = ""
    auth_admin_token_url: str = ""
    auth_admin_userinfo_url: str = ""
    auth_admin_logout_url: str = ""
    auth_admin_jwks_url: str = ""
    auth_admin_scope: str = "openid profile email"
    auth_admin_redirect_path: str = "/api/v1/auth/callback"
    auth_admin_stub_login_email: str = ""

    # Invite / onboarding
    invite_token_ttl_hours: int = 72
    invite_state_ttl_minutes: int = 30
    invite_require_email_match: bool = True
    invite_email_from: str = ""

    # Invite login redirect scaffold
    authentik_authorize_url: str = ""
    authentik_client_id: str = ""
    authentik_client_secret: str = ""
    authentik_oidc_configuration_url: str = ""
    authentik_token_url: str = ""
    authentik_userinfo_url: str = ""
    authentik_scope: str = "openid profile email"
    authentik_redirect_path: str = "/api/v1/invites/callback"
    authentik_stub_login_email: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def configured_amie_site_names() -> list[str]:
    """Return ordered, deduplicated AMIE site names from config."""
    configured: list[str] = []
    raw = str(settings.amie_site_names or "")
    for token in raw.replace(";", ",").split(","):
        site = token.strip()
        if site and site not in configured:
            configured.append(site)

    default_site = str(settings.amie_site_name or "").strip()
    if default_site and default_site not in configured:
        configured.insert(0, default_site)

    if not configured:
        configured.append("NRP")
    return configured
