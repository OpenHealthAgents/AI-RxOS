from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.db.pool import close_pool, init_pool
from app.routers import health, wiki

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.llm_wiki_api_key:
        logger.warning(
            "LLM_WIKI_API_KEY is not set -- llm-wiki is accepting unauthenticated "
            "requests. This is fine for local dev but must be set before deploying."
        )
    await init_pool()
    logger.info("llm-wiki ready, database pool initialized")
    yield
    await close_pool()


app = FastAPI(
    title="AI-RxOS LLM Wiki Service",
    description=(
        "Persistent backend for the Open Knowledge Format (OKF) LLM Wiki. "
        "Implements the write/read contract already used by "
        "services/literature's LLMWikiClient (POST /api/v1/wiki/compile) "
        "and services/search's LLMWikiProvider (POST /llmwiki/query)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(wiki.router)
