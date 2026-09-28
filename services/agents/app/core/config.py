import base64
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    agent_max_transitions: int = 100
    agent_max_retries: int = 3
    allowed_agent_types: str = "default"
    agent_retry_base_seconds: float = 1.0
    agent_worker_reclaim_idle_seconds: float = 60.0
    agent_worker_execution_timeout_seconds: float = 300.0
    agent_worker_lock_ttl_seconds: float = 390.0
    redis_operation_timeout_seconds: float = 10.0
    redis_password: str | None = None
    redis_tls_required: bool = False
    agent_job_stream: str = "agents:jobs"
    agent_job_group: str = "agents-workers"
    agent_dlq_stream: str = "agents:jobs:dead-letter"
    agent_rate_limit_per_minute: int = 60
    agent_max_concurrent_executions: int = 10
    agent_max_input_bytes: int = 1_000_000
    model_pricing_json: str | None = None
    execution_payload_ttl: int = 86400
    checkpoint_ttl: int = 86400
    metadata_ttl: int = 86400
    idempotency_ttl: int = 86400

    database_url: str = "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"
    redis_url: str = "redis://redis:6379/0"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme_neo4j"
    opensearch_url: str = "http://opensearch:9200"
    jwt_secret: str = "change_this_dev_secret_before_deploying"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    # Canonical LLM Wiki URL (see root .env.example / services/search). When
    # unset, long-term agent memory persistence is skipped rather than
    # pointed at a service that doesn't exist in this repo's docker-compose.
    llm_wiki_url: str | None = None
    model_registry_json: str | None = None
    execution_payload_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    @model_validator(mode="after")
    def require_production_payload_key(self) -> "Settings":
        production = self.environment.lower() in {"production", "prod"}
        if production:
            if self.execution_payload_key == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=":
                raise ValueError("EXECUTION_PAYLOAD_KEY must be configured in production")
            if self.jwt_secret in {"", "change_this_dev_secret_before_deploying", "changeme"}:
                raise ValueError("JWT_SECRET must be configured in production")
            if not self.jwt_issuer or not self.jwt_audience:
                raise ValueError("JWT_ISSUER and JWT_AUDIENCE must be configured in production")
            if self.redis_tls_required and not self.redis_url.startswith("rediss://"):
                raise ValueError("production Redis must use rediss:// when TLS is required")
        try:
            decoded_key = base64.urlsafe_b64decode(self.execution_payload_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError("EXECUTION_PAYLOAD_KEY must be a valid Fernet key") from exc
        if len(decoded_key) != 32 or len(self.execution_payload_key) != 44:
            raise ValueError("EXECUTION_PAYLOAD_KEY must be a valid Fernet key")
        if any(value <= 0 for value in (self.execution_payload_ttl, self.checkpoint_ttl, self.metadata_ttl, self.idempotency_ttl)):
            raise ValueError("retention TTLs must be positive")
        if any(value > 31_536_000 for value in (self.execution_payload_ttl, self.checkpoint_ttl, self.metadata_ttl, self.idempotency_ttl)):
            raise ValueError("retention TTLs must not exceed one year")
        if self.agent_worker_lock_ttl_seconds <= (
            self.agent_worker_execution_timeout_seconds
            + self.agent_worker_reclaim_idle_seconds
        ):
            raise ValueError(
                "AGENT_WORKER_LOCK_TTL_SECONDS must exceed execution timeout plus reclaim idle timeout"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
