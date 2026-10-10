from __future__ import annotations

import json
import hashlib
import logging
import re
import threading
import time
import urllib.parse
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

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
_PUBMED_RATE_LOCK = threading.Lock()
_PUBMED_LAST_REQUEST = 0.0
_FDA_RATE_LOCK = threading.Lock()
_FDA_LAST_REQUEST = 0.0


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
    """PubMed connector using NCBI E-utilities ESearch and EFetch endpoints."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "pubmed"
        self.base_url = self.config.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils").rstrip("/")
        self.api_key = self.config.get("api_key")
        self.email = self.config.get("email")
        self.tool = self.config.get("tool", "AI-RxOS")
        self.requests_per_second = float(self.config.get("requests_per_second", 3.0))
        self.last_total_count = 0
        self.last_malformed_records: list[dict[str, Any]] = []
        if self.requests_per_second < 0:
            raise ValueError("PubMed requests_per_second must be non-negative")

    def _request(self, method: str, url: str, **kwargs: Any):
        global _PUBMED_LAST_REQUEST
        if self.requests_per_second > 0:
            with _PUBMED_RATE_LOCK:
                now = time.monotonic()
                interval = 1 / self.requests_per_second
                delay = max(0.0, interval - (now - _PUBMED_LAST_REQUEST)) if _PUBMED_LAST_REQUEST else 0.0
                if delay:
                    time.sleep(delay)
                    now = time.monotonic()
                _PUBMED_LAST_REQUEST = now
        return super()._request(method, url, **kwargs)

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        records, _ = self.fetch_page(
            query,
            page_token=kwargs.get("page_token"),
            page_size=int(kwargs.get("page_size", kwargs.get("max_results", 5))),
        )
        return records

    def fetch_page(
        self,
        query: str,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], str | None]:
        offset = int(page_token or 0)
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query.strip(),
            "retmode": "json",
            "retmax": page_size,
            "retstart": offset,
            "sort": "pub date",
            "tool": self.tool,
        }
        if not params["term"]:
            raise ValueError("PubMed query must not be empty")
        if page_size < 1 or page_size > 500:
            raise ValueError("PubMed page_size must be between 1 and 500")
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        search_response = self._request("GET", f"{self.base_url}/esearch.fcgi", params=params)
        try:
            search = search_response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("NCBI returned malformed PubMed search JSON") from exc
        if not isinstance(search, dict):
            raise ValueError("NCBI returned a non-object PubMed search response")
        id_list = (search or {}).get("esearchresult", {}).get("idlist", [])
        self.last_total_count = int((search or {}).get("esearchresult", {}).get("count", len(id_list)))
        self.last_malformed_records = []
        if not id_list:
            return [], None

        fetch_params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(str(pmid) for pmid in id_list),
            "retmode": "xml",
            "tool": self.tool,
        }
        if self.email:
            fetch_params["email"] = self.email
        if self.api_key:
            fetch_params["api_key"] = self.api_key
        response = self._request(
            "GET", f"{self.base_url}/efetch.fcgi", params=fetch_params
        )
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise ValueError("NCBI returned malformed PubMed XML") from exc

        documents: list[dict[str, Any]] = []
        for article_set in root.findall(".//PubmedArticle"):
            normalized = self._normalize_article(article_set, query)
            if normalized is not None:
                documents.append(normalized)
            else:
                self.last_malformed_records.append({
                    "pmid": article_set.findtext(".//PMID"),
                    "raw_xml": ET.tostring(article_set, encoding="unicode"),
                })

        count = self.last_total_count
        next_offset = offset + len(id_list)
        next_page_token = str(next_offset) if next_offset < count else None
        return documents, next_page_token

    def _normalize_article(self, article_set: ET.Element, query: str) -> dict[str, Any] | None:
        citation = article_set.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        pmid = citation.findtext("PMID") if citation is not None else None
        if article is None or not pmid:
            logger.warning("Skipping PubMed record without article or PMID")
            return None

        def text(element: ET.Element | None) -> str | None:
            if element is None:
                return None
            value = "".join(element.itertext()).strip()
            return value or None

        title = text(article.find("ArticleTitle"))
        if not title:
            logger.warning("Skipping PubMed record without source title", extra={"pmid": str(pmid)})
            return None

        abstract_sections = [
            {"label": section.get("Label"), "nlm_category": section.get("NlmCategory"), "text": text(section)}
            for section in article.findall(".//Abstract/AbstractText")
        ]
        abstract = "\n".join(
            f"{section['label']}: {section['text']}" if section["label"] else section["text"] or ""
            for section in abstract_sections
        ).strip() or None

        authors: list[dict[str, Any]] = []
        affiliations: list[str] = []
        for author in article.findall(".//AuthorList/Author"):
            author_name = {
                key: text(author.find(key))
                for key in ("ForeName", "Initials", "LastName", "CollectiveName")
            }
            identifiers = [
                {"source": item.get("Source"), "value": text(item)}
                for item in author.findall("Identifier")
            ]
            author_affiliations = [
                value for value in (text(item) for item in author.findall(".//AffiliationInfo/Affiliation")) if value
            ]
            affiliations.extend(author_affiliations)
            authors.append({**author_name, "identifiers": identifiers, "affiliations": author_affiliations})

        pub_date = article.find(".//JournalIssue/PubDate")
        publication_date_parts = []
        if pub_date is not None:
            for field in ("Year", "Month", "Day", "Season", "MedlineDate"):
                value = text(pub_date.find(field))
                if value:
                    publication_date_parts.append(value)
        publication_date = " ".join(publication_date_parts) or None
        article_dates = []
        for article_date in article.findall(".//ArticleDate"):
            parts = []
            for field in ("Year", "Month", "Day"):
                value = text(article_date.find(field))
                if value:
                    parts.append(value)
            article_dates.append({
                "date_type": article_date.get("DateType"),
                "source_precision": " ".join(parts) or None,
            })

        identifiers: dict[str, str] = {"pmid": str(pmid)}
        pubmed_data = article_set.find("PubmedData")
        if pubmed_data is not None:
            for item in pubmed_data.findall(".//ArticleId"):
                id_type = (item.get("IdType") or "").lower()
                value = text(item)
                if id_type and value:
                    identifiers[id_type] = value
        doi = identifiers.get("doi")
        pmcid = identifiers.get("pmc")

        journal = article.find("Journal")
        publication_types = [value for value in (text(item) for item in article.findall(".//PublicationType")) if value]
        mesh_terms = [
            {
                "descriptor": text(item.find("DescriptorName")),
                "major_topic": item.find("DescriptorName").get("MajorTopicYN") if item.find("DescriptorName") is not None else None,
                "qualifiers": [text(qualifier) for qualifier in item.findall("QualifierName")],
            }
            for item in article.findall(".//MeshHeading")
        ]
        keywords = [value for value in (text(item) for item in article.findall(".//Keyword")) if value]
        chemicals = [
            {
                "name": text(item.find("NameOfSubstance")),
                "registry_number": text(item.find("RegistryNumber")),
                "mesh_ui": item.find("NameOfSubstance").get("UI") if item.find("NameOfSubstance") is not None else None,
            }
            for item in article.findall(".//Chemical")
        ]
        grants = [
            {
                "grant_id": text(item.find("GrantID")),
                "acronym": text(item.find("Acronym")),
                "agency": text(item.find("Agency")),
                "country": text(item.find("Country")),
            }
            for item in article.findall(".//Grant")
        ]
        source_metadata = {
            "pmid": str(pmid),
            "pmcid": pmcid,
            "doi": doi,
            "article_ids": identifiers,
            "authors": authors,
            "journal": {
                "title": text(journal.find("Title")) if journal is not None else None,
                "iso_abbreviation": text(journal.find("ISOAbbreviation")) if journal is not None else None,
                "issn": text(journal.find("ISSN")) if journal is not None else None,
            },
            "abstract_sections": abstract_sections,
            "publication_date_source": publication_date,
            "article_dates": article_dates,
            "publication_types": publication_types,
            "languages": [value for value in (text(item) for item in article.findall("Language")) if value],
            "affiliations": sorted(set(affiliations)),
            "mesh_terms": mesh_terms,
            "keywords": keywords,
            "chemicals": chemicals,
            "journal_issue": {
                "volume": text(journal.find("JournalIssue/Volume")) if journal is not None else None,
                "issue": text(journal.find("JournalIssue/Issue")) if journal is not None else None,
                "pages": text(article.find("Pagination/MedlinePgn")),
            },
            "grants": grants,
            "raw_xml": ET.tostring(article_set, encoding="unicode"),
            "parser": "pubmed-efetch-xml-v1",
            "query": query,
        }
        source_metadata["content_hash"] = hashlib.sha256(
            source_metadata["raw_xml"].encode("utf-8")
        ).hexdigest()
        normalized = self.normalize_document(
            {
                "title": title,
                "abstract": abstract,
                "content": abstract,
                "source": self.name,
                "source_id": f"PMID:{pmid}",
                "pmid": str(pmid),
                "pmcid": pmcid,
                "authors": authors,
                "publication_date": publication_date,
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "journal": source_metadata["journal"]["title"],
                "metadata": source_metadata,
            }
        )
        normalized.update({
            "abstract": abstract,
            "content": abstract,
            "pmid": str(pmid),
            "pmcid": pmcid,
            "publication_date": publication_date,
        })
        return normalized


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
    """ClinicalTrials.gov v2 API adapter with lossless study normalization."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "clinicaltrials"
        self.base_url = self.config.get(
            "base_url", "https://clinicaltrials.gov/api/v2/studies"
        ).rstrip("/")
        self.requests_per_second = float(self.config.get("requests_per_second", 2.0))
        self.last_malformed_records: list[dict[str, Any]] = []
        self.last_total_count = 0
        self._last_request_at: float | None = None
        self._rate_lock = threading.Lock()
        if self.requests_per_second < 0:
            raise ValueError("ClinicalTrials requests_per_second must be non-negative")

    def _request(self, method: str, url: str, **kwargs: Any):
        for attempt in range(self.max_retries + 1):
            if self.requests_per_second > 0:
                with self._rate_lock:
                    now = time.monotonic()
                    interval = 1.0 / self.requests_per_second
                    if self._last_request_at is not None:
                        delay = max(0.0, interval - (now - self._last_request_at))
                        if delay:
                            time.sleep(delay)
                    self._last_request_at = time.monotonic()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code in {429, 500, 502, 503, 504}
                if not retryable or attempt >= self.max_retries:
                    raise
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
            time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError("ClinicalTrials.gov request exhausted retries")

    @staticmethod
    def _date_text(value: Any) -> str | None:
        if isinstance(value, dict):
            value = value.get("date")
        return str(value).strip() if value not in (None, "") else None

    @staticmethod
    def _items(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _study_modules(study: dict[str, Any]) -> dict[str, Any]:
        protocol = study.get("protocolSection")
        if not isinstance(protocol, dict):
            raise ValueError("study is missing protocolSection")
        return protocol

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        documents, _ = self.fetch_page(
            query,
            page_token=kwargs.get("page_token"),
            page_size=int(kwargs.get("page_size", kwargs.get("max_results", 5))),
        )
        return documents

    def fetch_page(
        self,
        query: str,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], str | None]:
        query = query.strip()
        if not query:
            raise ValueError("ClinicalTrials.gov query must not be empty")
        if page_size < 1 or page_size > 1000:
            raise ValueError("ClinicalTrials.gov page_size must be between 1 and 1000")

        params: dict[str, Any] = {"pageSize": page_size, "format": "json"}
        if re.fullmatch(r"NCT\d{8}", query, flags=re.IGNORECASE):
            params["query.id"] = query.upper()
        else:
            params["query.term"] = query
        if page_token:
            params["pageToken"] = page_token

        response = self._request("GET", self.base_url, params=params)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("ClinicalTrials.gov returned malformed JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
            raise ValueError("ClinicalTrials.gov response must contain a studies array")

        total_count = payload.get("totalCount")
        self.last_total_count = total_count if isinstance(total_count, int) else 0
        self.last_malformed_records = []
        documents: list[dict[str, Any]] = []
        for index, study in enumerate(payload["studies"]):
            try:
                if not isinstance(study, dict):
                    raise ValueError("study item must be an object")
                documents.append(self._normalize_study(study, query))
            except (TypeError, ValueError, AttributeError) as exc:
                raw_id = None
                if isinstance(study, dict):
                    protocol = study.get("protocolSection")
                    identity = protocol.get("identificationModule") if isinstance(protocol, dict) else None
                    raw_id = identity.get("nctId") if isinstance(identity, dict) else None
                self.last_malformed_records.append({
                    "source_id": raw_id,
                    "page_token": page_token,
                    "record_index": index,
                    "error_message": str(exc),
                    "raw_payload": study,
                })
        next_page_token = payload.get("nextPageToken")
        if next_page_token is not None and not isinstance(next_page_token, str):
            raise ValueError("ClinicalTrials.gov nextPageToken must be a string")
        return documents, next_page_token

    def _normalize_study(self, study: dict[str, Any], query: str) -> dict[str, Any]:
        protocol = self._study_modules(study)
        identification = protocol.get("identificationModule") or {}
        status = protocol.get("statusModule") or {}
        design = protocol.get("designModule") or {}
        sponsor = protocol.get("sponsorCollaboratorsModule") or {}
        interventions_module = protocol.get("armsInterventionsModule") or {}
        outcomes = protocol.get("outcomesModule") or {}
        eligibility = protocol.get("eligibilityModule") or {}
        contacts_locations = protocol.get("contactsLocationsModule") or {}
        enrollment_info = design.get("enrollmentInfo") or {}
        results = study.get("resultsSection") or {}
        nct_id = str(identification.get("nctId") or "").strip().upper()
        if not re.fullmatch(r"NCT\d{8}", nct_id):
            raise ValueError("study is missing a valid NCT identifier")
        organizations = identification.get("organization") or {}
        lead_sponsor = sponsor.get("leadSponsor") or {}
        interventions = self._items(interventions_module.get("interventions"))
        arms = self._items(interventions_module.get("armGroups"))
        source_metadata = {
            "parser": "clinicaltrials-api-v2-v1",
            "query": query,
            "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
            "api_endpoint": self.base_url,
        }
        content_hash = hashlib.sha256(
            json.dumps(study, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        source_metadata["content_hash"] = content_hash
        normalized = {
            "nct_id": nct_id,
            "official_title": identification.get("officialTitle"),
            "brief_title": identification.get("briefTitle"),
            "acronym": identification.get("acronym"),
            "organization": organizations,
            "secondary_identifiers": identification.get("secondaryIdInfos") or [],
            "org_study_id": (identification.get("orgStudyIdInfo") or {}).get("id"),
            "references": (protocol.get("referencesModule") or {}).get("references", []),
            "results": results,
            "overall_status": status.get("overallStatus"),
            "status_verified_date": self._date_text(status.get("statusVerifiedDateStruct")),
            "why_stopped": status.get("whyStopped"),
            "study_type": design.get("studyType"),
            "phases": design.get("phases") or [],
            "design": design,
            "enrollment": enrollment_info,
            "lead_sponsor": lead_sponsor,
            "collaborators": self._items(sponsor.get("collaborators")),
            "conditions": self._items((protocol.get("conditionsModule") or {}).get("conditions")),
            "keywords": self._items((protocol.get("conditionsModule") or {}).get("keywords")),
            "interventions": interventions,
            "arms": arms,
            "primary_outcomes": self._items(outcomes.get("primaryOutcomes")),
            "secondary_outcomes": self._items(outcomes.get("secondaryOutcomes")),
            "eligibility": eligibility,
            "locations": self._items(contacts_locations.get("locations")),
            "start_date": self._date_text(status.get("startDateStruct")),
            "primary_completion_date": self._date_text(status.get("primaryCompletionDateStruct")),
            "completion_date": self._date_text(status.get("completionDateStruct")),
            "study_first_submitted_date": self._date_text(status.get("studyFirstSubmitDate")),
            "study_first_posted_date": self._date_text(status.get("studyFirstPostDateStruct")),
            "results_first_submitted_date": self._date_text(status.get("resultsFirstSubmitDate")),
            "results_first_posted_date": self._date_text(status.get("resultsFirstPostDateStruct")),
            "last_update_submitted_date": self._date_text(status.get("lastUpdateSubmitDate")),
            "last_update_posted_date": self._date_text(status.get("lastUpdatePostDateStruct")),
            "source_metadata": source_metadata,
        }
        return {
            "source": self.name,
            "source_id": nct_id,
            "nct_id": nct_id,
            "title": normalized["official_title"] or normalized["brief_title"] or nct_id,
            "abstract": (protocol.get("descriptionModule") or {}).get("briefSummary"),
            "content": (protocol.get("descriptionModule") or {}).get("detailedDescription"),
            "authors": [],
            "published_date": None,
            "doi": None,
            "url": source_metadata["source_url"],
            "journal": "ClinicalTrials.gov",
            "metadata": normalized,
            "raw_payload": study,
            "content_hash": content_hash,
        }


class FDARegulatoryConnector(BaseConnector):
    """Official openFDA Drugs@FDA submissions adapter."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.name = "regulatory"
        self.base_url = self.config.get(
            "base_url", "https://api.fda.gov/drug/drugsfda.json"
        ).rstrip("/")
        self.requests_per_second = float(self.config.get("requests_per_second", 1.0))
        self.last_malformed_records: list[dict[str, Any]] = []
        self.last_total_count = 0
        self.last_offset_limit_reached = False
        if self.requests_per_second < 0:
            raise ValueError("FDA requests_per_second must be non-negative")

    def _request_page(self, params: dict[str, Any]) -> httpx.Response:
        global _FDA_LAST_REQUEST
        for attempt in range(self.max_retries + 1):
            if self.requests_per_second > 0:
                with _FDA_RATE_LOCK:
                    now = time.monotonic()
                    interval = 1.0 / self.requests_per_second
                    if _FDA_LAST_REQUEST:
                        delay = max(0.0, interval - (now - _FDA_LAST_REQUEST))
                        if delay:
                            time.sleep(delay)
                    _FDA_LAST_REQUEST = time.monotonic()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(
                        self.base_url,
                        params=params,
                        headers={"User-Agent": self.user_agent},
                    )
                if response.status_code == 404:
                    try:
                        error = response.json().get("error", {})
                    except (ValueError, AttributeError):
                        error = {}
                    if (
                        isinstance(error, dict)
                        and error.get("code") == "NOT_FOUND"
                        and error.get("message") == "No matches found!"
                    ):
                        return response
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                if attempt >= self.max_retries:
                    raise
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
            time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError("FDA Drugs@FDA request exhausted retries")

    def fetch(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        records, _ = self.fetch_page(
            query,
            offset=int(kwargs.get("offset", 0)),
            page_size=int(kwargs.get("page_size", kwargs.get("max_results", 5))),
        )
        return records

    def fetch_page(
        self,
        query: str,
        *,
        offset: int = 0,
        page_size: int = 100,
    ) -> tuple[list[dict[str, Any]], int | None]:
        query = query.strip()
        if not query:
            raise ValueError("FDA openFDA search query must not be empty")
        if offset < 0 or offset > 25_000:
            raise ValueError("FDA openFDA offset must be between 0 and 25000")
        if page_size < 1 or page_size > 1000:
            raise ValueError("FDA openFDA page_size must be between 1 and 1000")
        self.last_offset_limit_reached = False
        params: dict[str, Any] = {"limit": page_size, "skip": offset}
        params["search"] = query

        response = self._request_page(params)
        if response.status_code == 404:
            self.last_total_count = 0
            self.last_malformed_records = []
            return [], None
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("FDA Drugs@FDA returned malformed JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("FDA Drugs@FDA response must contain a results array")
        metadata = payload.get("meta")
        results_meta = metadata.get("results") if isinstance(metadata, dict) else None
        total = results_meta.get("total") if isinstance(results_meta, dict) else None
        if not isinstance(total, int) or total < 0:
            raise ValueError("FDA Drugs@FDA response is missing a valid result total")
        self.last_total_count = total
        self.last_offset_limit_reached = False
        self.last_malformed_records = []
        records: list[dict[str, Any]] = []
        for index, application in enumerate(payload["results"]):
            try:
                if not isinstance(application, dict):
                    raise ValueError("FDA application record must be an object")
                submissions = application.get("submissions")
                if not isinstance(submissions, list):
                    raise ValueError("FDA application record is missing submissions")
                for submission_index, submission in enumerate(submissions):
                    if not isinstance(submission, dict):
                        self.last_malformed_records.append({
                            "source_id": application.get("application_number"),
                            "record_index": index,
                            "submission_index": submission_index,
                            "error_message": "FDA submission must be an object",
                            "raw_payload": submission,
                        })
                        continue
                    try:
                        records.append(self._normalize_submission(application, submission, query))
                    except (TypeError, ValueError, AttributeError) as exc:
                        self.last_malformed_records.append({
                            "source_id": application.get("application_number"),
                            "record_index": index,
                            "submission_index": submission_index,
                            "error_message": str(exc),
                            "raw_payload": submission,
                        })
            except (TypeError, ValueError, AttributeError) as exc:
                raw_id = application.get("application_number") if isinstance(application, dict) else None
                self.last_malformed_records.append({
                    "source_id": raw_id,
                    "record_index": index,
                    "error_message": str(exc),
                    "raw_payload": application,
                })
        next_offset = offset + len(payload["results"])
        next_page = next_offset if next_offset < total else None
        if next_page is not None and next_page > 25_000:
            self.last_offset_limit_reached = True
            next_page = None
        return records, next_page

    def _normalize_submission(
        self,
        application: dict[str, Any],
        submission: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        application_number = str(application.get("application_number") or "").strip().upper()
        submission_number = str(submission.get("submission_number") or "").strip().upper()
        if not application_number or not submission_number:
            raise ValueError("FDA application and submission numbers are required")
        submission_status = str(submission.get("submission_status") or "").strip().upper()
        status_date = str(submission.get("submission_status_date") or "").strip()
        status_to_type = {
            "AP": "approval",
            "TA": "tentative_approval",
            "CR": "complete_response",
        }
        event_type = status_to_type.get(submission_status, "regulatory_submission")
        event_id = f"FDA:{application_number}:{submission_number}"
        products = []
        for product in application.get("products") or []:
            if not isinstance(product, dict):
                continue
            products.append({
                "product_number": product.get("product_number"),
                "brand_name": product.get("brand_name"),
                "reference_drug": product.get("reference_drug"),
                "marketing_status": product.get("marketing_status"),
                "active_ingredients": product.get("active_ingredients") or [],
                "te_code": product.get("te_code"),
            })
        raw_payload = {
            "application": {
                key: value for key, value in application.items() if key != "submissions"
            },
            "submission": submission,
        }
        content_hash = hashlib.sha256(
            json.dumps(
                raw_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8")
        ).hexdigest()
        application_digits = re.sub(r"[^0-9]", "", application_number)
        source_url = (
            "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?"
            f"event=overview.process&ApplNo={urllib.parse.quote(application_digits)}"
        )
        metadata = {
            "regulator": "U.S. Food and Drug Administration",
            "jurisdiction": "US",
            "event_id": event_id,
            "event_type": event_type,
            "event_status": submission_status or None,
            "application_number": application_number,
            "application_type": application.get("application_type"),
            "sponsor_name": application.get("sponsor_name"),
            "submission_number": submission_number,
            "submission_type": submission.get("submission_type"),
            "submission_status": submission_status or None,
            "submission_status_date_source": status_date or None,
            "submission_class_code": submission.get("submission_class_code"),
            "submission_class_code_description": submission.get("submission_class_code_description"),
            "review_priority": submission.get("review_priority"),
            "products": products,
            "source_metadata": {
                "source": "openFDA Drugs@FDA",
                "api_endpoint": self.base_url,
                "source_url": source_url,
                "query": query,
                "parser": "openfda-drugsfda-v1",
                "raw_source_status": submission.get("submission_status"),
                "raw_source_type": submission.get("submission_type"),
                "retrieved_at": None,
            },
        }
        return {
            "source": self.name,
            "source_id": event_id,
            "title": (
                f"{products[0]['brand_name']} {event_type.replace('_', ' ')} "
                f"({application_number}, submission {submission_number})"
                if products and products[0].get("brand_name")
                else f"{application_number} {event_type.replace('_', ' ')} "
                f"(submission {submission_number})"
            ),
            "abstract": None,
            "url": source_url,
            "metadata": metadata,
            "raw_payload": raw_payload,
            "content_hash": content_hash,
        }


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
