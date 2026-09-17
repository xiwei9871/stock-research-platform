from __future__ import annotations

import importlib
from pathlib import Path


MODULE_NAME = "stock_research.data_to_brief_docling_90_stock_review_dashboard_integration"


def test_docling_paths_follow_runtime_release_root(monkeypatch) -> None:
    module = importlib.import_module(MODULE_NAME)
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", "/tmp/stock-release")

    module = importlib.reload(module)

    assert module.PROJECT_ROOT == Path("/tmp/stock-release")
    assert module.SOURCE_DIR == Path(
        "/tmp/stock-release/outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
    )
    assert module.OUTPUT_DIR == Path(
        "/tmp/stock-release/outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1"
    )

    monkeypatch.delenv("STOCK_RESEARCH_RELEASE_ROOT")
    importlib.reload(module)


def test_resolve_docling_artifact_rejects_traversal(tmp_path) -> None:
    module = importlib.import_module(MODULE_NAME)
    artifact = (
        tmp_path
        / "outputs"
        / "research"
        / module.BATCH_ID
        / "reports_html"
        / "report.html"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_text("<html></html>", encoding="utf-8")

    assert module.resolve_docling_artifact(tmp_path, "reports_html/report.html") == artifact
    assert module.resolve_docling_artifact(tmp_path, "../report.html") is None
    assert module.resolve_docling_artifact(tmp_path, "reports_html/../../report.html") is None
