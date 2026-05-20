from __future__ import annotations

import json
from pathlib import Path

import pytest

import stock_research.report_delivery_openclaw as report_delivery_openclaw


def _touch(path: Path, content: str = "x") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _artifact(
    tmp_path: Path,
    *,
    artifact_id: str,
    report_type: str,
    title: str,
    severity: str = "info",
    recommended_channels: list[str] | None = None,
    markdown_exists: bool = True,
    json_exists: bool = False,
    csv_exists: bool = False,
    run_card_exists: bool = False,
    evidence_exists: bool = False,
    requires_attention: bool = False,
) -> dict[str, object]:
    markdown_path = tmp_path / f"{artifact_id}.md"
    json_path = tmp_path / f"{artifact_id}.json"
    csv_path = tmp_path / f"{artifact_id}.csv"
    run_card_path = tmp_path / f"{artifact_id}_run_card.json"
    evidence_dir = tmp_path / f"{artifact_id}_evidence"

    artifact: dict[str, object] = {
        "artifact_id": artifact_id,
        "report_type": report_type,
        "title": title,
        "trade_date": "2026-05-20",
        "generated_at": "2026-05-21T08:00:00Z",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "csv_paths": [str(csv_path)],
        "run_card_path": str(run_card_path),
        "evidence_dir": str(evidence_dir),
        "warnings": [],
        "severity": severity,
        "summary": f"{title} summary",
        "tags": [report_type],
        "recommended_channels": list(recommended_channels or ["local"]),
        "requires_attention": requires_attention,
        "delivery_priority": 10,
        "metadata": {"source_path": str(markdown_path)},
    }

    if markdown_exists:
        _touch(markdown_path, f"# {title}\n")
    if json_exists:
        _touch(json_path, "{}\n")
    if csv_exists:
        _touch(csv_path, "a,b\n1,2\n")
    if run_card_exists:
        _touch(run_card_path, "{}\n")
    if evidence_exists:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        _touch(evidence_dir / "evidence.txt", "evidence\n")

    return artifact


