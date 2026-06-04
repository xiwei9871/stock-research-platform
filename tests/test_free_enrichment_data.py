import json

import pandas as pd

from stock_research.free_enrichment_data import (
    DATASETS,
    DatasetRunResult,
    _fetch_stock_jgdy_detail_em_robust,
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
    run_express_backfill,
    run_forecast_backfill,
    run_free_enrichment_backfill,
    run_holder_backfill,
    run_lhb_backfill,
    run_mainbiz_backfill,
    run_repurchase_backfill,
    run_survey_backfill,
    ts_code_to_akshare_symbol,
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


def test_normalize_shareholder_count_rows_maps_actual_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "代码": "600000",
                "股东户数统计截止日": "2025-03-31",
                "股东户数公告日期": "2025-04-20",
                "股东户数-本次": 100000,
                "股东户数-增减": -1000,
                "股东户数-增减比例": -1.0,
            }
        ]
    )

    frame = normalize_shareholder_count_rows(raw, endpoint="stock_zh_a_gdhs_detail_em")

    assert frame.iloc[0]["report_date"] == "2025-03-31"
    assert frame.iloc[0]["announcement_date"] == "2025-04-20"
    assert frame.iloc[0]["shareholder_count"] == 100000
    assert frame.iloc[0]["shareholder_count_change"] == -1000
    assert frame.iloc[0]["shareholder_count_change_pct"] == -1.0


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


def test_normalize_top_holder_rows_maps_actual_top10_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "股票代码": "600000",
                "报告期": "2025-03-31",
                "股东名称": "上海国际集团有限公司",
                "股份类型": "流通A股",
                "持股数": 123,
                "占总股本持股比例": 1.2,
                "名次": 1,
            }
        ]
    )

    frame = normalize_top_holder_rows(raw, endpoint="stock_gdfx_top_10_em")

    assert frame.iloc[0]["holder_type"] == "流通A股"
    assert frame.iloc[0]["hold_ratio"] == 1.2


def test_normalize_top_holder_rows_maps_actual_free_top10_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "股票代码": "600000",
                "报告期": "2025-03-31",
                "股东名称": "香港中央结算有限公司",
                "股东性质": "其它",
                "股份类型": "流通A股",
                "持股数": 456,
                "占总流通股本持股比例": 2.3,
                "名次": 1,
            }
        ]
    )

    frame = normalize_top_holder_rows(raw, endpoint="stock_gdfx_free_top_10_em")

    assert frame.iloc[0]["holder_type"] == "其它"
    assert frame.iloc[0]["hold_ratio"] == 2.3


def test_normalize_repurchase_rows_builds_event_id():
    raw = pd.DataFrame([{"代码": "600000", "公告日期": "2025-02-01", "进度": "实施", "已回购金额": 1000}])
    frame = normalize_repurchase_rows(raw, endpoint="stock_repurchase_em")
    assert frame.iloc[0]["event_id"].startswith("repurchase:")
    assert frame.iloc[0]["asset_id"] == "CN:SH:600000"
    assert frame.iloc[0]["announcement_date"] == "2025-02-01"


def test_normalize_repurchase_rows_maps_actual_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "股票代码": "600000",
                "最新公告日期": "2025-02-01",
                "回购起始时间": "2025-01-15",
                "实施进度": "实施中",
                "已回购金额": 1000,
                "计划回购金额区间-下限": 500,
                "计划回购金额区间-上限": 1500,
                "已回购股份价格区间-下限": 8.5,
                "已回购股份价格区间-上限": 10.5,
            }
        ]
    )

    frame = normalize_repurchase_rows(raw, endpoint="stock_repurchase_em")

    assert frame.iloc[0]["announcement_date"] == "2025-02-01"
    assert frame.iloc[0]["progress_date"] == "2025-01-15"
    assert frame.iloc[0]["progress"] == "实施中"
    assert frame.iloc[0]["repurchase_amount"] == 1000
    assert frame.iloc[0]["repurchase_amount_min"] == 500
    assert frame.iloc[0]["repurchase_amount_max"] == 1500
    assert frame.iloc[0]["repurchase_price_min"] == 8.5
    assert frame.iloc[0]["repurchase_price_max"] == 10.5


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


