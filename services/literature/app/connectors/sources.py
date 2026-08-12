from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any
from urllib.parse import urlparse

from app.connectors.base import BaseConnector
from app.crawling.crawler import WebCrawler
from app.utils.html_utils import (
    extract_page_metadata,
    extract_search_result_urls,
    is_access_restricted,
    normalize_url,
    url_allowed_domain,
)

logger = logging.getLogger(__name__)


def _matches_query(query: str, *values: str | None) -> bool:
    query_terms = [term for term in query.lower().split() if term]
    haystack = " ".join(value or "" for value in values).lower()
    return not query_terms or any(term in haystack for term in query_terms)


def _resolve_search_url(base_url: str, query: str, path: str) -> str:
    params = {"q": query.strip() or "oncology"}
    # allow connector-specific query path templates
    if "{query}" in path:
        return path.format(query=urllib.parse.quote(query.strip() or "oncology"))
    if "?" in path:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"


def _parse_detail_urls(html_text: str, base_url: str) -> list[str]:
    urls = extract_search_result_urls(html_text, base_url=base_url)
    detail_urls = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and url_allowed_domain(url, [urlparse(base_url).hostname or ""]):
            detail_urls.append(url)
    return detail_urls


def _load_json_payload(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _normalize_detail_document(html_text: str, url: str, source: str, limitation: str | None = None) -> dict[str, Any]:
    metadata = extract_page_metadata(html_text, url)
    if limitation:
        metadata.setdefault("limitation", limitation)
    return {
        "title": metadata.get("title"),
        "abstract": metadata.get("abstract"),
        "content": metadata.get("content"),
        "authors": metadata.get("authors") or [],
        "published_date": metadata.get("published_date"),
        "source": source,
        "source_id": url,
        "doi": None,
        "url": url,
        "journal": source,
        "metadata": metadata,
    }


def _build_search_documents(search_html: str, base_url: str, source: str, limitation: str | None = None) -> list[dict[str, Any]]:
    metadata = extract_page_metadata(search_html, base_url)
    content_value = metadata.get("content")
    docs = [
        {
            "title": metadata.get("title") or f"{source.upper()} search results",
            "abstract": metadata.get("abstract") or metadata.get("meta", {}).get("description"),
            "content": content_value[:4000] if isinstance(content_value, str) else None,
            "authors": metadata.get("authors") or [],
            "published_date": metadata.get("published_date"),
            "source": source,
            "source_id": base_url,
            "doi": None,
            "url": base_url,
            "journal": f"{source.upper()} search",
            "metadata": {"query_url": base_url, "limitation": limitation, "meta": metadata.get("meta", {})},
        }
    ]
    return docs


def _fetch_detail_documents(connector: BaseConnector, search_html: str, base_url: str, source: str, limitation: str | None, max_results: int) -> list[dict[str, Any]]:
    detail_urls = _parse_detail_urls(search_html, base_url)
    documents: list[dict[str, Any]] = []
    for url in detail_urls:
        html = connector._request_text(url)
        if not html or is_access_restricted(html):
            continue
        documents.append(connector.normalize_document(_normalize_detail_document(html, url, source, limitation)))
        if len(documents) >= max_results:
            break
    return documents


def _fetch_html_search_documents(
    connector: BaseConnector,
    search_html: str,
    search_url: str,
    source: str,
    limitation: str | None,
    max_results: int,
) -> list[dict[str, Any]]:
    detail_urls = _parse_detail_urls(search_html, search_url)
    documents: list[dict[str, Any]] = []
    for url in detail_urls:
        html = connector._request_text(url)
        if not html or is_access_restricted(html):
            continue
        documents.append(connector.normalize_document(_normalize_detail_document(html, url, source, limitation)))
        if len(documents) >= max_results:
            break
    return documents


def _fetch_search_result_pages(connector: BaseConnector, search_url: str, source: str, query: str, limitation: str | None, max_results: int) -> list[dict[str, Any]]:
    html = connector._request_text(search_url)
    if not html:
        return []
    if is_access_restricted(html):
        return _build_search_documents(html, search_url, source, limitation)

    detail_documents = _fetch_detail_documents(connector, html, search_url, source, limitation, max_results)
    if detail_documents:
        return detail_documents

    return _build_search_documents(html, search_url, source, limitation)


class PubMedConnector(BaseConnector):
    """PubMed connector using NCBI E-utilities search and summary endpoints."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "pubmed"
        self.base_url = self.config.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils").rstrip("/")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        params = {
            "db": "pubmed",
            "term": query.strip() or "oncology",
            "retmode": "json",
            "retmax": kwargs.get("max_results", 5),
        }
        search = self._request_json(f"{self.base_url}/esearch.fcgi", params=params)
        id_list = (search or {}).get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        summary = self._request_json(
            f"{self.base_url}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"},
        )
        result_map = (summary or {}).get("result", {})
        documents: list[dict[str, Any]] = []
        for pmid in id_list:
            item = result_map.get(str(pmid), {})
            if not item:
                continue
            authors = [author.get("name") for author in item.get("authors", []) if isinstance(author, dict) and author.get("name")]
            documents.append(
                self.normalize_document(
                    {
                        "title": item.get("title"),
                        "abstract": item.get("sortfirstauthor"),
                        "source": self.name,
                        "source_id": f"PMID:{pmid}",
                        "authors": authors,
                        "published_date": item.get("pubdate"),
                        "doi": item.get("elocationid"),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "journal": item.get("source"),
                        "metadata": {"pmid": pmid, "query": params["term"]},
                    }
                )
            )
        return documents


class PMCConnector(BaseConnector):
    """PubMed Central connector using NCBI E-utilities search and summary endpoints."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "pmc"
        self.base_url = self.config.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils").rstrip("/")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        params = {
            "db": "pmc",
            "term": query.strip() or "oncology",
            "retmode": "json",
            "retmax": kwargs.get("max_results", 5),
        }
        search = self._request_json(f"{self.base_url}/esearch.fcgi", params=params)
        id_list = (search or {}).get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        summary = self._request_json(
            f"{self.base_url}/esummary.fcgi",
            params={"db": "pmc", "id": ",".join(id_list), "retmode": "json"},
        )
        result_map = (summary or {}).get("result", {})
        documents: list[dict[str, Any]] = []
        for pmc_id in id_list:
            item = result_map.get(str(pmc_id), {})
            if not item:
                continue
            documents.append(
                self.normalize_document(
                    {
                        "title": item.get("title"),
                        "abstract": item.get("sortfirstauthor"),
                        "source": self.name,
                        "source_id": f"PMC{pmc_id}",
                        "authors": [author.get("name") for author in item.get("authors", []) if isinstance(author, dict) and author.get("name")],
                        "published_date": item.get("pubdate"),
                        "url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/",
                        "journal": item.get("source"),
                        "metadata": {"pmc_id": pmc_id, "query": params["term"]},
                    }
                )
            )
        return documents