def _write_manifest(tmp_path: Path, artifacts: list[dict[str, object]]) -> Path:
    manifest = {
        "generated_at": "2026-05-21T08:10:00Z",
        "trade_date": "2026-05-20",
        "channel": "local",
        "artifact_count": len(artifacts),
        "report_types": sorted({str(artifact["report_type"]) for artifact in artifacts}),
        "requires_attention_count": sum(1 for artifact in artifacts if artifact["requires_attention"]),
        "high_severity_count": sum(
            1 for artifact in artifacts if artifact["severity"] in {"high", "critical"}
        ),
        "artifacts": artifacts,
        "warnings": [],
        "errors": [],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_default_export_only_includes_openclaw_artifacts(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="daily_topn",
                report_type="daily_topn_report",
                title="Daily TopN",
                recommended_channels=["local", "openclaw"],
                json_exists=True,
            ),
            _artifact(
                tmp_path,
                artifact_id="watchlist",
                report_type="watchlist_report",
                title="Watchlist",
                recommended_channels=["local"],
                json_exists=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    assert result.item_count == 1
    assert [item.artifact_id for item in result.items] == ["daily_topn"]


def test_include_all_exports_all_artifacts(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="daily_topn",
                report_type="daily_topn_report",
                title="Daily TopN",
                recommended_channels=["local", "openclaw"],
                json_exists=True,
            ),
            _artifact(
                tmp_path,
                artifact_id="watchlist",
                report_type="watchlist_report",
                title="Watchlist",
                recommended_channels=["local"],
                json_exists=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path, include_all=True)

    assert result.item_count == 2
    assert [item.artifact_id for item in result.items] == ["daily_topn", "watchlist"]


def test_min_severity_filters_by_threshold(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="info_report",
                report_type="generic_report",
                title="Info",
                severity="info",
                recommended_channels=["local", "openclaw"],
                markdown_exists=True,
            ),
            _artifact(
                tmp_path,
                artifact_id="medium_report",
                report_type="generic_report",
                title="Medium",
                severity="medium",
                recommended_channels=["local", "openclaw"],
                markdown_exists=True,
            ),
            _artifact(
                tmp_path,
                artifact_id="high_report",
                report_type="generic_report",
                title="High",
                severity="high",
                recommended_channels=["local", "openclaw"],
                markdown_exists=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path, min_severity="medium")

    assert [item.artifact_id for item in result.items] == ["medium_report", "high_report"]


def test_missing_source_paths_are_skipped_with_warning(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="broken_report",
                report_type="generic_report",
                title="Broken",
                recommended_channels=["local", "openclaw"],
                markdown_exists=False,
                json_exists=False,
                csv_exists=False,
                run_card_exists=False,
                evidence_exists=False,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    assert result.item_count == 0
    assert any(warning.startswith("missing_source_path:") for warning in result.warnings)


def test_openclaw_export_writes_manifest_items_and_log(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="daily_topn",
                report_type="daily_topn_report",
                title="Daily TopN",
                recommended_channels=["local", "openclaw"],
                json_exists=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    manifest_file = Path(result.openclaw_manifest_path)
    items_file = Path(result.openclaw_items_path)
    log_file = Path(result.openclaw_delivery_log_path)

    assert result.status == "dry_run"
    assert result.item_count == 1
    assert manifest_file.exists()
    assert items_file.exists()
    assert log_file.exists()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["channel"] == "openclaw"
    assert manifest["dry_run"] is True
    assert manifest["source_manifest_path"] == str(manifest_path)
    assert manifest["item_count"] == 1
    assert [item["artifact_id"] for item in manifest["items"]] == ["daily_topn"]

    item_lines = items_file.read_text(encoding="utf-8").splitlines()
    assert len(item_lines) == 1
    assert json.loads(item_lines[0])["artifact_id"] == "daily_topn"

    log_lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 1
    log_record = json.loads(log_lines[0])
    assert log_record["status"] == "dry_run"
    assert log_record["channel"] == "openclaw"
    assert log_record["item_count"] == 1
    assert log_record["openclaw_manifest_path"] == str(manifest_file)
    assert log_record["openclaw_items_path"] == str(items_file)


def test_openclaw_export_dry_run_writes_dry_run_log_status(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="risk_alert",
                report_type="risk_alert_report",
                title="Risk Alert",
                recommended_channels=["local", "openclaw"],
                json_exists=True,
                requires_attention=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path, dry_run=True)

    log_record = json.loads(Path(result.openclaw_delivery_log_path).read_text(encoding="utf-8").splitlines()[0])

    assert result.status == "dry_run"
    assert log_record["status"] == "dry_run"


def test_openclaw_export_empty_match_set_does_not_crash(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                tmp_path,
                artifact_id="broken_report",
                report_type="generic_report",
                title="Broken",
                recommended_channels=["local", "openclaw"],
                markdown_exists=False,
                json_exists=False,
                csv_exists=False,
                run_card_exists=False,
                evidence_exists=False,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    manifest_file = Path(result.openclaw_manifest_path)
    items_file = Path(result.openclaw_items_path)
    log_file = Path(result.openclaw_delivery_log_path)

    assert result.item_count == 0
    assert result.warnings
    assert manifest_file.exists()
    assert items_file.exists()
    assert log_file.exists()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["item_count"] == 0
    assert manifest["items"] == []
    assert any(warning.startswith("missing_source_path:") for warning in manifest["warnings"])
    assert items_file.read_text(encoding="utf-8") == ""


def test_openclaw_export_defaults_to_openclaw_output_root_sibling_of_trade_date_dir(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs" / "report_delivery"
    trade_date_dir = output_root / "2026-05-20"
    trade_date_dir.mkdir(parents=True)
    manifest_path = _write_manifest(
        trade_date_dir,
        [
            _artifact(
                trade_date_dir,
                artifact_id="daily_topn",
                report_type="daily_topn_report",
                title="Daily TopN",
                recommended_channels=["local", "openclaw"],
                json_exists=True,
            ),
        ],
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    expected_output_dir = output_root / "openclaw" / "2026-05-20"
    assert result.output_dir == str(expected_output_dir.resolve())
    assert Path(result.openclaw_manifest_path) == expected_output_dir / "openclaw_manifest.json"
    assert Path(result.openclaw_items_path) == expected_output_dir / "openclaw_items.jsonl"
    assert (
        Path(result.openclaw_delivery_log_path)
        == expected_output_dir / "openclaw_delivery_log.jsonl"
    )


@pytest.mark.parametrize(
    ("report_type", "expected_action", "expected_route"),
    [
        ("run_card_bundle", "review_evidence", "evidence_review"),
        ("daily_topn_report", "review_topn_candidates", "daily_research"),
        ("watchlist_report", "review_watchlist", "daily_research"),
        ("must_watch_report", "review_must_watch", "daily_research"),
        ("risk_alert_report", "review_risk_alert", "research_alert"),
        ("factor_eval_report", "review_factor_eval", "research_validation"),
        ("backtest_report", "review_backtest", "research_validation"),
        ("generic_report", "review_report", "research_inbox"),
    ],
)
def test_mapping_rules_render_stable_actions_and_routes(
    tmp_path: Path,
    report_type: str,
    expected_action: str,
    expected_route: str,
) -> None:
    artifact = _artifact(
        tmp_path,
        artifact_id=f"{report_type}:2026-05-20:abc123",
        report_type=report_type,
        title=report_type.replace("_", " ").title(),
        recommended_channels=["local", "openclaw"],
        markdown_exists=True,
        json_exists=True,
        csv_exists=True,
        run_card_exists=True,
        evidence_exists=True,
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    item = adapter.build_openclaw_item(artifact)

    assert item.recommended_action == expected_action
    assert item.openclaw_route == expected_route
    assert item.payload["recommended_action"] == expected_action
    assert item.payload["openclaw_route"] == expected_route


def test_export_item_preserves_source_evidence_and_run_card_references(tmp_path: Path) -> None:
    artifact = _artifact(
        tmp_path,
        artifact_id="run_card_bundle:2026-05-20:abc123",
        report_type="run_card_bundle",
        title="Run Card",
        recommended_channels=["local", "openclaw"],
        markdown_exists=True,
        json_exists=True,
        csv_exists=True,
        run_card_exists=True,
        evidence_exists=True,
    )

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    item = adapter.build_openclaw_item(artifact)

    assert item.source_paths == [
        str(tmp_path / "run_card_bundle:2026-05-20:abc123.md"),
        str(tmp_path / "run_card_bundle:2026-05-20:abc123.json"),
        str(tmp_path / "run_card_bundle:2026-05-20:abc123.csv"),
    ]
    assert item.evidence_paths == [str(tmp_path / "run_card_bundle:2026-05-20:abc123_evidence")]
    assert item.run_card_path == str(tmp_path / "run_card_bundle:2026-05-20:abc123_run_card.json")
    assert item.payload["source_paths"] == item.source_paths
    assert item.payload["evidence_paths"] == item.evidence_paths
    assert item.payload["run_card_path"] == item.run_card_path


def test_export_resolves_relative_paths_against_manifest_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_root = tmp_path / "manifest-root"
    artifact_dir = manifest_root / "reports"
    evidence_dir = manifest_root / "evidence"
    manifest_root.mkdir()
    artifact_dir.mkdir()
    evidence_dir.mkdir()

    (artifact_dir / "daily_topn.md").write_text("# Daily TopN\n", encoding="utf-8")
    (artifact_dir / "daily_topn.json").write_text("{}\n", encoding="utf-8")
    (artifact_dir / "daily_topn.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (manifest_root / "run_card.json").write_text("{}\n", encoding="utf-8")
    (evidence_dir / "evidence.txt").write_text("evidence\n", encoding="utf-8")

    manifest = {
        "generated_at": "2026-05-21T08:10:00Z",
        "trade_date": "2026-05-20",
        "channel": "local",
        "artifact_count": 1,
        "report_types": ["daily_topn_report"],
        "requires_attention_count": 0,
        "high_severity_count": 0,
        "artifacts": [
            {
                "artifact_id": "daily_topn_report:2026-05-20:abc123",
                "report_type": "daily_topn_report",
                "title": "Daily TopN",
                "trade_date": "2026-05-20",
                "generated_at": "2026-05-21T08:00:00Z",
                "markdown_path": "reports/daily_topn.md",
                "json_path": "reports/daily_topn.json",
                "csv_paths": ["reports/daily_topn.csv"],
                "run_card_path": "run_card.json",
                "evidence_dir": "evidence",
                "warnings": [],
                "severity": "info",
                "summary": "Daily TopN summary",
                "tags": ["daily_topn_report"],
                "recommended_channels": ["local", "openclaw"],
                "requires_attention": False,
                "delivery_priority": 10,
                "metadata": {"source_path": "reports/daily_topn.md"},
            }
        ],
        "warnings": [],
        "errors": [],
    }
    manifest_path = manifest_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(manifest_path)

    assert result.item_count == 1
    item = result.items[0]
    assert item.source_paths == [
        str(artifact_dir / "daily_topn.md"),
        str(artifact_dir / "daily_topn.json"),
        str(artifact_dir / "daily_topn.csv"),
    ]
    assert item.evidence_paths == [str(evidence_dir)]
    assert item.run_card_path == str(manifest_root / "run_card.json")
    assert item.payload["source_paths"] == item.source_paths
    assert item.payload["evidence_paths"] == item.evidence_paths
    assert item.payload["run_card_path"] == item.run_card_path
