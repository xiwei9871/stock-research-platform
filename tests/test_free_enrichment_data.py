import json

import pandas as pd

from stock_research.free_enrichment_data import (
    DATASETS,
    DatasetRunResult,
    build_event_id,
    normalize_earnings_express_rows,
    normalize_earnings_forecast_rows,
    normalize_institution_survey_rows,
    normalize_main_business_rows,
    normalize_repurchase_rows,
    normalize_shareholder_count_rows,
    normalize_shareholder_trade_rows,
    normalize_top_holder_rows,
    normalize_ts_code,
    payload_hash,
    run_free_enrichment_backfill,
    run_lhb_backfill,
    ts_code_to_asset_id,
    upsert_event_rows,
    upsert_main_business_rows,
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


def test_normalize_earnings_forecast_rows():
    raw = pd.DataFrame([{"代码": "600000", "公告日期": "2025-04-10", "报告期": "2025-03-31", "预告类型": "预增", "净利润下限": 10}])
    frame = normalize_earnings_forecast_rows(raw, endpoint="stock_yjyg_em")
    assert frame.iloc[0]["event_id"].startswith("earnings_forecast:")
    assert frame.iloc[0]["forecast_type"] == "预增"
    assert frame.iloc[0]["report_period"] == "2025-03-31"


def test_normalize_earnings_express_rows():
    raw = pd.DataFrame([{"代码": "000001", "公告日期": "2025-04-15", "报告期": "2025-03-31", "营业收入": 100, "净利润": 20}])
    frame = normalize_earnings_express_rows(raw, endpoint="stock_yjkb_em")
    assert frame.iloc[0]["event_id"].startswith("earnings_express:")
    assert frame.iloc[0]["revenue"] == 100
    assert frame.iloc[0]["np_parent"] == 20


def test_normalize_main_business_rows():
    raw = pd.DataFrame([{"代码": "600000", "报告期": "2025-06-30", "分类方向": "按产品", "主营构成": "贷款", "主营收入": 1000, "毛利率": 40}])
    frame = normalize_main_business_rows(raw, endpoint="stock_zygc_em")
    assert frame.iloc[0]["classify_type"] == "按产品"
    assert frame.iloc[0]["item_name"] == "贷款"


def test_normalize_main_business_rows_filters_empty_and_invalid_rows():
    assert normalize_main_business_rows(pd.DataFrame(), endpoint="x").empty

    invalid = normalize_main_business_rows(
        pd.DataFrame(
            [
                {"代码": "bad", "报告期": "2025-06-30", "分类方向": "按产品", "主营构成": "贷款"},
                {"代码": "600000", "分类方向": "按产品", "主营构成": "贷款"},
                {"代码": "600000", "报告期": "2025-06-30", "分类方向": "", "主营构成": "贷款"},
                {"代码": "600000", "报告期": "2025-06-30", "分类方向": "按产品", "主营构成": " "},
            ]
        ),
        endpoint="x",
    )

    assert invalid.empty


def test_normalize_earnings_forecast_sparse_rows_use_payload_hash_and_require_announcement_date():
    frame = normalize_earnings_forecast_rows(
        pd.DataFrame(
            [
                {"代码": "600000", "公告日期": "2025-04-10", "报告期": "2025-03-31", "预告类型": "预增", "净利润下限": 10},
                {"代码": "600000", "公告日期": "2025-04-10", "报告期": "2025-03-31", "预告类型": "预增", "净利润下限": 20},
                {"代码": "600000", "报告期": "2025-03-31", "预告类型": "预增", "净利润下限": 30},
            ]
        ),
        endpoint="stock_yjyg_em",
    )

    assert len(frame) == 2
    assert frame["event_id"].nunique() == 2


def test_event_normalizers_keep_sparse_rows_with_distinct_event_ids():
    repurchase = normalize_repurchase_rows(
        pd.DataFrame(
            [
                {"代码": "600000", "已回购金额": 1000},
                {"代码": "600000", "已回购金额": 2000},
            ]
        ),
        endpoint="stock_repurchase_em",
    )
    survey = normalize_institution_survey_rows(
        pd.DataFrame(
            [
                {"代码": "000001", "机构数量": 1},
                {"代码": "000001", "机构数量": 2},
            ]
        ),
        endpoint="stock_jgdy_detail_em",
    )
    trade = normalize_shareholder_trade_rows(
        pd.DataFrame(
            [
                {"代码": "000001", "变动数量": 10},
                {"代码": "000001", "变动数量": 20},
            ]
        ),
        endpoint="stock_ggcg_em",
    )

    assert len(repurchase) == 2
    assert repurchase["event_id"].nunique() == 2
    assert len(survey) == 2
    assert survey["event_id"].nunique() == 2
    assert len(trade) == 2
    assert trade["event_id"].nunique() == 2


def test_event_normalizers_filter_invalid_assets_and_empty_frames():
    assert normalize_repurchase_rows(pd.DataFrame(), endpoint="x").empty
    assert normalize_institution_survey_rows(pd.DataFrame(), endpoint="x").empty
    assert normalize_shareholder_trade_rows(pd.DataFrame(), endpoint="x").empty
    assert normalize_repurchase_rows(pd.DataFrame([{"代码": "bad", "公告日期": "2025-01-01"}]), endpoint="x").empty


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


def test_upsert_event_rows_allows_earnings_tables(monkeypatch):
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

    forecast = pd.DataFrame(
        [
            {
                "event_id": "earnings_forecast:1",
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "announcement_date": "2025-04-10",
                "report_period": "2025-03-31",
                "forecast_type": "预增",
                "payload_hash": "h1",
            }
        ]
    )
    express = pd.DataFrame(
        [
            {
                "event_id": "earnings_express:1",
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "announcement_date": "2025-04-15",
                "report_period": "2025-03-31",
                "revenue": 100,
                "np_parent": 20,
                "payload_hash": "h2",
            }
        ]
    )

    upsert_event_rows(forecast, table="event.earnings_forecast", service="test")
    upsert_event_rows(express, table="event.earnings_express", service="test")

    assert "INSERT INTO event.earnings_forecast" in calls[0][0]
    assert "INSERT INTO event.earnings_express" in calls[1][0]
    assert calls[0][1][0][0:6] == (
        "earnings_forecast:1",
        "CN:SH:600000",
        "600000.SH",
        "2025-04-10",
        "2025-03-31",
        "预增",
    )
    assert calls[1][1][0][0:6] == (
        "earnings_express:1",
        "CN:SZ:000001",
        "000001.SZ",
        "2025-04-15",
        "2025-03-31",
        100,
    )


def test_upsert_main_business_rows_uses_expected_table_conflict_key_and_order(monkeypatch):
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

    frame = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_period": "2025-06-30",
                "classify_type": "按产品",
                "item_name": "贷款",
                "revenue": 1000,
                "revenue_ratio": 50,
                "cost": 600,
                "gross_profit": 400,
                "gross_margin": 40,
                "source": "akshare",
                "source_endpoint": "stock_zygc_em",
                "payload_hash": "h",
            }
        ]
    )

    upsert_main_business_rows(frame, service="test")

    sql, rows = calls[0]
    assert "INSERT INTO finance.main_business_composition" in sql
    assert "ON CONFLICT (asset_id, report_period, classify_type, item_name, source)" in sql
    assert rows[0] == (
        "CN:SH:600000",
        "600000.SH",
        "2025-06-30",
        "按产品",
        "贷款",
        1000,
        50,
        600,
        400,
        40,
        "akshare",
        "stock_zygc_em",
        "h",
    )


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


