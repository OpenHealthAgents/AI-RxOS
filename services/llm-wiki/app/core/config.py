from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    # Same shared Postgres instance every other AI-RxOS service uses.
    # Wiki data lives in its own `llm_wiki` schema (see migrations/), not a
    # separate database, so no new datastore is introduced.
    database_url: str = "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"

    # Service-to-service auth. When unset, the service accepts
    # unauthenticated requests (matches services/literature's
    # LLMWikiClient, which only sends a bearer token when it has one) --
    # this is a dev-only posture and a startup warning is logged if unset.
    llm_wiki_api_key: str | None = None

    # /llmwiki/query result size (see services/search's LLMWikiProvider).
    query_default_limit: int = 10
    query_max_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
