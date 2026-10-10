from __future__ import annotations

import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import BinaryIO
from xml.etree import ElementTree as ET

from app.parsing.duplicates import duplicate_detector
from app.parsing.metrics import parser_metrics

try:
    import PyPDF2
except ImportError:  # pragma: no cover
    PyPDF2 = None

SUPPORTED_FORMATS = {"pdf", "xml", "html", "nxml", "jats"}


class DocumentParseError(Exception):
    pass


class DuplicateDocumentError(DocumentParseError):
    pass


@dataclass
class DocumentMetadata:
    title: str | None = None
    authors: list[str] | None = None
    affiliations: list[str] | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    sections: list[dict[str, str]] | None = None
    references: list[dict[str, str]] | None = None
    tables: list[dict[str, str]] | None = None
    figures: list[dict[str, str]] | None = None
    supplementary: list[str] | None = None

    def __post_init__(self) -> None:
        self.authors = self.authors or []
        self.affiliations = self.affiliations or []
        self.keywords = self.keywords or []
        self.sections = self.sections or []
        self.references = self.references or []
        self.tables = self.tables or []
        self.figures = self.figures or []
        self.supplementary = self.supplementary or []


def _validate_metadata(metadata: dict[str, object]) -> None:
    if not isinstance(metadata, dict):
        raise DocumentParseError("parsed metadata must be a JSON object")

    for key in ["title", "authors", "abstract"]:
        if (
            key in metadata
            and metadata[key] is not None
            and not isinstance(metadata[key], (str, list))
        ):
            raise DocumentParseError(f"invalid metadata type for {key}")

    if (
        "authors" in metadata
        and metadata["authors"] is not None
        and not isinstance(metadata["authors"], list)
    ):
        raise DocumentParseError("authors must be a list")

    if (
        "keywords" in metadata
        and metadata["keywords"] is not None
        and not isinstance(metadata["keywords"], list)
    ):
        raise DocumentParseError("keywords must be a list")

    if (
        "references" in metadata
        and metadata["references"] is not None
        and not isinstance(metadata["references"], list)
    ):
        raise DocumentParseError("references must be a list")

    if (
        "tables" in metadata
        and metadata["tables"] is not None
        and not isinstance(metadata["tables"], list)
    ):
        raise DocumentParseError("tables must be a list")

    if (
        "figures" in metadata
        and metadata["figures"] is not None
        and not isinstance(metadata["figures"], list)
    ):
        raise DocumentParseError("figures must be a list")


def _parse_xml_metadata(root: ET.Element) -> dict[str, object]:
    metadata: dict[str, object] = {}

    title = root.findtext(".//article-title") or root.findtext(".//title")
    metadata["title"] = title.strip() if title else None

    authors: list[str] = []
    affiliations: list[str] = []
    for contrib in root.findall(".//contrib"):
        surname = contrib.findtext(".//surname")
        given_names = contrib.findtext(".//given-names")
        name_parts = [part for part in [given_names, surname] if part]
        if name_parts:
            authors.append(" ".join(name_parts).strip())

    for aff in root.findall(".//aff"):
        affiliation = ET.tostring(aff, encoding="unicode", method="text").strip()
        if affiliation:
            affiliations.append(affiliation)

    metadata["authors"] = authors
    metadata["affiliations"] = affiliations

    metadata["doi"] = root.findtext(".//article-id[@pub-id-type='doi']")
    metadata["pmid"] = root.findtext(".//article-id[@pub-id-type='pmid']")
    metadata["pmcid"] = root.findtext(".//article-id[@pub-id-type='pmcid']")

    abstract = root.findtext(".//abstract")
    metadata["abstract"] = abstract.strip() if abstract else None

    keywords: list[str] = []
    for kwd in root.findall(".//kwd"):
        if kwd.text:
            keywords.append(kwd.text.strip())
    metadata["keywords"] = keywords

    sections: list[dict[str, str]] = []
    for sec in root.findall(".//sec"):
        title = sec.findtext("title")
        body_text = ET.tostring(sec, encoding="unicode", method="text").strip()
        if title or body_text:
            sections.append(
                {"title": title.strip() if title else "", "text": body_text}
            )
    metadata["sections"] = sections

    references: list[dict[str, str]] = []
    for ref in root.findall(".//ref"):
        citation = ref.findtext(".//mixed-citation") or ET.tostring(
            ref, encoding="unicode", method="text"
        )
        references.append({"citation": citation.strip()})
    metadata["references"] = references

    tables: list[dict[str, str]] = []
    for table in root.findall(".//table"):
        label = table.findtext(".//label")
        caption = table.findtext(".//caption")
        tables.append(
            {
                "label": label.strip() if label else "",
                "caption": caption.strip() if caption else "",
            }
        )
    metadata["tables"] = tables

    figures: list[dict[str, str]] = []
    for fig in root.findall(".//fig"):
        label = fig.findtext(".//label")
        caption = fig.findtext(".//caption")
        figures.append(
            {
                "label": label.strip() if label else "",
                "caption": caption.strip() if caption else "",
            }
        )
    metadata["figures"] = figures

    supplementary: list[str] = []
    for sup in root.findall(".//supplementary-material"):
        if sup.text:
            supplementary.append(sup.text.strip())
    metadata["supplementary"] = supplementary

    return metadata


