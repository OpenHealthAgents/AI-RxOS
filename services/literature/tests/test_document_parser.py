import io

import pytest

from app.parsing import parse_document, parser_metrics, DuplicateDocumentError


def test_parse_xml_document_metadata():
    xml = """
    <article>
      <front>
        <article-meta>
          <title-group><article-title>Test Title</article-title></title-group>
          <contrib-group>
            <contrib><name><surname>Doe</surname><given-names>Jane</given-names></name></contrib>
          </contrib-group>
          <article-id pub-id-type="doi">10.1000/test</article-id>
          <abstract>Test abstract content.</abstract>
          <kwd-group><kwd>keyword1</kwd><kwd>keyword2</kwd></kwd-group>
        </article-meta>
      </front>
    </article>
    """
    stream = io.StringIO(xml)
    metadata = parse_document("xml", stream)

    assert metadata["title"] == "Test Title"
    assert metadata["doi"] == "10.1000/test"
    assert metadata["abstract"] == "Test abstract content."
    assert metadata["authors"] == ["Jane Doe"]
    assert metadata["keywords"] == ["keyword1", "keyword2"]


def test_parse_html_document_metadata():
    html = """
    <html>
      <head>
        <title>HTML Title</title>
        <meta name="author" content="Alice Smith" />
        <meta name="citation_doi" content="10.2000/html" />
        <meta name="keywords" content="testing, parser" />
      </head>
      <body>
        <h1>Section 1</h1>
        <p>Some text.</p>
        <a href="https://example.com">Reference</a>
      </body>
    </html>
    """
    stream = io.StringIO(html)
    metadata = parse_document("html", stream)

    assert metadata["title"] == "HTML Title"
    assert metadata["doi"] == "10.2000/html"
    assert metadata["authors"] == ["Alice Smith"]
    assert metadata["keywords"] == ["testing", "parser"]
    assert metadata["references"] == [{"href": "https://example.com", "text": "Reference"}]


def test_duplicate_document_detection():
    xml = "<xml><title>Duplicate</title></xml>"
    stream_a = io.StringIO(xml)
    stream_b = io.StringIO(xml)

    parser_metrics.counters = {key: 0 for key in parser_metrics.counters}
    parse_document("xml", stream_a)

    with pytest.raises(DuplicateDocumentError):
        parse_document("xml", stream_b)