def test_normalize_shareholder_trade_rows_maps_actual_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "代码": "000001",
                "股东名称": "holder",
                "持股变动信息-增减": "减持",
                "持股变动信息-变动数量": 10,
                "持股变动信息-占总股本比例": 0.1,
                "变动截止日": "2025-04-01",
                "公告日": "2025-04-10",
            }
        ]
    )

    frame = normalize_shareholder_trade_rows(raw, endpoint="stock_ggcg_em")

    assert frame.iloc[0]["trade_date"] == "2025-04-01"
    assert frame.iloc[0]["announcement_date"] == "2025-04-10"
    assert frame.iloc[0]["trade_type"] == "减持"
    assert frame.iloc[0]["trade_amount"] == 10
    assert frame.iloc[0]["trade_ratio"] == 0.1


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


def test_normalize_earnings_express_rows_maps_actual_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "股票代码": "000001",
                "公告日期": "2025-04-15",
                "报告期": "2025-03-31",
                "每股收益": 1.2,
                "营业收入-营业收入": 100,
                "营业收入-同比增长": 10,
                "净利润-净利润": 20,
                "净利润-同比增长": 5,
                "净资产收益率": 8,
            }
        ]
    )

    frame = normalize_earnings_express_rows(raw, endpoint="stock_yjkb_em")

    assert frame.iloc[0]["revenue"] == 100
    assert frame.iloc[0]["revenue_yoy"] == 10
    assert frame.iloc[0]["np_parent"] == 20
    assert frame.iloc[0]["np_parent_yoy"] == 5
    assert frame.iloc[0]["eps_basic"] == 1.2
    assert frame.iloc[0]["roe_weighted"] == 8


def test_normalize_main_business_rows():
    raw = pd.DataFrame([{"代码": "600000", "报告期": "2025-06-30", "分类方向": "按产品", "主营构成": "贷款", "主营收入": 1000, "毛利率": 40}])
    frame = normalize_main_business_rows(raw, endpoint="stock_zygc_em")
    assert frame.iloc[0]["classify_type"] == "按产品"
    assert frame.iloc[0]["item_name"] == "贷款"


def test_normalize_main_business_rows_maps_actual_akshare_columns():
    raw = pd.DataFrame(
        [
            {
                "股票代码": "600000",
                "报告日期": "2025-06-30",
                "分类类型": "按产品",
                "主营构成": "贷款",
                "主营收入": 1000,
                "收入比例": 50,
                "主营成本": 600,
                "主营利润": 400,
                "毛利率": 40,
            }
        ]
    )

    frame = normalize_main_business_rows(raw, endpoint="stock_zygc_em")

    assert frame.iloc[0]["report_period"] == "2025-06-30"
    assert frame.iloc[0]["classify_type"] == "按产品"
    assert frame.iloc[0]["revenue"] == 1000
    assert frame.iloc[0]["cost"] == 600


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


def test_ts_code_to_akshare_symbol_converts_ts_code():
    assert ts_code_to_akshare_symbol("600000.SH") == "SH600000"
    assert ts_code_to_akshare_symbol("000001.SZ") == "SZ000001"
    assert ts_code_to_akshare_symbol("bad") == ""


