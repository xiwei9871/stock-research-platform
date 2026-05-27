from stock_research.p2.artifact_rollup import build_p2_artifact_rollup


def test_build_p2_artifact_rollup_marks_ready_when_required_artifacts_exist(tmp_path):
    artifact_path = tmp_path / "agent_report.json"
    artifact_path.write_text('{"status": "written"}', encoding="utf-8")

    rollup = build_p2_artifact_rollup(
        {
            "trade_date": "2026-05-28",
            "run_id": "p2-rollup-2026-05-28",
            "artifacts": [
                {
                    "group": "agent",
                    "name": "agent_report",
                    "path": str(artifact_path),
                    "required": True,
                }
            ],
        }
    )

    assert rollup["status"] == "ready"
    assert rollup["artifact_count"] == 1
    assert rollup["missing_required_count"] == 0
    assert rollup["artifacts"][0]["exists"] is True
    assert rollup["artifacts"][0]["path"] == str(artifact_path)


def test_build_p2_artifact_rollup_blocks_when_required_artifact_missing(tmp_path):
    missing_path = tmp_path / "missing.json"

    rollup = build_p2_artifact_rollup(
        {
            "trade_date": "2026-05-28",
            "run_id": "p2-rollup-2026-05-28",
            "artifacts": [
                {
                    "group": "simulation",
                    "name": "portfolio_simulation",
                    "path": str(missing_path),
                    "required": True,
                }
            ],
        }
    )

    assert rollup["status"] == "blocked"
    assert rollup["missing_required_count"] == 1
    assert rollup["artifacts"][0]["group"] == "simulation"
    assert rollup["artifacts"][0]["name"] == "portfolio_simulation"
    assert rollup["artifacts"][0]["required"] is True
    assert rollup["artifacts"][0]["exists"] is False