def test_run_free_enrichment_backfill_forwards_lhb_args_and_writes_structured_summary(
    monkeypatch, tmp_path, capsys
):
    calls = []

    def fake_lhb(**kwargs):
        calls.append(kwargs)
        return DatasetRunResult(dataset="lhb", fetched_rows=2, normalized_rows=2, upserted_rows=2)

    monkeypatch.setattr("stock_research.free_enrichment_data.run_lhb_backfill", fake_lhb)

    result = run_free_enrichment_backfill(
        dataset="lhb",
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        batch_size=7,
        sleep_seconds=0.5,
        limit=3,
        dry_run=True,
        service="test",
    )

    assert calls[0]["start_date"] == "2025-01-01"
    assert calls[0]["end_date"] == "2025-01-31"
    assert calls[0]["dry_run"] is True
    assert calls[0]["service"] == "test"
    assert result["summary_path"].endswith("run_summary.json")
    assert result["coverage_path"].endswith("dataset_coverage.csv")
    assert result["failures_path"].endswith("dataset_failures.csv")
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "dataset_coverage.csv").exists()
    assert (tmp_path / "dataset_failures.csv").exists()
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["params"]["batch_size"] == 7
    assert summary["params"]["sleep_seconds"] == 0.5
    assert summary["params"]["limit"] == 3
    assert summary["params"]["limit_applies_to_placeholders"] is False
    assert summary["results"][0]["status"] == "success"
    assert "free_enrichment_batch|dataset=lhb|batch=1/1|dry_run=True|status=success" in capsys.readouterr().out