def _parse_html_metadata(html_text: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    parser = _HTMLMetadataParser()
    parser.feed(html_text)
    metadata["title"] = parser.metadata.get("title")
    metadata["authors"] = parser.metadata.get("authors", [])
    metadata["affiliations"] = []
    metadata["doi"] = parser.metadata.get("citation_doi")
    metadata["pmid"] = parser.metadata.get("citation_pmid")
    metadata["pmcid"] = parser.metadata.get("citation_pmcid")
    metadata["abstract"] = parser.metadata.get("description")
    metadata["keywords"] = parser.metadata.get("keywords", [])
    metadata["sections"] = parser.sections
    metadata["references"] = parser.references
    metadata["tables"] = parser.tables
    metadata["figures"] = parser.figures
    metadata["supplementary"] = []
    return metadata


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, object] = {}
        self.sections: list[dict[str, str]] = []
        self.references: list[dict[str, str]] = []
        self.tables: list[dict[str, str]] = []
        self.figures: list[dict[str, str]] = []
        self._current_tag: str | None = None
        self._current_attrs: dict[str, str] = {}
        self._current_data: list[str] = []
        self._heading_text: str | None = None
        self._collect_heading: bool = False
        self._section_texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value for name, value in attrs if value is not None}
        self._current_tag = tag
        self._current_attrs = attrs_dict

        if tag == "meta" and "name" in attrs_dict and "content" in attrs_dict:
            name = attrs_dict["name"].lower()
            content = attrs_dict["content"].strip()
            if name == "keywords":
                keywords = self.metadata.setdefault("keywords", [])
                if isinstance(keywords, list):
                    keywords.extend(
                        [kw.strip() for kw in content.split(",") if kw.strip()]
                    )
            elif name in {
                "author",
                "citation_doi",
                "citation_pmid",
                "citation_pmcid",
                "description",
                "title",
            }:
                if name == "author":
                    authors = self.metadata.setdefault("authors", [])
                    if isinstance(authors, list):
                        authors.append(content)
                else:
                    self.metadata[name] = content

        if tag == "title":
            self._current_tag = "title"
            self._current_data = []

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_text = ""
            self._collect_heading = True
            self._section_texts = []

        if tag == "a" and "href" in attrs_dict:
            self._current_data = []

        if tag in {"table", "figure"}:
            self._current_data = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._current_tag == "title":
            self._current_tag = None

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._collect_heading:
            self._collect_heading = False
            if self._heading_text is not None:
                self.sections.append(
                    {
                        "title": self._heading_text.strip(),
                        "text": "".join(self._section_texts).strip(),
                    }
                )
            self._section_texts = []
            self._heading_text = None

        if tag == "a" and self._current_tag == "a" and self._current_attrs.get("href"):
            text = "".join(self._current_data).strip()
            self.references.append({"href": self._current_attrs["href"], "text": text})
            self._current_data = []

        if tag == "table" and self._current_tag == "table":
            self.tables.append({"caption": ""})
            self._current_data = []

        if tag == "figure" and self._current_tag == "figure":
            self.figures.append({"caption": ""})
            self._current_data = []

        super().handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._current_tag == "title":
            title = self.metadata.get("title", "")
            if not isinstance(title, str):
                title = ""
            self.metadata["title"] = title + data

        if self._collect_heading and self._heading_text is not None:
            self._heading_text += data
            self._section_texts.append(data)

        if self._current_tag in {"a", "table", "figure"}:
            self._current_data.append(data)

    def feed(self, data: str) -> None:
        super().feed(data)


