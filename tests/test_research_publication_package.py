import json
from pathlib import Path

from stock_research import cli
from stock_research import research_publication_package


def _gate(status: str = "blocked") -> dict:
    return {
        "trade_date": "2026-07-03",
        "status": status,
        "research_ready_for_publication": status == "research_ready",
        "actual_publish_enabled": False,
        "publication_entrypoint_status": "scaffolded",
        "internal_snapshot_enabled": status == "research_ready",
        "external_delivery_enabled": False,
        "summary": {
            "case_count": 15,
            "open_case_count": 15,
            "claim_count": 90,
            "evidence_artifact_count": 30,
            "evidence_link_count": 120,
            "evidence_gap_count": 15 if status == "blocked" else 0,
            "pending_gap_count": 14 if status == "blocked" else 0,
            "reviewed_gap_count": 0,
            "request_more_evidence_count": 1 if status == "blocked" else 0,
            "deferred_gap_count": 0,
            "unmatched_digest_count": 0,
            "error_count": 0,
        },
        "blockers": [
            {"code": "pending_gap", "message": "14 gap cases have not been reviewed", "count": 14}
        ]
        if status == "blocked"
        else [],
        "warnings": [
            {
                "code": "external_delivery_not_connected",
                "message": "External research delivery is not connected",
                "count": 1,
            }
        ],
        "top_blocked_cases": [
            {
                "case_id": "research_case:alpha",
                "trade_date": "2026-07-03",
                "asset_id": "CN:SZ:000001",
                "theme": "bank_reversal",
                "title": "Bank reversal candidate",
                "review_status": "pending",
                "gap_reasons": ["partial_evidence"],
                "gap_summary": "partial evidence signal found",
                "payload": {"must_not": "leak"},
            }
        ],
    }


def test_publication_package_blocked_gate_is_preview_not_publishable(monkeypatch):
    monkeypatch.setattr(research_publication_package, "get_research_publish_gate", lambda **kwargs: _gate("blocked"))

    package = research_publication_package.build_research_publication_package("2026-07-03")

    assert package["trade_date"] == "2026-07-03"
    assert package["package_id"].startswith("research_publication_package:")
    assert package["publishable"] is False
    assert package["actual_publish_enabled"] is False
    assert package["gate"]["status"] == "blocked"
    assert package["summary"]["case_count"] == 15
    assert package["summary"]["gap_count"] == 15
    assert package["sections"][1]["section_type"] == "blocked_cases"
    assert package["sections"][1]["items"][0]["case_id"] == "research_case:alpha"
    assert "payload" not in json.dumps(package)
    assert "auto_trade" not in json.dumps(package)
    assert "buy" not in json.dumps(package).lower()
    assert "sell" not in json.dumps(package).lower()


def test_publication_package_research_ready_is_publishable_but_actual_publish_disabled(monkeypatch):
    monkeypatch.setattr(research_publication_package, "get_research_publish_gate", lambda **kwargs: _gate("research_ready"))

    package = research_publication_package.build_research_publication_package("2026-07-03")

    assert package["publishable"] is True
    assert package["actual_publish_enabled"] is False
    assert package["gate"]["status"] == "research_ready"
    assert package["warnings"][0]["code"] == "external_delivery_not_connected"


def test_run_research_publication_preview_writes_json_and_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(
        research_publication_package,
        "build_research_publication_package",
        lambda trade_date, service="research": {
            "trade_date": trade_date,
            "package_id": "research_publication_package:abc",
            "publishable": False,
            "actual_publish_enabled": False,
            "gate": {"status": "blocked", "research_ready_for_publication": False, "actual_publish_enabled": False},
            "summary": {"case_count": 1, "claim_count": 2, "gap_count": 1},
            "sections": [],
            "warnings": [],
            "blockers": [{"code": "pending_gap", "message": "1 gap case has not been reviewed", "count": 1}],
        },
    )

    result = research_publication_package.run_research_publication_preview(
        trade_date="2026-07-03",
        output_dir=tmp_path,
    )

    assert result["status"] == "preview_generated"
    assert result["publishable"] is False
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    persisted = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert persisted["package_id"] == "research_publication_package:abc"
    assert "publishable=false" in Path(result["markdown_path"]).read_text(encoding="utf-8")


def test_publication_entrypoint_lock_report_is_written(tmp_path):
    path = research_publication_package.write_publication_entrypoint_lock_report(tmp_path)

    content = Path(path).read_text(encoding="utf-8")
    assert "Canonical recommendation" in content
    assert "p5/notifications.py" in content
    assert "strategy_eod_publish.py" in content
    assert "publication_snapshot" in content
    assert Path(path).name == "publication_entrypoint_lock_report.md"


def test_research_publication_preview_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "preview_generated",
            "publishable": False,
            "json_path": str(tmp_path / "research_publication_package.json"),
            "markdown_path": str(tmp_path / "research_publication_preview.md"),
            "package_id": "research_publication_package:abc",
        }

    monkeypatch.setattr(cli, "run_research_publication_preview", fake_run)

    cli.main_for_args(
        [
            "research-publication-preview",
            "--trade-date",
            "2026-07-03",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-07-03"
    assert captured["output_dir"] == tmp_path
