from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.utils.html_utils import (
    extract_page_metadata,
    is_access_restricted,
    normalize_url,
    url_allowed_domain,
)

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    url: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    html: str | None = None


class WebCrawler:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.timeout = float(self.config.get("timeout", 10.0))
        self.max_pages = int(self.config.get("max_pages", 10))
        self.max_depth = int(self.config.get("max_depth", 2))
        self.rate_limit = float(self.config.get("rate_limit", 0.5))
        self.user_agent = str(self.config.get("user_agent", "AI-RxOS LiteratureBot/1.0"))
        self.allowed_domains = [d.lower() for d in self.config.get("allowed_domains", []) if d]
        self.visited: set[str] = set()
        self.queue: deque[tuple[str, int]] = deque()
        self.results: list[CrawlResult] = []
        self.last_request_at = 0.0
        self.robots_cache: dict[str, bool] = {}

    def enqueue(self, url: str, depth: int = 0) -> None:
        normalized = normalize_url(url)
        if not normalized:
            return
        if normalized in self.visited:
            return
        if not url_allowed_domain(normalized, self.allowed_domains):
            logger.debug("URL outside allowed domains: %s", normalized)
            return
        self.visited.add(normalized)
        self.queue.append((normalized, depth))

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain in self.robots_cache:
            return self.robots_cache[domain]
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"
        try:
            response = httpx.get(robots_url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            if response.status_code == 200 and "Disallow: /" in response.text:
                logger.info("Robots blocked crawling of domain %s", domain)
                self.robots_cache[domain] = False
                return False
            self.robots_cache[domain] = True
            return True
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch robots.txt for %s: %s", domain, exc)
            self.robots_cache[domain] = True
            return True

    def _wait_rate_limit(self) -> None:
        now = time.time()
        since = now - self.last_request_at
        if since < self.rate_limit:
            time.sleep(self.rate_limit - since)
        self.last_request_at = time.time()

    def crawl(self, seed_urls: list[str]) -> list[CrawlResult]:
        for seed in seed_urls:
            self.enqueue(seed, 0)

        while self.queue and len(self.results) < self.max_pages:
            url, depth = self.queue.popleft()
            if depth > self.max_depth:
                logger.debug("Skipping %s due to depth limit", url)
                continue
            if not self._can_fetch(url):
                self.results.append(CrawlResult(url=url, success=False, error="disallowed_by_robots"))
                continue
            self._wait_rate_limit()
            try:
                response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
                if response.status_code != 200:
                    self.results.append(CrawlResult(url=url, success=False, status_code=response.status_code, error="http_error"))
                    continue
                html_text = response.text
                if is_access_restricted(html_text):
                    self.results.append(CrawlResult(url=url, success=False, status_code=response.status_code, error="access_restricted"))
                    continue
                metadata = extract_page_metadata(html_text, url)
                metadata["source_url"] = url
                metadata["depth"] = depth
                result = CrawlResult(url=url, success=True, status_code=response.status_code, metadata=metadata, html=html_text)
                self.results.append(result)
                if depth < self.max_depth:
                    from app.utils.html_utils import extract_search_result_urls
                    for link in extract_search_result_urls(html_text, base_url=url):
                        if len(self.visited) >= self.max_pages:
                            break
                        self.enqueue(link, depth + 1)
            except httpx.HTTPError as exc:
                self.results.append(CrawlResult(url=url, success=False, error=str(exc)))
            except (ValueError, TypeError, RuntimeError) as exc:
                self.results.append(CrawlResult(url=url, success=False, error=f"parse_error:{exc}"))
        return self.results