def _parse_pdf_metadata(stream: BinaryIO) -> dict[str, object]:
    if PyPDF2 is None:
        raise DocumentParseError("PDF parser dependency is missing")

    try:
        reader = PyPDF2.PdfReader(stream)
    except Exception as exc:
        parser_metrics.increment("parser.parse_errors")
        raise DocumentParseError("failed to parse PDF document") from exc

    info = reader.metadata
    metadata: dict[str, object] = {
        "title": None,
        "authors": [],
        "affiliations": [],
        "doi": None,
        "pmid": None,
        "pmcid": None,
        "abstract": None,
        "keywords": [],
        "sections": [],
        "references": [],
        "tables": [],
        "figures": [],
        "supplementary": [],
    }

    if info is not None:
        metadata["title"] = getattr(info, "/Title", None) or getattr(
            info, "title", None
        )
        author = getattr(info, "/Author", None) or getattr(info, "author", None)
        if author:
            metadata["authors"] = [author]

    try:
        pages = list(reader.pages)
        if pages:
            text = pages[0].extract_text() or ""
            snippet = text.strip().split("\n\n", 1)[0]
            metadata["abstract"] = snippet if snippet else None
    except (AttributeError, IndexError, OSError, ValueError):
        metadata["abstract"] = None

    return metadata


def _read_as_text(stream: BinaryIO) -> str:
    current_position = None
    try:
        current_position = stream.tell()
    except (AttributeError, OSError):
        pass

    content = stream.read()
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception as exc:
            raise DocumentParseError("failed to decode document content") from exc
    elif isinstance(content, str):
        text = content
    else:
        raise DocumentParseError("unsupported stream content type")

    try:
        stream.seek(current_position or 0)
    except (AttributeError, OSError):
        pass
    return text


def _fingerprint_stream(stream: BinaryIO) -> str:
    current_position = None
    try:
        current_position = stream.tell()
    except (AttributeError, OSError):
        pass

    hasher = hashlib.sha256()
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", errors="ignore")
        hasher.update(chunk)

    try:
        stream.seek(current_position or 0)
    except (AttributeError, OSError):
        pass

    return hasher.hexdigest()


def parse_document(format_name: str, stream: BinaryIO) -> dict[str, object]:
    lowercase_format = format_name.strip().lower()
    if lowercase_format not in SUPPORTED_FORMATS:
        raise DocumentParseError(f"unsupported document format: {format_name}")

    if duplicate_detector.register(stream):
        parser_metrics.increment("parser.duplicate_documents")
        raise DuplicateDocumentError("duplicate document detected")

    parser_metrics.increment("parser.documents_parsed")

    if lowercase_format == "pdf":
        metadata = _parse_pdf_metadata(stream)
    else:
        html_text = _read_as_text(stream)

        if lowercase_format in {"xml", "nxml", "jats"}:
            try:
                root = ET.fromstring(html_text)
                metadata = _parse_xml_metadata(root)
            except ET.ParseError:
                parser_metrics.increment("parser.parse_errors")
                raise DocumentParseError("failed to parse XML document")
        else:
            try:
                metadata = _parse_html_metadata(html_text)
            except (TypeError, ValueError, OSError):
                parser_metrics.increment("parser.parse_errors")
                metadata = {
                    "title": None,
                    "authors": [],
                    "affiliations": [],
                    "doi": None,
                    "pmid": None,
                    "pmcid": None,
                    "abstract": None,
                    "keywords": [],
                    "sections": [],
                    "references": [],
                    "tables": [],
                    "figures": [],
                    "supplementary": [],
                }

    try:
        _validate_metadata(metadata)
    except DocumentParseError:
        parser_metrics.increment("parser.validation_failures")
        raise

    parser_metrics.increment("parser.documents_validated")
    return metadata
