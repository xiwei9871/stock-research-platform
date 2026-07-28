from __future__ import annotations

import stock_research.strategy_manifest_transfer as transfer


def _rows(trade_date: str = "2026-07-28"):
    run_id = f"strategy-eod-{trade_date}-local"
    return [
        {
            "run_id": run_id,
            "trade_date": trade_date,
            "module": module,
            "status": "success",
            "artifact_path": f"/release/outputs/research/{module}.csv",
            "metadata": {"review_path": f"/release/outputs/research/{module}.csv"},
        }
        for module in sorted(transfer.REQUIRED_MODULES)
    ]


def test_export_snapshot_validates_official_run_and_relocates_paths(monkeypatch):
    monkeypatch.setattr(transfer, "load_recent_data_run_manifest", lambda **_kwargs: _rows())

    payload = transfer.export_strategy_manifest_snapshot(
        trade_date="2026-07-28",
        source_root="/release",
        target_root="/app",
    )

    assert payload["run_id"] == "strategy-eod-2026-07-28-local"
    assert payload["rows"][0]["artifact_path"].startswith("/app/outputs/research/")
    assert payload["rows"][0]["metadata"]["review_path"].startswith("/app/outputs/research/")


def test_import_snapshot_upserts_all_rows_in_one_connection(monkeypatch):
    rows = _rows()
    payload = {
        "schema_version": transfer.SCHEMA_VERSION,
        "trade_date": "2026-07-28",
        "run_id": "strategy-eod-2026-07-28-local",
        "rows": rows,
    }
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(transfer, "apply_data_run_manifest_schema", lambda **_kwargs: None)
    monkeypatch.setattr(transfer, "connect", lambda _service: Connection())
    monkeypatch.setattr(
        transfer,
        "upsert_data_run_manifest_with_connection",
        lambda row, *, conn: calls.append((row["module"], conn)),
    )

    assert transfer.import_strategy_manifest_snapshot(payload) == len(rows)
    assert {module for module, _conn in calls} == transfer.REQUIRED_MODULES
