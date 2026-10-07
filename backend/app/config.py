from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    database_url: str = "postgresql://getnet:getnet_local@localhost:5433/getnet"
    daily_model_call_limit: int = 100
    daily_web_call_limit: int = 10
    max_output_tokens: int = 900
    demo_mode: bool = True
    demo_unlimited_usage: bool = False
    auth_jwt_secret: SecretStr = SecretStr("change-this-demo-secret-before-production")
    auth_cookie_name: str = "getnet_session"
    customer_cookie_name: str = "getnet_customer_session"
    auth_session_minutes: int = 30
    auth_cookie_secure: bool = False
    auth_login_max_failures: int = 5
    auth_login_window_seconds: int = 300
    auth_login_lock_seconds: int = 900
    rate_limit_backend: str = "database"
    handoff_offline_timeout_seconds: int = 300
    handoff_mode: str = "manual"
    max_chats_per_tech: int = 5
    sla_wait_warn_seconds: int = 120
    allow_pull: bool = True
    rag_auto_ingest: bool = False
    seed_admin_username: str = "Admin"
    seed_admin_password: SecretStr = SecretStr("Admin")
    seed_admin_display_name: str = "Administrador"
    seed_technician_username: str = "Tecnico"
    seed_technician_password: SecretStr = SecretStr("Tecnico")
    seed_technician_display_name: str = "Técnico"
    default_customer_password: SecretStr = SecretStr("123")
    chat_allow_anonymous_demo: bool | None = None
    off_topic_policy: str | None = None
    web_search_allowed_domains: str = "getnet.net,site.getnet.com.br"
    rag_max_distance: float = 0.8
    guardrail_tool_timeout_seconds: float = 8.0
    app_env: str = "development"
    cors_allowed_origins: str = "http://127.0.0.1:8080,http://localhost:8080"
    csrf_trusted_origins: str = "http://127.0.0.1:8080,http://localhost:8080"
    max_request_body_bytes: int = 32_768
    websocket_max_message_bytes: int = 8_192
    websocket_messages_per_minute: int = 60
    websocket_idle_timeout_seconds: int = 120
    chat_requests_per_minute: int = 20
    customer_daily_token_budget: int = 100_000
    max_active_conversations_per_customer: int = 3
    ingest_allowed_domains: str = "getnet.net,site.getnet.com.br"
    ingest_timeout_seconds: float = 10.0
    ingest_max_bytes: int = 2_000_000
    ingest_pdf_max_bytes: int = 10_000_000
    ingest_pdf_max_pages: int = 100
    ingest_max_redirects: int = 4
    retention_days: int = 365
    retention_action: str = "anonymize"
    retention_interval_hours: int = 24
    conversation_history_messages: int = 8
    conversation_history_chars: int = 6000
    conversation_summary_chars: int = 3000
    openai_timeout_seconds: float = 20.0
    openai_max_retries: int = 2
    openai_circuit_failure_threshold: int = 4
    openai_circuit_reset_seconds: int = 60
    metrics_token: SecretStr = SecretStr("")

    @property
    def unlimited_demo_usage(self) -> bool:
        return self.demo_unlimited_usage and self.demo_mode and self.app_env.casefold() == "development"

    @property
    def anonymous_chat_enabled(self) -> bool:
        requested = (
            self.demo_mode if self.chat_allow_anonymous_demo is None else self.chat_allow_anonymous_demo
        )
        return self.app_env.casefold() == "development" and self.demo_mode and requested

    @property
    def effective_off_topic_policy(self) -> str:
        # Old demo environments may still contain OFF_TOPIC_POLICY=challenge.
        # Legacy values cannot re-enable unrelated topics such as weather.
        return "getnet_exchange"

    @property
    def allowed_web_domains(self) -> tuple[str, ...]:
        return tuple(
            item.strip().casefold() for item in self.web_search_allowed_domains.split(",") if item.strip()
        )

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(
            item.strip().rstrip("/") for item in self.cors_allowed_origins.split(",") if item.strip()
        )

    @property
    def trusted_csrf_origins(self) -> tuple[str, ...]:
        return tuple(
            item.strip().rstrip("/") for item in self.csrf_trusted_origins.split(",") if item.strip()
        )

    @property
    def allowed_ingest_domains(self) -> tuple[str, ...]:
        return tuple(
            item.strip().casefold().lstrip(".")
            for item in self.ingest_allowed_domains.split(",")
            if item.strip()
        )

    @property
    def production(self) -> bool:
        return self.app_env.casefold() == "production"

    @property
    def effective_handoff_mode(self) -> str:
        return self.handoff_mode if self.handoff_mode in {"manual", "auto"} else "manual"

    def validate_production(self) -> None:
        if not self.production:
            return
        problems = []
        secret = self.auth_jwt_secret.get_secret_value()
        if len(secret) < 32 or secret == "change-this-demo-secret-before-production":
            problems.append("AUTH_JWT_SECRET deve ser aleatório e ter ao menos 32 caracteres")
        if self.demo_mode:
            problems.append("DEMO_MODE deve ser false")
        if self.chat_allow_anonymous_demo is True or self.anonymous_chat_enabled:
            problems.append("CHAT_ALLOW_ANONYMOUS_DEMO deve ser false")
        if "*" in self.allowed_origins:
            problems.append("CORS_ALLOWED_ORIGINS não aceita curinga")
        if self.seed_admin_username == "Admin" or self.seed_admin_password.get_secret_value() == "Admin":
            problems.append("credenciais padrão do administrador são proibidas")
        if (
            self.seed_technician_username == "Tecnico"
            or self.seed_technician_password.get_secret_value() == "Tecnico"
        ):
            problems.append("credenciais padrão do técnico são proibidas")
        if "getnet_local" in self.database_url:
            problems.append("senha padrão do banco é proibida")
        if self.rate_limit_backend != "database":
            problems.append("RATE_LIMIT_BACKEND deve ser database para compartilhar limites entre réplicas")
        if problems:
            raise RuntimeError("Configuração de produção insegura: " + "; ".join(problems))


@lru_cache
def settings() -> Settings:
    return Settings()