def test_run_free_enrichment_backfill_all_marks_unimplemented_datasets_as_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.run_lhb_backfill",
        lambda **kwargs: DatasetRunResult(dataset="lhb", upserted_rows=1),
    )

    result = run_free_enrichment_backfill(
        dataset="all",
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        sleep_seconds=0,
        service="test",
    )

    assert [item.dataset for item in result["results"]] == list(DATASETS)
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))
    statuses = {item["dataset"]: item["status"] for item in summary["results"]}
    assert statuses["lhb"] == "success"
    assert statuses["holder"] == "not_implemented"
    assert summary["results"][1]["message"] == "dataset runner not implemented"
    failures = pd.read_csv(tmp_path / "dataset_failures.csv")
    assert set(failures["dataset"]) == set(DATASETS) - {"lhb"}
    assert set(failures["error"]) == {"dataset runner not implemented"}
    coverage = pd.read_csv(tmp_path / "dataset_coverage.csv")
    assert coverage["dataset"].tolist() == list(DATASETS)
    assert "status" in coverage.columns
    assert "message" in coverage.columns
    assert coverage.loc[coverage["dataset"].eq("lhb"), "row_count"].iloc[0] == 1


def test_run_free_enrichment_backfill_captures_runner_exception(monkeypatch, tmp_path):
    def boom(**kwargs):
        raise RuntimeError("akshare down")

    monkeypatch.setattr("stock_research.free_enrichment_data.run_lhb_backfill", boom)

    result = run_free_enrichment_backfill(
        dataset="lhb",
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        sleep_seconds=0,
        service="test",
    )

    assert result["results"][0].status == "failed"
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["results"][0]["status"] == "failed"
    assert summary["results"][0]["message"] == "akshare down"
    failures = pd.read_csv(tmp_path / "dataset_failures.csv")
    assert failures.iloc[0]["dataset"] == "lhb"
    assert failures.iloc[0]["request"] == "dataset"
    assert failures.iloc[0]["error"] == "akshare down"


def test_run_free_enrichment_backfill_invalid_dataset_does_not_create_output_dir(tmp_path):
    out = tmp_path / "new-output"

    try:
        run_free_enrichment_backfill(
            dataset="bad",
            start_date="2025-01-01",
            end_date="2025-01-31",
            output_dir=out,
            sleep_seconds=0,
            service="test",
        )
    except ValueError as exc:
        assert "Unsupported free enrichment dataset: bad" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    assert not out.exists()
