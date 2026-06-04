import pandas as pd

from stock_research.free_enrichment_data import (
    DatasetRunResult,
    build_event_id,
    normalize_shareholder_count_rows,
    normalize_top_holder_rows,
    normalize_ts_code,
    payload_hash,
    run_lhb_backfill,
    ts_code_to_asset_id,
    upsert_shareholder_count_rows,
    upsert_top_holder_rows,
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


def test_normalize_shareholder_count_rows_maps_chinese_columns():
    raw = pd.DataFrame(
        [
            {
                "代码": "600000",
                "截止日期": "2025-03-31",
                "公告日期": "2025-04-20",
                "股东户数": 100000,
                "股东户数增减": -1000,
                "股东户数较上期变化百分比": -1.0,
            }
        ]
    )

    frame = normalize_shareholder_count_rows(raw, endpoint="stock_zh_a_gdhs_detail_em")

    assert frame.iloc[0]["ts_code"] == "600000.SH"
    assert frame.iloc[0]["asset_id"] == "CN:SH:600000"
    assert frame.iloc[0]["report_date"] == "2025-03-31"
    assert frame.iloc[0]["shareholder_count"] == 100000


def test_normalize_top_holder_rows_supports_float_holder_flag():
    raw = pd.DataFrame(
        [
            {
                "代码": "000001",
                "报告期": "2025-03-31",
                "股东名称": "中央汇金资产管理有限责任公司",
                "股东类型": "其它",
                "持股数": 123,
                "占总股本持股比例": 1.2,
                "增减": 3,
                "名次": 1,
            }
        ]
    )

    frame = normalize_top_holder_rows(raw, endpoint="stock_gdfx_top_10_em")

    assert frame.iloc[0]["ts_code"] == "000001.SZ"
    assert frame.iloc[0]["report_period"] == "2025-03-31"
    assert frame.iloc[0]["holder_name"] == "中央汇金资产管理有限责任公司"


def test_holder_upserts_use_expected_tables(monkeypatch):
    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("stock_research.free_enrichment_data.connect", lambda service: Conn())
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.execute_many",
        lambda conn, sql, rows: calls.append((sql, list(rows))),
    )

    shareholder = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_date": "2025-03-31",
                "announcement_date": "2025-04-20",
                "shareholder_count": 100000,
                "shareholder_count_change": -1000,
                "shareholder_count_change_pct": -1,
                "source": "akshare",
                "source_endpoint": "stock_zh_a_gdhs_detail_em",
                "payload_hash": "h1",
            }
        ]
    )
    holders = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_period": "2025-03-31",
                "holder_name": "holder",
                "holder_type": "fund",
                "hold_amount": 1,
                "hold_ratio": 1,
                "hold_change": 0,
                "rank": 1,
                "source": "akshare",
                "source_endpoint": "stock_gdfx_top_10_em",
                "payload_hash": "h2",
            }
        ]
    )

    upsert_shareholder_count_rows(shareholder, service="test")
    upsert_top_holder_rows(holders, table="fundamental.top10_holder", service="test")

    assert "INSERT INTO fundamental.shareholder_count" in calls[0][0]
    assert "INSERT INTO fundamental.top10_holder" in calls[1][0]


def test_run_lhb_backfill_uses_existing_lhb_import(tmp_path):
    calls = []

    def fake_lhb_import(**kwargs):
        calls.append(kwargs)
        return {
            "top_list": pd.DataFrame([{"ts_code": "600000.SH"}]),
            "top_inst": pd.DataFrame(),
            "paths": {"top_list": str(tmp_path / "list.csv"), "top_inst": str(tmp_path / "inst.csv")},
        }

    result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=False,
        service="test",
        runner=fake_lhb_import,
    )

    assert calls[0]["provider"] == "akshare"
    assert calls[0]["ts_codes"] is None
    assert result.dataset == "lhb"
    assert result.normalized_rows == 1


def test_run_lhb_backfill_dry_run_does_not_call_importer(tmp_path):
    def fail_import(**kwargs):
        raise AssertionError("runner should not be called")

    result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=True,
        service="test",
        runner=fail_import,
    )

    assert result == DatasetRunResult(dataset="lhb")


def test_run_lhb_backfill_counts_none_and_missing_outputs_as_empty(tmp_path):
    none_result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=False,
        service="test",
        runner=lambda **kwargs: {"top_list": None, "top_inst": None},
    )
    missing_result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=False,
        service="test",
        runner=lambda **kwargs: {},
    )

    assert none_result.normalized_rows == 0
    assert none_result.empty_results == 1
    assert missing_result.normalized_rows == 0
    assert missing_result.empty_results == 1