def test_run_holder_backfill_fetches_per_stock_periods_and_shareholder_trade(monkeypatch):
    calls = []
    upserts = []

    class FakeClient:
        def stock_zh_a_gdhs_detail_em(self, symbol):
            calls.append(("gdhs", symbol))
            return pd.DataFrame(
                [
                    {
                        "代码": symbol[-6:],
                        "股东户数统计截止日": "2025-03-31",
                        "股东户数公告日期": "2025-04-20",
                        "股东户数-本次": 100,
                    },
                    {
                        "代码": symbol[-6:],
                        "股东户数统计截止日": "2024-12-31",
                        "股东户数公告日期": "2025-01-02",
                        "股东户数-本次": 90,
                    },
                ]
            )

        def stock_gdfx_top_10_em(self, symbol, date):
            calls.append(("top10", symbol, date))
            return pd.DataFrame([{"股东名称": "top holder", "持股数": 10, "名次": 1}])

        def stock_gdfx_free_top_10_em(self, symbol, date):
            calls.append(("free_top10", symbol, date))
            return pd.DataFrame([{"股东名称": "float holder", "持股数": 5, "名次": 1}])

        def stock_ggcg_em(self, symbol):
            calls.append(("trade", symbol))
            return pd.DataFrame(
                [
                    {
                        "代码": "600000",
                        "股东名称": "holder",
                        "持股变动信息-增减": "减持",
                        "持股变动信息-变动数量": 1,
                        "变动截止日": "2025-04-01",
                        "公告日": "2025-04-10",
                    },
                    {
                        "代码": "600000",
                        "股东名称": "holder",
                        "持股变动信息-增减": "增持",
                        "持股变动信息-变动数量": 2,
                        "变动截止日": "2024-12-01",
                        "公告日": "2024-12-10",
                    },
                ]
            )

    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_shareholder_count_rows",
        lambda frame, service: upserts.append(("shareholder_count", frame.copy(), service)) or len(frame),
    )
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_top_holder_rows",
        lambda frame, table, service: upserts.append((table, frame.copy(), service)) or len(frame),
    )
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_event_rows",
        lambda frame, table, service: upserts.append((table, frame.copy(), service)) or len(frame),
    )

    result = run_holder_backfill(
        start_date="2025-01-01",
        end_date="2025-06-30",
        batch_size=1,
        sleep_seconds=0,
        limit=1,
        dry_run=False,
        service="test",
        client=FakeClient(),
        ts_codes=["600000.SH", "000001.SZ"],
    )

    assert ("gdhs", "600000") in calls
    assert ("top10", "SH600000", "20250331") in calls
    assert ("top10", "SH600000", "20250630") in calls
    assert ("free_top10", "SH600000", "20250331") in calls
    assert ("trade", "全部") in calls
    assert not any(call == ("gdhs", "000001") for call in calls)
    assert result.status == "success"
    assert result.upserted_rows == 6
    assert upserts[0][0] == "shareholder_count"
    assert upserts[0][1]["report_date"].tolist() == ["2025-03-31"]
    assert upserts[1][0] == "fundamental.top10_holder"
    assert set(upserts[1][1]["report_period"]) == {"2025-03-31", "2025-06-30"}
    assert upserts[2][0] == "fundamental.top10_float_holder"
    assert upserts[3][0] == "event.shareholder_trade"
    assert upserts[3][1]["trade_date"].tolist() == ["2025-04-01"]


def test_run_holder_backfill_reports_universe_loader_failure(monkeypatch):
    def fail_loader(**kwargs):
        raise RuntimeError("asset master unavailable")

    monkeypatch.setattr("stock_research.free_enrichment_data.load_free_enrichment_ts_codes", fail_loader)

    result = run_holder_backfill(
        start_date="2025-01-01",
        end_date="2025-06-30",
        batch_size=1,
        sleep_seconds=0,
        dry_run=True,
        service="test",
        client=object(),
    )

    assert result.status == "failed"
    assert result.failed_requests == 1
    assert "asset master unavailable" in result.message


def test_run_mainbiz_backfill_allows_explicit_empty_ts_codes(monkeypatch):
    def fail_loader(**kwargs):
        raise AssertionError("loader should not be called for explicit empty ts_codes")

    monkeypatch.setattr("stock_research.free_enrichment_data.load_free_enrichment_ts_codes", fail_loader)
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_main_business_rows",
        lambda frame, service: len(frame),
    )

    result = run_mainbiz_backfill(
        start_date="2025-01-01",
        end_date="2025-06-30",
        batch_size=1,
        sleep_seconds=0,
        dry_run=False,
        service="test",
        client=object(),
        ts_codes=[],
    )

    assert result.status == "success"
    assert result.failed_requests == 0
    assert result.normalized_rows == 0


def test_run_forecast_and_express_backfill_use_quarter_periods(monkeypatch):
    calls = []
    upserts = []

    class FakeClient:
        def stock_yjyg_em(self, date):
            calls.append(("forecast", date))
            return pd.DataFrame([{"股票代码": "600000", "公告日期": "2025-04-15", "预告类型": "预增"}])

        def stock_yjkb_em(self, date):
            calls.append(("express", date))
            return pd.DataFrame(
                [{"股票代码": "600000", "公告日期": "2025-04-20", "营业收入-营业收入": 100, "净利润-净利润": 20}]
            )

    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_event_rows",
        lambda frame, table, service: upserts.append((table, frame.copy(), service)) or len(frame),
    )

    forecast = run_forecast_backfill(
        start_date="2025-04-01",
        end_date="2025-12-31",
        batch_size=2,
        sleep_seconds=0,
        limit=None,
        dry_run=False,
        service="test",
        client=FakeClient(),
    )
    express = run_express_backfill(
        start_date="2025-04-01",
        end_date="2025-12-31",
        batch_size=2,
        sleep_seconds=0,
        limit=2,
        dry_run=False,
        service="test",
        client=FakeClient(),
    )

    assert [call for call in calls if call[0] == "forecast"] == [
        ("forecast", "20250630"),
        ("forecast", "20250930"),
        ("forecast", "20251231"),
    ]
    assert [call for call in calls if call[0] == "express"] == [("express", "20250630"), ("express", "20250930")]
    assert forecast.upserted_rows == 3
    assert express.upserted_rows == 2
    assert upserts[0][0] == "event.earnings_forecast"
    assert upserts[0][1]["report_period"].tolist() == ["2025-06-30", "2025-09-30", "2025-12-31"]
    assert upserts[1][0] == "event.earnings_express"
    assert upserts[1][1]["report_period"].tolist() == ["2025-06-30", "2025-09-30"]


