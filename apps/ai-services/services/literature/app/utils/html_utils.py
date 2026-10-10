from __future__ import annotations

import html
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}

RESTRICTED_KEYWORDS = [
    "sign in",
    "sign_in",
    "log in",
    "login",
    "access denied",
    "403",
    "404",
    "paywall",
    "subscription",
    "restricted",
]


def normalize_url(url: str, base_url: str | None = None) -> str:
    if base_url:
        url = urljoin(base_url, url)
    url = html.unescape(url.strip())
    parsed = urlparse(url)
    cleaned_query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_QUERY_PARAMS]
    )
    normalized = urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.params, cleaned_query, ""))
    return normalized


def is_access_restricted(html_text: str) -> bool:
    if not html_text:
        return False
    lower = html_text.lower()
    return any(token in lower for token in RESTRICTED_KEYWORDS)


class LinkAndMetaParser(HTMLParser):
    def __init__(self, base_url: str | None = None):
        super().__init__()
        self.base_url = base_url
        self.title_fragments: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = attrs_dict.get("name") or attrs_dict.get("property")
            content = attrs_dict.get("content") or attrs_dict.get("value")
            if name and content:
                self.meta[name.lower()] = content.strip()
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                normalized = normalize_url(href, self.base_url)
                if normalized:
                    self.links.append(normalized)

    def handle_endtag(self, tag: str):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str):
        if self._in_title:
            self.title_fragments.append(data)

    def get_title(self) -> str | None:
        title = " ".join(self.title_fragments).strip()
        return title or None

    def get_meta(self) -> dict[str, str]:
        return self.meta

    def get_links(self) -> list[str]:
        unique_links: list[str] = []
        seen: set[str] = set()
        for url in self.links:
            if url not in seen:
                seen.add(url)
                unique_links.append(url)
        return unique_links


def extract_page_metadata(html_text: str, url: str) -> dict[str, Any]:
    parser = LinkAndMetaParser(base_url=url)
    parser.feed(html_text)
    title = parser.get_title() or parser.get_meta().get("og:title") or parser.get_meta().get("twitter:title")
    description = (
        parser.get_meta().get("description")
        or parser.get_meta().get("og:description")
        or parser.get_meta().get("twitter:description")
    )
    authors = []
    if "citation_author" in parser.get_meta():
        authors = [author.strip() for author in parser.get_meta()["citation_author"].split(";") if author.strip()]
    elif "author" in parser.get_meta():
        authors = [author.strip() for author in parser.get_meta()["author"].split(",") if author.strip()]
    published_date = (
        parser.get_meta().get("citation_publication_date")
        or parser.get_meta().get("article:published_time")
        or parser.get_meta().get("date")
        or parser.get_meta().get("pubdate")
    )
    content = strip_tags(html_text)
    return {
        "title": title,
        "abstract": description,
        "content": content,
        "authors": authors,
        "published_date": published_date,
        "url": url,
        "metadata": {"meta": parser.get_meta()},
    }


def extract_search_result_urls(html_text: str, base_url: str | None = None) -> list[str]:
    parser = LinkAndMetaParser(base_url=base_url)
    parser.feed(html_text)
    return parser.get_links()


def strip_tags(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def url_allowed_domain(url: str, allowed_domains: Iterable[str]) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    hostname = hostname.lower()
    if not hostname:
        return False
    if not allowed_domains:
        return True
    for allowed in allowed_domains:
        if hostname == allowed.lower() or hostname.endswith("." + allowed.lower()):
            return True
    return False
