from app.connectors.factory import ConnectorFactory
from app.nlp.pipeline import LiteratureNLP
from app.orchestrator.pipeline import PipelineRunner


def test_connector_factory_builds_pubmed_connector():
    connector = ConnectorFactory.create("pubmed", {"base_url": "https://example.com"})
    assert connector.name == "pubmed"
    assert connector.config["base_url"] == "https://example.com"


def test_pipeline_runner_executes_stage_sequence():
    runner = PipelineRunner(stages=[lambda doc: {**doc, "stage": "parsed"}, lambda doc: {**doc, "stage": "indexed"}])
    result = runner.run({"id": "paper-1"})
    assert result["stage"] == "indexed"


def test_nlp_pipeline_extracts_entities_and_summary():
    text = "HER2-positive breast cancer is treated by trastuzumab in combination therapy."
    result = LiteratureNLP().run(text)
    assert "entities" in result
    assert "summary" in result
    assert any(entity.lower() in {"her2", "trastuzumab", "breast cancer"} for entity in result["entities"])