def test_run_repurchase_survey_and_mainbiz_backfills_call_expected_endpoints(monkeypatch):
    calls = []
    upserts = []

    class FakeClient:
        def stock_repurchase_em(self):
            calls.append(("repurchase",))
            return pd.DataFrame(
                [{"股票代码": "600000", "最新公告日期": "2025-02-01", "实施进度": "实施中", "已回购金额": 1000}]
            )

        def stock_jgdy_detail_em(self, date):
            calls.append(("survey", date))
            return pd.DataFrame([{"代码": "000001", "调研机构": "org", "调研日期": "2025-05-01", "公告日期": "2025-05-02"}])

        def stock_zygc_em(self, symbol):
            calls.append(("mainbiz", symbol))
            return pd.DataFrame(
                [
                    {
                        "股票代码": "600000",
                        "报告日期": "2025-06-30",
                        "分类类型": "按产品",
                        "主营构成": "贷款",
                        "主营收入": 1000,
                    }
                ]
            )

    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_event_rows",
        lambda frame, table, service: upserts.append((table, frame.copy(), service)) or len(frame),
    )
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_main_business_rows",
        lambda frame, service: upserts.append(("finance.main_business_composition", frame.copy(), service)) or len(frame),
    )

    repurchase = run_repurchase_backfill(
        start_date="2025-01-01",
        end_date="2025-12-31",
        batch_size=10,
        sleep_seconds=0,
        limit=1,
        dry_run=False,
        service="test",
        client=FakeClient(),
    )
    survey = run_survey_backfill(
        start_date="2025-05-01",
        end_date="2025-05-31",
        batch_size=10,
        sleep_seconds=0,
        limit=None,
        dry_run=False,
        service="test",
        client=FakeClient(),
    )
    mainbiz = run_mainbiz_backfill(
        start_date="2025-01-01",
        end_date="2025-12-31",
        batch_size=1,
        sleep_seconds=0,
        limit=1,
        dry_run=False,
        service="test",
        client=FakeClient(),
        ts_codes=["600000.SH", "000001.SZ"],
    )

    assert ("repurchase",) in calls
    assert ("survey", "20250430") in calls
    assert ("mainbiz", "SH600000") in calls
    assert not any(call == ("mainbiz", "SZ000001") for call in calls)
    assert repurchase.upserted_rows == 1
    assert survey.upserted_rows == 1
    assert mainbiz.upserted_rows == 1
    assert [item[0] for item in upserts] == [
        "event.stock_repurchase",
        "event.institution_survey",
        "finance.main_business_composition",
    ]


def test_run_survey_backfill_queries_day_before_start_date(monkeypatch):
    calls = []

    class FakeClient:
        def stock_jgdy_detail_em(self, date):
            calls.append(date)
            return pd.DataFrame([{"代码": "000001", "调研日期": "2025-05-01"}])

    monkeypatch.setattr(
        "stock_research.free_enrichment_data.upsert_event_rows",
        lambda frame, table, service: len(frame),
    )

    result = run_survey_backfill(
        start_date="2025-05-01",
        end_date="2025-05-31",
        batch_size=10,
        sleep_seconds=0,
        limit=None,
        dry_run=False,
        service="test",
        client=FakeClient(),
    )

    assert calls == ["20250430"]
    assert result.upserted_rows == 1


