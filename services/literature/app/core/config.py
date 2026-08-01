from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"
    redis_url: str = "redis://redis:6379/0"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme_neo4j"
    opensearch_url: str = "http://opensearch:9200"
    search_service_url: str = "http://search:8084"
    search_service_timeout_seconds: int = 5
    search_service_max_retries: int = 3
    kg_service_url: str = "http://kg:8083"
    kg_service_timeout_seconds: int = 5
    kg_service_max_retries: int = 3
    llmwiki_service_url: str = "http://llmwiki:8086"
    llmwiki_service_timeout_seconds: int = 5
    llmwiki_service_max_retries: int = 3
    jwt_secret: str = "changeme_secret"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    pubmed_base_url: str = "https://api.ncbi.nlm.nih.gov/lit/ctxp/v1/pubmed/"
    pmc_base_url: str = "https://api.ncbi.nlm.nih.gov/lit/ctxp/v1/pmc/"
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/query"
    biorxiv_base_url: str = "https://api.biorxiv.org"
    medrxiv_base_url: str = "https://api.biorxiv.org"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