class ClinicalTrialsConnector(BaseConnector):
    """ClinicalTrials.gov REST API connector."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "clinicaltrials"
        self.base_url = self.config.get("base_url", "https://clinicaltrials.gov/api/v2/studies")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self._request_json(
            self.base_url,
            params={"query.term": query.strip() or "oncology", "pageSize": kwargs.get("max_results", 5)},
        )
        studies = (payload or {}).get("studies", [])
        documents: list[dict[str, Any]] = []
        for study in studies:
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            desc = protocol.get("descriptionModule", {})
            status_mod = protocol.get("statusModule", {})
            nct_id = ident.get("nctId")
            if not nct_id:
                continue
            documents.append(
                self.normalize_document(
                    {
                        "title": ident.get("briefTitle"),
                        "abstract": desc.get("briefSummary"),
                        "content": desc.get("detailedDescription"),
                        "source": self.name,
                        "source_id": nct_id,
                        "authors": [ident.get("organization", {}).get("fullName")] if ident.get("organization") else [],
                        "published_date": status_mod.get("startDateStruct", {}).get("date"),
                        "url": f"https://clinicaltrials.gov/study/{nct_id}",
                        "journal": "ClinicalTrials.gov",
                        "metadata": {
                            "overallStatus": status_mod.get("overallStatus"),
                            "studyType": protocol.get("designModule", {}).get("studyType"),
                            "query": query.strip() or "oncology",
                        },
                    }
                )
            )
        return documents


class AACRConnector(BaseConnector):
    """AACR search-page connector with documented publisher access limits."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "aacr"
        self.base_url = self.config.get("base_url", "https://aacrjournals.org").rstrip("/")

    def get_limitation(self) -> str | None:
        return "AACR abstracts and proceedings may require institutional access for full-text retrieval."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        search_url = _resolve_search_url(self.base_url, query, "/search-results?q={query}")
        return _fetch_search_result_pages(self, search_url, self.name, query, self.get_limitation(), kwargs.get("max_results", 5))


