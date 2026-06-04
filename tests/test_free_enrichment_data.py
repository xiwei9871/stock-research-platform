import pandas as pd

from stock_research.free_enrichment_data import (
    DatasetRunResult,
    build_event_id,
    normalize_ts_code,
    payload_hash,
    run_lhb_backfill,
    ts_code_to_asset_id,
)


def test_normalize_ts_code_and_asset_id():
    assert normalize_ts_code("600000") == "600000.SH"
    assert normalize_ts_code("000001") == "000001.SZ"
    assert ts_code_to_asset_id("600000.SH") == "CN:SH:600000"
    assert ts_code_to_asset_id("000001.SZ") == "CN:SZ:000001"


def test_normalize_ts_code_handles_numeric_and_missing_values():
    assert normalize_ts_code(1.0) == "000001.SZ"
    assert normalize_ts_code(None) == ""
    assert normalize_ts_code(float("nan")) == ""
    assert normalize_ts_code(pd.NA) == ""


def test_normalize_ts_code_handles_prefixed_and_asset_id_forms():
    assert normalize_ts_code("SZ.000001") == "000001.SZ"
    assert normalize_ts_code("SH600000") == "600000.SH"
    assert normalize_ts_code("SH.600000") == "600000.SH"
    assert normalize_ts_code("CN:SZ:000001") == "000001.SZ"


def test_ts_code_to_asset_id_rejects_malformed_inputs():
    assert ts_code_to_asset_id("") == ""
    assert ts_code_to_asset_id("not-a-code") == ""
    assert ts_code_to_asset_id("SZ.000001") == "CN:SZ:000001"


def test_payload_hash_is_stable_for_dict_key_order():
    left = payload_hash({"b": 2, "a": 1})
    right = payload_hash({"a": 1, "b": 2})
    assert left == right
    assert len(left) == 64


def test_build_event_id_is_deterministic():
    assert build_event_id("repurchase", ["600000.SH", "2025-01-02", "plan"]) == build_event_id(
        "repurchase", ["600000.SH", "2025-01-02", "plan"]
    )


def test_build_event_id_changes_when_parts_change():
    assert build_event_id("repurchase", ["600000.SH", "2025-01-02", "plan"]) != build_event_id(
        "repurchase", ["600000.SH", "2025-01-03", "plan"]
    )


def test_build_event_id_preserves_zero_as_distinct_part():
    assert build_event_id("x", [0]) != build_event_id("x", [""])


def test_build_event_id_handles_missing_parts_without_crashing():
    first = build_event_id("x", [None, float("nan"), pd.NA])
    second = build_event_id("x", [None, float("nan"), pd.NA])
    assert first == second


def test_dataset_run_result_to_dict():
    result = DatasetRunResult(
        dataset="repurchase",
        fetched_rows=3,
        normalized_rows=2,
        upserted_rows=2,
        empty_results=1,
        failed_requests=0,
    )
    assert result.to_dict()["dataset"] == "repurchase"
    assert result.to_dict()["upserted_rows"] == 2


def test_run_lhb_backfill_uses_existing_lhb_import(monkeypatch, tmp_path):
    calls = []

    def fake_lhb_import(**kwargs):
        calls.append(kwargs)
        return {
            "top_list": pd.DataFrame([{"ts_code": "600000.SH"}]),
            "top_inst": pd.DataFrame(),
            "paths": {"top_list": str(tmp_path / "list.csv"), "top_inst": str(tmp_path / "inst.csv")},
        }

    monkeypatch.setattr("stock_research.free_enrichment_data.run_lhb_sample_import", fake_lhb_import)

    result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=False,
        service="test",
    )

    assert calls[0]["provider"] == "akshare"
    assert calls[0]["ts_codes"] is None
    assert result.dataset == "lhb"
    assert result.normalized_rows == 1
