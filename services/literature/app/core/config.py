from functools import lru_cache

from pydantic import AliasChoices, Field
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
    jwt_secret: str = "change_this_dev_secret_before_deploying"

    kg_service_url: str = "http://kg:8083"
    # LLM_WIKI_URL is the repo-wide canonical env var (see root .env.example
    # and services/search); OKF_WIKI_URL is kept as a fallback alias so
    # existing literature-only deployments don't break.
    okf_wiki_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_WIKI_URL", "OKF_WIKI_URL"),
    )
    okf_wiki_dir: str = "wiki-root"

    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_api_url: str | None = None
    llm_model: str = "gpt-3.5-turbo"
    llm_timeout: float = 10.0
    llm_max_retries: int = 1
    llm_backoff_seconds: float = 0.25

    ner_provider: str = "rule_based"
    ner_model: str = "en_core_web_sm"
    ner_timeout: float = 10.0

    kg_timeout: float = 5.0
    kg_max_retries: int = 1
    kg_backoff_seconds: float = 0.25

    wiki_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_WIKI_API_KEY", "WIKI_API_KEY"),
    )
    wiki_timeout: float = 5.0
    wiki_max_retries: int = 1
    wiki_backoff_seconds: float = 0.25

    crawler_user_agent: str = "AI-RxOS LiteratureBot/1.0"
    crawler_timeout: float = 10.0
    crawler_rate_limit: float = 0.5
    crawler_max_pages: int = 10
    crawler_max_depth: int = 2
    crawler_allowed_domains: list[str] = []

    cors_origins: list[str] = ["*"]

    # Base URLs for connectors
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    pmc_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/v2/studies"
    biorxiv_base_url: str = "https://api.biorxiv.org/details/biorxiv"
    medrxiv_base_url: str = "https://api.biorxiv.org/details/medrxiv"

    # Services URLs and parameters
    search_service_url: str = "http://search:8084"
    kg_service_timeout_seconds: float = 5.0
    kg_service_max_retries: int = 3
    llmwiki_service_url: str = "http://wiki:8000"
    llmwiki_service_timeout_seconds: float = 5.0
    llmwiki_service_max_retries: int = 3
    search_service_timeout_seconds: float = 5.0
    search_service_max_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
