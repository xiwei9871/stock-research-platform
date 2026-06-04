import pandas as pd

from stock_research.free_enrichment_data import (
    DatasetRunResult,
    build_event_id,
    normalize_institution_survey_rows,
    normalize_repurchase_rows,
    normalize_shareholder_count_rows,
    normalize_shareholder_trade_rows,
    normalize_top_holder_rows,
    normalize_ts_code,
    payload_hash,
    run_lhb_backfill,
    ts_code_to_asset_id,
    upsert_event_rows,
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


def test_payload_hash_normalizes_missing_and_numpy_scalar_values():
    import numpy as np

    assert payload_hash({"x": None}) == payload_hash({"x": np.nan})
    assert payload_hash({"x": pd.NA}) == payload_hash({"x": pd.NaT})
    assert payload_hash({"x": np.int64(1)}) == payload_hash({"x": 1})


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


def test_normalize_repurchase_rows_builds_event_id():
    raw = pd.DataFrame([{"代码": "600000", "公告日期": "2025-02-01", "进度": "实施", "已回购金额": 1000}])
    frame = normalize_repurchase_rows(raw, endpoint="stock_repurchase_em")
    assert frame.iloc[0]["event_id"].startswith("repurchase:")
    assert frame.iloc[0]["asset_id"] == "CN:SH:600000"
    assert frame.iloc[0]["announcement_date"] == "2025-02-01"


def test_normalize_institution_survey_rows_keeps_summary():
    raw = pd.DataFrame([{"代码": "000001", "调研日期": "2025-05-01", "机构数量": 12, "调研内容": "核心问题"}])
    frame = normalize_institution_survey_rows(raw, endpoint="stock_jgdy_detail_em")
    assert frame.iloc[0]["event_id"].startswith("survey:")
    assert frame.iloc[0]["institution_count"] == 12
    assert frame.iloc[0]["summary"] == "核心问题"


def test_normalize_shareholder_trade_rows_keeps_trade_type():
    raw = pd.DataFrame([{"代码": "000001", "变动日期": "2025-04-01", "股东名称": "holder", "变动方向": "减持", "变动数量": 10}])
    frame = normalize_shareholder_trade_rows(raw, endpoint="stock_ggcg_em")
    assert frame.iloc[0]["event_id"].startswith("shareholder_trade:")
    assert frame.iloc[0]["trade_type"] == "减持"


def test_holder_normalizers_filter_invalid_rows_and_empty_frames():
    empty_shareholders = normalize_shareholder_count_rows(pd.DataFrame(), endpoint="x")
    empty_holders = normalize_top_holder_rows(pd.DataFrame(), endpoint="x")
    assert empty_shareholders.empty
    assert empty_holders.empty

    invalid_shareholders = normalize_shareholder_count_rows(
        pd.DataFrame([{"代码": "bad", "截止日期": "2025-03-31"}]),
        endpoint="x",
    )
    invalid_holders = normalize_top_holder_rows(
        pd.DataFrame([{"代码": "000001", "报告期": "2025-03-31", "股东名称": ""}]),
        endpoint="x",
    )

    assert invalid_shareholders.empty
    assert invalid_holders.empty


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
    assert "ON CONFLICT (asset_id, report_period, holder_name, source)" in calls[1][0]
    assert calls[1][1][0][0:5] == ("CN:SH:600000", "600000.SH", "2025-03-31", "holder", "fund")


def test_holder_upserts_convert_missing_values_and_use_conflict_keys(monkeypatch):
    import numpy as np

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
                "announcement_date": pd.NaT,
                "shareholder_count": pd.NA,
                "shareholder_count_change": float("nan"),
                "shareholder_count_change_pct": -1,
                "source": "akshare",
                "source_endpoint": "endpoint",
                "payload_hash": "h",
            }
        ]
    )
    upsert_shareholder_count_rows(shareholder, service="test")

    sql, rows = calls[0]
    assert "ON CONFLICT (asset_id, report_date, source)" in sql
    assert rows[0][0:4] == ("CN:SH:600000", "600000.SH", "2025-03-31", None)
    assert rows[0][4] is None
    assert rows[0][5] is None

    holders = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_period": "2025-03-31",
                "holder_name": "holder",
                "holder_type": np.array(["fund", "other"]),
                "hold_amount": 1,
                "hold_ratio": 1,
                "hold_change": 0,
                "rank": 1,
                "source": "akshare",
                "source_endpoint": "endpoint",
                "payload_hash": "h",
            }
        ]
    )
    upsert_top_holder_rows(holders, table="fundamental.top10_float_holder", service="test")

    assert calls[1][1][0][4] == ["fund", "other"]


def test_upsert_top_holder_rejects_unknown_table():
    try:
        upsert_top_holder_rows(pd.DataFrame(), table="fundamental.bad_table", service="test")
    except ValueError as exc:
        assert "Unsupported holder table" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_upsert_event_rows_uses_requested_event_table(monkeypatch):
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

    frame = pd.DataFrame([{"event_id": "repurchase:1", "asset_id": "CN:SH:600000", "ts_code": "600000.SH"}])
    upsert_event_rows(frame, table="event.stock_repurchase", service="test")

    assert "INSERT INTO event.stock_repurchase" in calls[0][0]
    assert "ON CONFLICT (event_id)" in calls[0][0]


def test_upsert_event_rows_rejects_unknown_table():
    try:
        upsert_event_rows(pd.DataFrame(), table="event.bad_table", service="test")
    except ValueError as exc:
        assert "Unsupported event table" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_upsert_event_rows_fills_missing_optional_columns(monkeypatch):
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

    frame = pd.DataFrame([{"event_id": "survey:1", "asset_id": "CN:SZ:000001", "ts_code": "000001.SZ"}])
    upsert_event_rows(frame, table="event.institution_survey", service="test")

    assert calls[0][1][0][0:3] == ("survey:1", "CN:SZ:000001", "000001.SZ")
    assert calls[0][1][0][3:9] == (None, None, None, None, None, None)


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
