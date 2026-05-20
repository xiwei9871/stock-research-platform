import json
from pathlib import Path

from stock_research import report_delivery
import stock_research.report_delivery_openclaw as report_delivery_openclaw


def _write_local_manifest(tmp_path: Path) -> Path:
    artifacts = [
        report_delivery.ReportArtifact(
            artifact_id="run_card_bundle:2026-05-20:abc123",
            report_type="run_card_bundle",
            title="Daily Research",
            trade_date="2026-05-20",
            generated_at="2026-05-20T08:00:00Z",
            run_card_path=str(tmp_path / "run_card.json"),
            evidence_dir=str(tmp_path / "evidence"),
            recommended_channels=["local", "openclaw"],
            summary="Daily research bundle",
        ),
        report_delivery.ReportArtifact(
            artifact_id="watchlist_report:2026-05-20:def456",
            report_type="watchlist_report",
            title="Watchlist",
            trade_date="2026-05-20",
            generated_at="2026-05-20T08:05:00Z",
            json_path=str(tmp_path / "watchlist.json"),
            recommended_channels=["local"],
            summary="Watchlist report",
        ),
    ]
    manifest = report_delivery.build_manifest(
        trade_date="2026-05-20",
        artifacts=artifacts,
        warnings=[],
        errors=[],
        generated_at="2026-05-20T08:10:00Z",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n")
    return manifest_path


def test_load_local_manifest_filters_single_openclaw_routable_artifact(tmp_path):
    manifest_path = _write_local_manifest(tmp_path)

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    manifest = adapter.load_local_manifest(manifest_path)
    artifacts = adapter.select_openclaw_artifacts(manifest)

    assert len(artifacts) == 1
    assert artifacts[0]["artifact_id"] == "run_card_bundle:2026-05-20:abc123"
    assert artifacts[0]["recommended_channels"] == ["local", "openclaw"]


def test_build_openclaw_item_uses_stable_run_card_routing(tmp_path):
    manifest_path = _write_local_manifest(tmp_path)

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    manifest = adapter.load_local_manifest(manifest_path)
    artifact = adapter.select_openclaw_artifacts(manifest)[0]
    item = adapter.build_openclaw_item(artifact)

    assert item.artifact_id == "run_card_bundle:2026-05-20:abc123"
    assert item.report_type == "run_card_bundle"
    assert item.route == "openclaw.report.run_card_bundle"
    assert item.action == "publish"
    assert item.payload["artifact_id"] == "run_card_bundle:2026-05-20:abc123"
