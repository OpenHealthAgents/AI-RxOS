from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"
    kg_canonical_database_url: str = "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"
    redis_url: str = "redis://redis:6379/0"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme_neo4j"
    opensearch_url: str = "http://opensearch:9200"
    jwt_secret: str = "change_this_dev_secret_before_deploying"
    research_llm_base_url: str | None = None
    research_llm_api_key: str | None = None
    research_llm_model: str | None = None
    research_llm_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment.lower() in {"production", "prod"}:
            if "jwt_secret" not in self.model_fields_set or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be explicitly configured with at least 32 characters in production")
            if "kg_canonical_database_url" not in self.model_fields_set:
                raise ValueError("KG_CANONICAL_DATABASE_URL must be explicitly configured in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