class ASCOConnector(BaseConnector):
    """ASCO search-page connector with documented publisher access limits."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "asco"
        self.base_url = self.config.get("base_url", "https://ascopubs.org").rstrip("/")

    def get_limitation(self) -> str | None:
        return "ASCO abstracts are available through publisher properties with access and reuse constraints."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        search_url = _resolve_search_url(self.base_url, query, "/action/doSearch?AllField={query}")
        return _fetch_search_result_pages(self, search_url, self.name, query, self.get_limitation(), kwargs.get("max_results", 5))


class SABCSConnector(BaseConnector):
    """SABCS conference-site connector with access limitations."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "sabcs"
        self.base_url = self.config.get("base_url", "https://www.sabcs.org").rstrip("/")

    def get_limitation(self) -> str | None:
        return "SABCS detailed abstracts may require conference registration or licensed access."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        search_url = _resolve_search_url(self.base_url, query, "/?s={query}")
        return _fetch_search_result_pages(self, search_url, self.name, query, self.get_limitation(), kwargs.get("max_results", 5))


class ESMOConnector(BaseConnector):
    """ESMO search-page connector with member-library limitations."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "esmo"
        self.base_url = self.config.get("base_url", "https://www.esmo.org").rstrip("/")

    def get_limitation(self) -> str | None:
        return "ESMO member content and some conference materials require authenticated access."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        search_url = _resolve_search_url(self.base_url, query, "/search?searchText={query}")
        return _fetch_search_result_pages(self, search_url, self.name, query, self.get_limitation(), kwargs.get("max_results", 5))


class BioRxivConnector(BaseConnector):
    """bioRxiv connector via the public bioRxiv API."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "biorxiv"
        self.base_url = self.config.get("base_url", "https://api.biorxiv.org/details/biorxiv").rstrip("/")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self._request_json(f"{self.base_url}/2024-01-01/2024-12-31/0/json")
        collection = (payload or {}).get("collection", [])
        documents: list[dict[str, Any]] = []
        for paper in collection:
            title = paper.get("title")
            abstract = paper.get("abstract")
            if not _matches_query(query, title, abstract):
                continue
            doi = paper.get("doi")
            documents.append(
                self.normalize_document(
                    {
                        "title": title,
                        "abstract": abstract,
                        "source": self.name,
                        "source_id": doi or paper.get("version"),
                        "authors": [part.strip() for part in str(paper.get("authors") or "").split(";") if part.strip()],
                        "published_date": paper.get("date"),
                        "doi": doi,
                        "url": f"https://www.biorxiv.org/content/{doi}" if doi else None,
                        "journal": "bioRxiv",
                        "metadata": {"query": query, "category": paper.get("category")},
                    }
                )
            )
            if len(documents) >= kwargs.get("max_results", 5):
                break
        return documents


