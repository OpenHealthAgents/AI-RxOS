from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Service-to-service auth for literature/search -> llm-wiki calls.

    Matches the bearer scheme services/literature's LLMWikiClient and
    services/search's LLMWikiProvider already send
    (`Authorization: Bearer {LLM_WIKI_API_KEY}`). When LLM_WIKI_API_KEY is
    not configured, requests are accepted unauthenticated -- this mirrors
    the client's own behavior (it only attaches the header when it has a
    key) and keeps local dev frictionless; app/main.py logs a warning at
    startup when this dev posture is active.
    """
    settings = get_settings()
    if not settings.llm_wiki_api_key:
        return

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )

    token = authorization.split(" ", 1)[1].strip()
    if token != settings.llm_wiki_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
        )
