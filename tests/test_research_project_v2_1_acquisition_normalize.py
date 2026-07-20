from __future__ import annotations

from pathlib import Path

from stock_research.research_project_v2_1.acquisition_import import (
    LocalFileProvider,
    build_manual_import_request,
)
from stock_research.research_project_v2_1.acquisition_normalize import (
    DeterministicNormalizationAdapter,
    DoclingNormalizationAdapter,
    build_acquisition_checkpoint,
    normalize_acquired_artifact,
    write_acquisition_checkpoint,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:normalize-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


def imported_html(tmp_path: Path, layout: LayeredResearchLayout):
    source = tmp_path / "source.html"
    source.write_text("<html><body><h1>Architecture</h1><p>Fixture</p></body></html>", encoding="utf-8")
    request = build_manual_import_request(
        project_id="research_project:ai_compute_pcb_industry_bottleneck",
        research_version_context="research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        requirement_id="requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
        candidate_id=None,
        local_path=str(source),
        source_title="Architecture HTML",
        publisher="Example Standards Body",
        original_url="https://example.com/architecture",
        source_note=None,
        publication_date="2026-07-01",
        imported_at="2026-07-20T08:00:00Z",
        imported_by="Codex",
        actor_type="codex",
        declared_mime_type="text/html",
        access_or_license_note="Public technical document.",
        locator_metadata={"section_locators_expected": True},
        provenance=PROVENANCE,
    )
    return LocalFileProvider(
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 10]).__next__,
    ).acquire(request, layout=layout)


def test_deterministic_normalization_preserves_raw_and_writes_distinct_document(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    acquired = imported_html(tmp_path, layout)
    raw_path = layout.root / acquired.artifact["raw_artifact_path"]
    before = raw_path.read_bytes()
    outcome = normalize_acquired_artifact(
        acquired.artifact,
        adapter=DeterministicNormalizationAdapter(),
        layout=layout,
        parsed_at="2026-07-20T08:00:02Z",
        provenance=PROVENANCE,
    )
    assert outcome.status == "normalized"
    assert outcome.document is not None
    assert outcome.document["artifact_id"] == acquired.artifact["evidence_artifact_id"]
    assert outcome.parser_configuration == {"mode": "deterministic"}
    assert raw_path.read_bytes() == before
    stored = layout.evidence_normalized_dir / f"{outcome.document['document_id']}.json"
    assert stored.is_file()


def test_normalization_failure_does_not_remove_raw_artifact(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    acquired = imported_html(tmp_path, layout)
    raw_path = layout.root / acquired.artifact["raw_artifact_path"]

    class FailingAdapter:
        name = "fixture-failure"
        version = "1.0.0"
        configuration = {"mode": "fixture"}

        def normalize(self, data: bytes, *, content_type: str):
            raise ValueError("fixture parse failure")

    outcome = normalize_acquired_artifact(
        acquired.artifact,
        adapter=FailingAdapter(),
        layout=layout,
        parsed_at="2026-07-20T08:00:02Z",
        provenance=PROVENANCE,
    )
    assert outcome.status == "failed"
    assert outcome.document is None
    assert outcome.failure_code == "unsupported_format"
    assert raw_path.is_file()


def test_checkpoint_references_attempt_artifact_and_normalization_without_research_version(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    acquired = imported_html(tmp_path, layout)
    outcome = normalize_acquired_artifact(
        acquired.artifact,
        adapter=DeterministicNormalizationAdapter(),
        layout=layout,
        parsed_at="2026-07-20T08:00:02Z",
        provenance=PROVENANCE,
    )
    checkpoint = build_acquisition_checkpoint(
        project_id="research_project:ai_compute_pcb_industry_bottleneck",
        research_version_context="research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        created_at="2026-07-20T08:00:03Z",
        attempts=[acquired.attempt],
        artifacts=[acquired.artifact],
        normalization_outcomes=[outcome],
        selected_requirement_ids=[
            "requirement:ai_compute_pcb_industry_bottleneck:r2b_er01"
        ],
        candidate_ids=["source_candidate:smoke-fixture"],
        exact_duplicate_results=[],
        provenance_completeness="complete",
        security_violations=[],
        unresolved_issues=["Evidence assessment is outside the smoke scope."],
        provenance=PROVENANCE,
    )
    assert checkpoint["status"] == "pending_assessment"
    assert checkpoint["pending_assessment_artifact_ids"] == [
        acquired.artifact["evidence_artifact_id"]
    ]
    assert checkpoint["normalization_records"][0]["parser"] == outcome.parser
    assert checkpoint["selected_requirement_ids"] == [
        "requirement:ai_compute_pcb_industry_bottleneck:r2b_er01"
    ]
    assert checkpoint["candidate_ids"] == ["source_candidate:smoke-fixture"]
    assert checkpoint["successful_attempt_count"] == 1
    assert checkpoint["failed_attempt_count"] == 0
    assert checkpoint["provider_distribution"] == {"local_file": 1}
    assert checkpoint["failure_distribution"] == {}
    assert checkpoint["provenance_completeness"] == "complete"
    assert checkpoint["security_violations"] == []
    assert checkpoint["unresolved_issues"] == [
        "Evidence assessment is outside the smoke scope."
    ]
    path = write_acquisition_checkpoint(checkpoint, layout=layout)
    assert path.is_file()
    assert not (layout.project_dir("ai_compute_pcb_industry_bottleneck") / "versions/v0.2.2.json").exists()


def test_optional_docling_adapter_creates_a_distinct_normalized_representation(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    acquired = imported_html(tmp_path, layout)
    deterministic = normalize_acquired_artifact(
        acquired.artifact,
        adapter=DeterministicNormalizationAdapter(),
        layout=layout,
        parsed_at="2026-07-20T08:00:02Z",
        provenance=PROVENANCE,
    )
    docling = normalize_acquired_artifact(
        acquired.artifact,
        adapter=DoclingNormalizationAdapter(
            parser=lambda _path: {
                "status": "parsed",
                "markdown": "# Architecture\n\nDocling fixture.",
            },
            version="2.110.0",
        ),
        layout=layout,
        parsed_at="2026-07-20T08:00:03Z",
        provenance=PROVENANCE,
    )
    assert docling.status == "normalized"
    assert docling.parser == "docling"
    assert docling.document["document_id"] != deterministic.document["document_id"]
    assert docling.parser_configuration == {
        "mode": "docling",
        "use_ocr": False,
        "table_mode": "preserve",
    }