class MedRxivConnector(BaseConnector):
    """medRxiv connector via the public medRxiv API."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "medrxiv"
        self.base_url = self.config.get("base_url", "https://api.biorxiv.org/details/medrxiv").rstrip("/")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self._request_json(f"{self.base_url}/2024-01-01/2024-12-31/0/json")
        collection = (payload or {}).get("collection", [])
        documents: list[dict[str, Any]] = []
        for paper in collection:
            title = paper.get("title")
            abstract = paper.get("abstract")
            if not _matches_query(query, title, abstract):
                continue
            doi = paper.get("doi")
            documents.append(
                self.normalize_document(
                    {
                        "title": title,
                        "abstract": abstract,
                        "source": self.name,
                        "source_id": doi or paper.get("version"),
                        "authors": [part.strip() for part in str(paper.get("authors") or "").split(";") if part.strip()],
                        "published_date": paper.get("date"),
                        "doi": doi,
                        "url": f"https://www.medrxiv.org/content/{doi}" if doi else None,
                        "journal": "medRxiv",
                        "metadata": {"query": query, "category": paper.get("category")},
                    }
                )
            )
            if len(documents) >= kwargs.get("max_results", 5):
                break
        return documents


class PatentsConnector(BaseConnector):
    """Patent connector with public-search fallback and documented API-key limits."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "patents"
        self.base_url = self.config.get("base_url", "https://api.patentsview.org/patents/query").rstrip("/")

    def get_limitation(self) -> str | None:
        return "High-volume or structured patent retrieval requires a licensed API such as USPTO or Lens credentials."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        max_results = kwargs.get("max_results", 5)
        query_text = query.strip() or "pharmaceutical"
        params = {
            "q": json.dumps({"_text_any": {"patent_title": query_text}}),
            "f": json.dumps([
                "patent_number",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
                "patent_current_assignee_organization",
                "inventor_last_name",
            ]),
            "o": json.dumps({"per_page": max_results, "page": 1}),
        }
        payload = self._request_json(self.base_url, params=params)
        patents = (payload or {}).get("patents", [])
        documents: list[dict[str, Any]] = []
        for patent in patents:
            patent_number = patent.get("patent_number")
            documents.append(
                self.normalize_document(
                    {
                        "title": patent.get("patent_title"),
                        "abstract": patent.get("patent_abstract"),
                        "content": patent.get("patent_abstract"),
                        "source": self.name,
                        "source_id": patent_number,
                        "authors": [patent.get("inventor_last_name")] if patent.get("inventor_last_name") else [],
                        "published_date": patent.get("patent_date"),
                        "url": f"https://patents.google.com/patent/{patent_number}" if patent_number else None,
                        "journal": "PatentsView",
                        "metadata": {"query": query, "patent_type": patent.get("patent_type")},
                    }
                )
            )
            if len(documents) >= max_results:
                break

        if documents:
            return documents

        search_url = f"https://patents.google.com/?q={urllib.parse.quote(query_text)}"
        html = self._request_text(search_url)
        if not html:
            return []
        return [
            self.normalize_document(
                {
                    "title": self._extract_html_title(html) or "Patent search results",
                    "abstract": self._html_to_text(html)[:1200],
                    "content": self._html_to_text(html)[:4000],
                    "source": self.name,
                    "source_id": search_url,
                    "url": search_url,
                    "journal": "Patent search",
                    "metadata": {"query": query, "limitation": self.get_limitation()},
                }
            )
        ]


class CompanyWebsiteConnector(BaseConnector):
    """Company website connector for configured press-release or IR URLs."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "company_websites"
        self.crawler_config = {
            "user_agent": self.user_agent,
            "timeout": float(self.config.get("crawler_timeout", self.timeout)),
            "rate_limit": float(self.config.get("crawler_rate_limit", 0.5)),
            "max_pages": int(self.config.get("crawler_max_pages", 5)),
            "max_depth": int(self.config.get("crawler_max_depth", 1)),
            "allowed_domains": self.config.get("allowed_domains", []),
        }

    def get_limitation(self) -> str | None:
        return "Company website ingestion requires explicitly configured public URLs; broad autonomous crawling is intentionally not enabled."

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        raw_urls = kwargs.get("urls") or self.config.get("urls") or []
        if isinstance(raw_urls, str):
            raw_urls = [raw_urls]

        crawler = WebCrawler(self.crawler_config)
        results = crawler.crawl([normalize_url(url) for url in raw_urls if normalize_url(url)])
        documents: list[dict[str, Any]] = []

        for result in results:
            if not result.success or not result.html:
                continue
            title = result.metadata.get("title") or self._extract_html_title(result.html) or result.url
            content = result.metadata.get("content") or self._html_to_text(result.html)
            if not _matches_query(query, title, content):
                continue
            documents.append(
                self.normalize_document(
                    {
                        "title": title,
                        "abstract": content[:1200],
                        "content": content[:4000],
                        "source": self.name,
                        "source_id": result.url,
                        "url": result.url,
                        "journal": "Company website",
                        "metadata": {"query": query, "limitation": self.get_limitation(), **result.metadata},
                    }
                )
            )
            if len(documents) >= kwargs.get("max_results", 5):
                break

        return documents