def test_fetch_stock_jgdy_detail_em_robust_retries_failed_pages():
    calls = []

    class FakeResponse:
        def __init__(self, page):
            self.page = page

        def json(self):
            return {
                "result": {
                    "pages": 2,
                    "data": [
                        {
                            "SECUCODE": f"00000{self.page}.SZ",
                            "SECURITY_CODE": f"00000{self.page}",
                            "SECURITY_NAME_ABBR": "测试",
                            "NOTICE_DATE": "2025-05-02",
                            "RECEIVE_START_DATE": "2025-05-01",
                            "RECEIVE_OBJECT": "机构",
                            "RECEIVE_PLACE": "线上",
                            "RECEIVE_WAY_EXPLAIN": "电话会议",
                            "INVESTIGATORS": "analyst",
                            "RECEPTIONIST": "ir",
                            "ORG_TYPE": "基金",
                            "CLOSE_PRICE": 10,
                            "CHANGE_RATE": 1,
                        }
                    ],
                }
            }

    attempts = {"2": 0}

    def fake_get(url, params, timeout):
        del url, timeout
        page = str(params["pageNumber"])
        calls.append(page)
        if page == "2" and attempts["2"] == 0:
            attempts["2"] += 1
            raise RuntimeError("temporary ssl eof")
        return FakeResponse(page)

    frame = _fetch_stock_jgdy_detail_em_robust(
        date="20250430",
        request_get=fake_get,
        max_retries=2,
        retry_sleep_seconds=0,
    )

    assert calls == ["1", "1", "2", "2"]
    assert frame["代码"].tolist() == ["000001", "000002"]
    assert frame["调研日期"].tolist() == [pd.Timestamp("2025-05-01").date(), pd.Timestamp("2025-05-01").date()]


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
    assert summary["params"]["batch_controls_applied_by_dataset"]["lhb"] is False
    assert summary["params"]["ignored_params_by_dataset"]["lhb"] == ["batch_size", "sleep_seconds", "limit"]
    assert summary["results"][0]["status"] == "success"
    out = capsys.readouterr().out
    assert "free_enrichment_batch|dataset=lhb|batch=1/1|dry_run=True|status=success" in out
    assert "batch_controls_applied=False|ignored_params=batch_size,sleep_seconds,limit" in out


def test_run_free_enrichment_backfill_all_dispatches_real_datasets_and_reports_batch_controls(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.run_lhb_backfill",
        lambda **kwargs: DatasetRunResult(dataset="lhb", upserted_rows=1),
    )
    for dataset_name in DATASETS:
        if dataset_name == "lhb":
            continue
        monkeypatch.setattr(
            f"stock_research.free_enrichment_data.run_{dataset_name}_backfill",
            lambda dataset_name=dataset_name, **kwargs: DatasetRunResult(dataset=dataset_name, upserted_rows=2),
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
    assert set(statuses.values()) == {"success"}
    assert "not_implemented" not in statuses.values()
    assert summary["params"]["batch_controls_applied_by_dataset"]["lhb"] is False
    assert summary["params"]["ignored_params_by_dataset"]["lhb"] == ["batch_size", "sleep_seconds"]
    assert summary["params"]["batch_controls_applied_by_dataset"]["holder"] == "partial"
    assert summary["params"]["ignored_params_by_dataset"]["holder"] == ["batch_size", "sleep_seconds"]
    assert summary["params"]["uncontrolled_request_units_by_dataset"]["holder"] == ["stock_ggcg_em(symbol=全部)"]
    assert summary["params"]["batch_controls_applied_by_dataset"]["repurchase"] is False
    assert summary["params"]["ignored_params_by_dataset"]["repurchase"] == ["batch_size", "sleep_seconds"]
    failures = pd.read_csv(tmp_path / "dataset_failures.csv")
    assert failures.empty
    coverage = pd.read_csv(tmp_path / "dataset_coverage.csv")
    assert coverage["dataset"].tolist() == list(DATASETS)
    assert "status" in coverage.columns
    assert "message" in coverage.columns
    assert coverage.loc[coverage["dataset"].eq("lhb"), "row_count"].iloc[0] == 1
    out = capsys.readouterr().out
    assert "free_enrichment_batch|dataset=holder" in out
    assert "dataset=holder" in out and "batch_controls_applied=partial|ignored_params=batch_size,sleep_seconds" in out
    assert "uncontrolled_request_units=stock_ggcg_em(symbol=全部)" in out
    assert "dataset=repurchase" in out and "batch_controls_applied=False|ignored_params=batch_size,sleep_seconds" in out


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
    assert len(failures) == 1


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
