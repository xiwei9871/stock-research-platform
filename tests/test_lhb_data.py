from pathlib import Path

import pandas as pd

from stock_research import cli
import stock_research.lhb_data as lhb_data


def test_normalize_top_list_rows():
    frame = lhb_data.normalize_top_list_rows(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260512",
                    "ts_code": "600726.SH",
                    "name": "华电能源",
                    "close": 10.5,
                    "pct_change": 9.98,
                    "turnover_rate": 12.3,
                    "amount": 123456789,
                    "l_sell": 1000,
                    "l_buy": 1200,
                    "l_amount": 2200,
                    "net_amount": 200,
                    "net_rate": 0.02,
                    "amount_rate": 0.15,
                    "float_values": 1000000,
                    "reason": "日涨幅偏离值达7%",
                }
            ]
        ),
        source="tushare",
    )

    assert frame.iloc[0]["trade_date"] == "2026-05-12"
    assert frame.iloc[0]["ts_code"] == "600726.SH"
    assert frame.iloc[0]["source"] == "tushare"


def test_upsert_lhb_rows_executes_sql(monkeypatch):
    executed = []

    class Conn:
        pass

    class Context:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(lhb_data, "connect", lambda service: Context(Conn()))
    monkeypatch.setattr(lhb_data, "execute_many", lambda conn, sql, rows: executed.append((sql, list(rows))))

    top_list = lhb_data.normalize_top_list_rows(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260512",
                    "ts_code": "600726.SH",
                    "name": "华电能源",
                    "close": 10.5,
                    "pct_change": 9.98,
                    "turnover_rate": 12.3,
                    "amount": 123456789,
                    "l_sell": 1000,
                    "l_buy": 1200,
                    "l_amount": 2200,
                    "net_amount": 200,
                    "net_rate": 0.02,
                    "amount_rate": 0.15,
                    "float_values": 1000000,
                    "reason": "日涨幅偏离值达7%",
                }
            ]
        ),
        source="tushare",
    )
    top_inst = lhb_data.normalize_top_inst_rows(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260512",
                    "ts_code": "600726.SH",
                    "exalter": "机构专用",
                    "buy": 500,
                    "buy_rate": 0.1,
                    "sell": 100,
                    "sell_rate": 0.02,
                    "net_buy": 400,
                    "reason": "日涨幅偏离值达7%",
                }
            ]
        ),
        source="tushare",
    )

    lhb_data.upsert_lhb_sample(top_list=top_list, top_inst=top_inst)

    assert len(executed) == 2
    assert "market.lhb_top_list_daily" in executed[0][0]
    assert "market.lhb_top_inst_daily" in executed[1][0]


def test_build_lhb_event_features_daily():
    top_list = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-09",
                "ts_code": "600726.SH",
                "name": "华电能源",
                "close": 9.6,
                "pct_change": 10.01,
                "turnover_rate": 8.0,
                "amount": 10000.0,
                "l_sell": 900.0,
                "l_buy": 1200.0,
                "l_amount": 2100.0,
                "net_amount": 300.0,
                "net_rate": 0.03,
                "amount_rate": 0.21,
                "float_values": 1000000.0,
                "reason": "日涨幅偏离值达7%",
                "source": "akshare",
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "name": "华电能源",
                "close": 10.5,
                "pct_change": 9.98,
                "turnover_rate": 12.3,
                "amount": 12000.0,
                "l_sell": 1000.0,
                "l_buy": 1500.0,
                "l_amount": 2500.0,
                "net_amount": 500.0,
                "net_rate": 0.04,
                "amount_rate": 0.20,
                "float_values": 1000000.0,
                "reason": "日涨幅偏离值达7%",
                "source": "akshare",
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "000017.SZ",
                "name": "深中华A",
                "close": 15.2,
                "pct_change": 3.0,
                "turnover_rate": 25.0,
                "amount": 8000.0,
                "l_sell": 1300.0,
                "l_buy": 900.0,
                "l_amount": 2200.0,
                "net_amount": -400.0,
                "net_rate": -0.05,
                "amount_rate": 0.27,
                "float_values": 900000.0,
                "reason": "日换手率达20%",
                "source": "akshare",
            },
        ]
    )
    top_inst = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "exalter": "机构汇总",
                "buy": 800.0,
                "buy_rate": None,
                "sell": 300.0,
                "sell_rate": None,
                "net_buy": 500.0,
                "reason": "日涨幅偏离值达7%",
                "source": "akshare",
            }
        ]
    )

    features = lhb_data.build_lhb_event_features_daily(top_list=top_list, top_inst=top_inst)

    assert len(features) == 3
    row = features[(features["trade_date"] == "2026-05-12") & (features["ts_code"] == "600726.SH")].iloc[0]
    assert bool(row["on_lhb"]) is True
    assert row["lhb_net_buy_amount"] == 500.0
    assert row["institution_net_buy"] == 500.0
    assert row["repeat_on_list_count_3d"] == 2
    assert bool(row["lhb_after_limit_up"]) is True
    assert row["top_seat_concentration"] > 0

    weak_row = features[(features["trade_date"] == "2026-05-12") & (features["ts_code"] == "000017.SZ")].iloc[0]
    assert weak_row["lhb_one_day_pump_risk"] > 0
    assert bool(weak_row["lhb_after_limit_up"]) is False


def test_upsert_lhb_event_features_executes_sql(monkeypatch):
    executed = []

    class Conn:
        pass

    class Context:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(lhb_data, "connect", lambda service: Context(Conn()))
    monkeypatch.setattr(lhb_data, "execute_many", lambda conn, sql, rows: executed.append((sql, list(rows))))

    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "on_lhb": True,
                "lhb_reason": "日涨幅偏离值达7%",
                "lhb_net_buy_amount": 500.0,
                "lhb_net_buy_ratio": 0.04,
                "lhb_buy_amount": 1500.0,
                "lhb_sell_amount": 1000.0,
                "institution_net_buy": 500.0,
                "top_seat_concentration": 0.2,
                "repeat_on_list_count_3d": 2,
                "repeat_on_list_count_5d": 2,
                "lhb_after_limit_up": True,
                "lhb_after_break_limit": False,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.5,
                "source": "akshare",
            }
        ]
    )

    lhb_data.upsert_lhb_event_features_daily(features=features)

    assert len(executed) == 1
    assert "factor.lhb_event_features_daily" in executed[0][0]


def test_build_dragon_case_lhb_alignment_audit(tmp_path):
    curated = pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "case_type": "second_wave",
                "first_limit_up_date": "2026-05-08",
                "break_limit_date": "2026-05-12",
                "reversal_date": "",
                "second_wave_start_date": "2026-05-13",
                "peak_date": "2026-05-14",
                "a_kill_start_date": "",
            }
        ]
    )
    top_list = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "reason": "日涨幅偏离值达7%",
                "net_amount": 200.0,
            }
        ]
    )
    top_inst = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "net_buy": 400.0,
            }
        ]
    )

    audit = lhb_data.build_dragon_case_lhb_alignment_audit(curated, top_list, top_inst, output_dir=tmp_path)

    assert Path(audit["paths"]["alignment_audit"]).exists()
    frame = audit["alignment_audit"]
    assert len(frame) > 0
    assert {"lhb_on_event_date", "lhb_before_event_3d", "institution_net_buy", "lhb_alignment_status"}.issubset(frame.columns)


def test_run_lhb_alignment_audit_tolerates_missing_tables(tmp_path, monkeypatch):
    curated_path = tmp_path / "curated.csv"
    pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "case_type": "second_wave",
                "first_limit_up_date": "2026-05-08",
            }
        ]
    ).to_csv(curated_path, index=False)

    def _boom(**kwargs):
        raise RuntimeError('relation "market.lhb_top_list_daily" does not exist')

    monkeypatch.setattr(lhb_data, "load_lhb_from_db", _boom)
    result = lhb_data.run_dragon_case_lhb_alignment_audit(curated_path=curated_path, output_dir=tmp_path)

    assert Path(result["paths"]["alignment_audit"]).exists()
    assert result["warnings"]


def test_run_lhb_event_features_build(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lhb_data,
        "load_lhb_from_db",
        lambda **kwargs: (
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-05-12",
                        "ts_code": "600726.SH",
                        "name": "华电能源",
                        "close": 10.5,
                        "pct_change": 9.98,
                        "turnover_rate": 12.3,
                        "amount": 12000.0,
                        "l_sell": 1000.0,
                        "l_buy": 1500.0,
                        "l_amount": 2500.0,
                        "net_amount": 500.0,
                        "net_rate": 0.04,
                        "amount_rate": 0.20,
                        "float_values": 1000000.0,
                        "reason": "日涨幅偏离值达7%",
                        "source": "akshare",
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-05-12",
                        "ts_code": "600726.SH",
                        "exalter": "机构汇总",
                        "buy": 800.0,
                        "buy_rate": None,
                        "sell": 300.0,
                        "sell_rate": None,
                        "net_buy": 500.0,
                        "reason": "日涨幅偏离值达7%",
                        "source": "akshare",
                    }
                ]
            ),
        ),
    )
    monkeypatch.setattr(lhb_data, "upsert_lhb_event_features_daily", lambda **kwargs: None)

    result = lhb_data.run_lhb_event_features_build(
        start_date="2026-05-01",
        end_date="2026-05-13",
        ts_codes=["600726.SH"],
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["lhb_event_features"]).exists()
    assert len(result["lhb_event_features"]) == 1


def test_load_lhb_from_db_without_ts_codes_loads_all_codes(monkeypatch):
    executed = []

    class _Cursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class _Ctx:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(lhb_data, "connect", lambda service: _Ctx())

    top_list, top_inst = lhb_data.load_lhb_from_db(
        ts_codes=None,
        start_date="2026-05-13",
        end_date="2026-06-05",
    )

    assert list(top_list.columns) == lhb_data.TOP_LIST_COLUMNS
    assert list(top_inst.columns) == lhb_data.TOP_INST_COLUMNS
    assert len(executed) == 2
    assert "ts_code IN" not in executed[0][0]
    assert executed[0][1] == ["2026-05-13", "2026-06-05"]


def test_build_dragon_case_lhb_summary_report(tmp_path):
    curated = pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "case_type": "second_wave",
                "verified_case_type": "second_wave",
                "success_or_failure": "success",
            },
            {
                "case_id": "c2",
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "case_type": "a_kill_failure",
                "verified_case_type": "a_kill_failure",
                "success_or_failure": "failure",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "case_type": "second_wave",
                "event_type": "second_wave_start",
                "event_date": "2026-05-12",
                "lhb_on_event_date": True,
                "lhb_before_event_3d": True,
                "lhb_after_event_3d": True,
                "lhb_reason": "日涨幅偏离值达7%",
                "lhb_net_buy_amount": 500.0,
                "institution_net_buy": 300.0,
                "top_seat_concentration": 0.2,
                "repeat_on_list_count_3d": 2,
                "repeat_on_list_count_5d": 3,
                "lhb_one_day_pump_risk": 0.4,
                "lhb_alignment_status": "matched",
            },
            {
                "case_id": "c2",
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "case_type": "a_kill_failure",
                "event_type": "a_kill_start",
                "event_date": "2024-01-24",
                "lhb_on_event_date": True,
                "lhb_before_event_3d": True,
                "lhb_after_event_3d": False,
                "lhb_reason": "日换手率达20%",
                "lhb_net_buy_amount": -400.0,
                "institution_net_buy": -200.0,
                "top_seat_concentration": 0.5,
                "repeat_on_list_count_3d": 1,
                "repeat_on_list_count_5d": 2,
                "lhb_one_day_pump_risk": 0.9,
                "lhb_alignment_status": "matched",
            },
        ]
    )

    result = lhb_data.build_dragon_case_lhb_summary_report(curated=curated, alignment_audit=audit, output_dir=tmp_path)

    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["comparison"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    assert {"case_type", "event_type", "sample_count", "matched_count", "on_event_date_rate"}.issubset(result["summary"].columns)
    assert {"case_group", "sample_count", "avg_lhb_net_buy_amount", "avg_lhb_one_day_pump_risk"}.issubset(result["comparison"].columns)
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Case Summary" in report
    assert "second_wave" in report


def test_build_lhb_case_difference_report_outputs_all_tables(tmp_path):
    curated = _sample_lhb_curated()
    alignment = _sample_lhb_alignment()
    features = _sample_lhb_features()
    factor_review = _sample_lhb_factor_review()

    result = lhb_data.build_lhb_case_difference_report(
        curated=curated,
        lhb_features=features,
        alignment_audit=alignment,
        output_dir=tmp_path,
        factor_review=factor_review,
    )

    expected_paths = {
        "case_type_difference_summary",
        "event_window_difference",
        "risk_signal_effectiveness",
        "positive_signal_effectiveness",
        "case_event_detail",
        "coverage_summary",
        "markdown_report",
    }
    assert expected_paths.issubset(result["paths"])
    for path in result["paths"].values():
        assert Path(path).exists()
    assert "success_or_failure" in result["case_type_difference_summary"].columns
    assert "event_window" in result["event_window_difference"].columns
    assert "risk_signal" in result["risk_signal_effectiveness"].columns
    assert "positive_signal" in result["positive_signal_effectiveness"].columns
    assert "diagnostic_note" in result["case_event_detail"].columns
    assert "matched_rate" in result["coverage_summary"].columns
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Case/Event Difference Report v1" in report
    assert "成功二波 vs 失败二波" in report


def test_lhb_risk_and_positive_signal_labels_are_generated(tmp_path):
    result = lhb_data.build_lhb_case_difference_report(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
    )

    risks = set(result["risk_signal_effectiveness"]["risk_signal"])
    positives = set(result["positive_signal_effectiveness"]["positive_signal"])
    notes = set(result["case_event_detail"]["diagnostic_note"])

    assert "lhb_negative_net_buy" in risks
    assert "lhb_high_pump_risk" in risks
    assert "lhb_positive_net_buy" in positives
    assert "lhb_repeat_with_positive_net_buy" in positives
    assert "a_kill_with_negative_lhb" in notes


def test_lhb_difference_report_handles_missing_samples(tmp_path):
    result = lhb_data.build_lhb_case_difference_report(
        curated=pd.DataFrame(columns=["case_id", "ts_code", "case_type"]),
        lhb_features=pd.DataFrame(columns=lhb_data.LHB_EVENT_FEATURE_COLUMNS),
        alignment_audit=pd.DataFrame(columns=lhb_data.LHB_ALIGNMENT_COLUMNS),
        output_dir=tmp_path,
    )

    assert result["warnings"]
    assert Path(result["paths"]["markdown_report"]).exists()
    assert result["coverage_summary"].iloc[0]["total_cases"] == 0


def test_build_lhb_risk_feature_diagnostics_outputs_tables(tmp_path):
    result = lhb_data.build_lhb_risk_feature_diagnostics(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={},
    )

    expected_paths = {
        "risk_feature_case_detail",
        "risk_score_bucket_effectiveness",
        "risk_failure_type_cross",
        "dragon_risk_cross_diagnostics",
        "coverage_gap_recommendations",
        "markdown_report",
    }
    assert expected_paths.issubset(result["paths"])
    for path in result["paths"].values():
        assert Path(path).exists()
    detail = result["risk_feature_case_detail"]
    assert {"lhb_negative_net_buy", "lhb_institution_selling", "lhb_high_pump_risk", "lhb_risk_score"}.issubset(detail.columns)
    assert result["risk_score_bucket_effectiveness"]["bucket"].notna().any()
    assert "lhb_risk_level" in result["risk_failure_type_cross"].columns
    assert "priority_for_lhb_backfill" in result["coverage_gap_recommendations"].columns


def test_lhb_risk_score_ignores_future_returns(tmp_path):
    base_review = _sample_lhb_factor_review()
    changed_review = base_review.copy()
    changed_review["future_5d_return"] = 99.0
    changed_review["future_10d_return"] = 99.0

    base = lhb_data.build_lhb_risk_feature_diagnostics(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path / "base",
        factor_review=base_review,
        optional_diagnostics={},
    )["risk_feature_case_detail"]["lhb_risk_score"].tolist()
    changed = lhb_data.build_lhb_risk_feature_diagnostics(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path / "changed",
        factor_review=changed_review,
        optional_diagnostics={},
    )["risk_feature_case_detail"]["lhb_risk_score"].tolist()

    assert base == changed


def test_lhb_risk_feature_flags_are_correct(tmp_path):
    result = lhb_data.build_lhb_risk_feature_diagnostics(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={},
    )
    detail = result["risk_feature_case_detail"]
    a_kill = detail[detail["case_id"] == "c_a_kill"].iloc[0]

    assert bool(a_kill["lhb_negative_net_buy"]) is True
    assert bool(a_kill["lhb_institution_selling"]) is True
    assert bool(a_kill["lhb_high_pump_risk"]) is True
    assert a_kill["lhb_risk_score"] > 0.5


def test_build_lhb_follow_exit_replay_classifies_follow_exit_and_avoid(tmp_path):
    result = lhb_data.build_lhb_follow_exit_replay_v1(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={},
    )

    detail = result["replay_detail"].set_index("case_id")
    assert detail.loc["c_success", "lhb_replay_action"] == "follow_candidate"
    assert detail.loc["c_failed_wave", "lhb_replay_action"] == "exit_confirmation"
    assert detail.loc["c_a_kill", "lhb_replay_action"] == "avoid_withdrawal"
    assert "positive_lhb_confirmed_structure" in detail.loc["c_success", "lhb_replay_reason"]
    assert "failure_structure" in detail.loc["c_failed_wave", "lhb_replay_reason"]
    assert "withdrawal_lhb" in detail.loc["c_a_kill", "lhb_replay_reason"]

    effectiveness = result["replay_effectiveness"].set_index("lhb_replay_action")
    assert effectiveness.loc["follow_candidate", "sample_count"] == 1
    assert effectiveness.loc["follow_candidate", "win_rate_5d"] == 1.0
    assert Path(result["paths"]["replay_detail"]).exists()
    assert Path(result["paths"]["replay_effectiveness"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_shortline_event_replay_outputs_unified_phase1_table(tmp_path):
    dragon = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "industry_name": "AI",
                "mainline_flag": True,
                "industry_rank": 1,
                "industry_focus_score_v2": 0.92,
                "dragon_role": "dragon_leader",
                "dragon_entry_score": 0.81,
                "dragon_risk_score": 0.22,
                "entry_window_v2": "breakout_entry",
            },
            {
                "trade_date": "2025-09-18",
                "ts_code": "000002.SZ",
                "industry_name": "地产",
                "mainline_flag": False,
                "industry_rank": 18,
                "industry_focus_score_v2": 0.20,
                "dragon_role": "cooling_down",
                "dragon_entry_score": 0.18,
                "dragon_risk_score": 0.86,
                "entry_window_v2": "overheat_avoid",
            },
        ]
    )
    market = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "short_market_state": "mainline_market",
                "short_allowed": True,
                "market_risk_level": "low",
            },
            {
                "trade_date": "2025-09-18",
                "short_market_state": "high_position_risk",
                "short_allowed": False,
                "market_risk_level": "high",
            },
        ]
    )

    result = lhb_data.build_lhb_shortline_event_replay_v1(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={"dragon": dragon},
        market_frame=market,
    )

    replay = result["event_replay"].set_index("case_id")
    assert replay.loc["c_success", "lhb_behavior_type"] == "support"
    assert replay.loc["c_success", "lhb_replay_action"] == "follow_candidate"
    assert replay.loc["c_success", "dragon_role"] == "dragon_leader"
    assert bool(replay.loc["c_success", "mainline_flag"]) is True
    assert replay.loc["c_success", "short_market_state"] == "mainline_market"
    assert replay.loc["c_success", "future_5d_return"] == 0.12
    assert replay.loc["c_a_kill", "lhb_behavior_type"] == "withdrawal"
    assert replay.loc["c_a_kill", "lhb_replay_action"] == "avoid_withdrawal"
    assert replay.loc["c_a_kill", "market_risk_level"] == "high"
    assert "future_10d_max_drawdown" in result["event_replay"].columns
    assert Path(result["paths"]["event_replay"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_follow_avoid_rule_audit_summarizes_phase2_effectiveness(tmp_path):
    replay = pd.DataFrame(
        [
            {
                "case_id": "c_follow",
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "stock_name": "Follow",
                "short_market_state": "mainline_market",
                "short_allowed": True,
                "mainline_flag": True,
                "dragon_role": "dragon_leader",
                "entry_window_v2": "breakout_entry",
                "event_structure": "second_wave",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "future_3d_return": 0.08,
                "future_5d_return": 0.12,
                "future_10d_return": 0.18,
                "future_5d_max_drawdown": -0.03,
                "future_10d_max_drawdown": -0.05,
                "success_or_failure": "success",
            },
            {
                "case_id": "c_elastic",
                "trade_date": "2026-05-13",
                "ts_code": "000001.SZ",
                "stock_name": "Elastic",
                "short_market_state": "mainline_market",
                "short_allowed": True,
                "mainline_flag": True,
                "dragon_role": "early_potential",
                "entry_window_v2": "acceleration_entry",
                "event_structure": "weak_to_strong",
                "lhb_behavior_type": "high_elasticity",
                "lhb_replay_action": "high_elasticity_follow",
                "future_3d_return": 0.03,
                "future_5d_return": 0.06,
                "future_10d_return": 0.10,
                "future_5d_max_drawdown": -0.08,
                "future_10d_max_drawdown": -0.12,
                "success_or_failure": "success",
            },
            {
                "case_id": "c_avoid",
                "trade_date": "2025-09-18",
                "ts_code": "000002.SZ",
                "stock_name": "Avoid",
                "short_market_state": "high_position_risk",
                "short_allowed": False,
                "mainline_flag": False,
                "dragon_role": "cooling_down",
                "entry_window_v2": "overheat_avoid",
                "event_structure": "a_kill_failure",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "future_3d_return": -0.08,
                "future_5d_return": -0.12,
                "future_10d_return": -0.20,
                "future_5d_max_drawdown": -0.15,
                "future_10d_max_drawdown": -0.25,
                "success_or_failure": "failure",
            },
        ]
    )

    result = lhb_data.build_lhb_follow_avoid_rule_audit_v1(event_replay=replay, output_dir=tmp_path)

    action = result["action_effectiveness"].set_index("lhb_replay_action")
    assert action.loc["follow_candidate", "sample_count"] == 1
    assert action.loc["follow_candidate", "win_rate_5d"] == 1.0
    assert action.loc["avoid_withdrawal", "avg_future_5d_return"] == -0.12
    rule = result["rule_matrix"]
    assert {
        "lhb_replay_action",
        "lhb_behavior_type",
        "event_structure",
        "dragon_role",
        "entry_window_v2",
        "sample_count",
    }.issubset(rule.columns)
    recommendations = set(result["rule_recommendations"]["rule_recommendation"])
    assert "follow_watch" in recommendations
    assert "high_elasticity_watch" in recommendations
    assert "avoid_watch" in recommendations
    assert Path(result["paths"]["action_effectiveness"]).exists()
    assert Path(result["paths"]["rule_matrix"]).exists()
    assert Path(result["paths"]["rule_recommendations"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_exit_rule_audit_summarizes_phase3_effectiveness(tmp_path):
    replay = pd.DataFrame(
        [
            {
                "case_id": "c_hard",
                "trade_date": "2025-09-18",
                "ts_code": "000002.SZ",
                "stock_name": "HardExit",
                "event_structure": "a_kill_failure",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb,failure_structure",
                "short_market_state": "high_position_risk",
                "market_risk_level": "high",
                "future_1d_return": -0.06,
                "future_3d_return": -0.08,
                "future_5d_return": -0.12,
                "future_10d_return": -0.20,
                "future_5d_max_drawdown": -0.15,
                "future_10d_max_drawdown": -0.25,
                "success_or_failure": "failure",
            },
            {
                "case_id": "c_reduce",
                "trade_date": "2024-01-24",
                "ts_code": "000017.SZ",
                "stock_name": "Reduce",
                "event_structure": "failed_second_wave",
                "lhb_behavior_type": "attention",
                "lhb_replay_action": "exit_confirmation",
                "exit_signal": "reduce_watch",
                "exit_reason": "failure_structure,after_event_attention",
                "short_market_state": "rotation_market",
                "market_risk_level": "medium",
                "future_1d_return": -0.02,
                "future_3d_return": -0.03,
                "future_5d_return": -0.05,
                "future_10d_return": -0.10,
                "future_5d_max_drawdown": -0.08,
                "future_10d_max_drawdown": -0.15,
                "success_or_failure": "failure",
            },
            {
                "case_id": "c_false_positive",
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "stock_name": "FalsePositive",
                "event_structure": "second_wave",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "exit_signal": "",
                "exit_reason": "",
                "short_market_state": "mainline_market",
                "market_risk_level": "low",
                "future_1d_return": 0.04,
                "future_3d_return": 0.08,
                "future_5d_return": 0.12,
                "future_10d_return": 0.18,
                "future_5d_max_drawdown": -0.03,
                "future_10d_max_drawdown": -0.05,
                "success_or_failure": "success",
            },
        ]
    )

    result = lhb_data.build_lhb_exit_rule_audit_v1(event_replay=replay, output_dir=tmp_path)

    signal = result["exit_signal_effectiveness"].set_index("exit_signal")
    assert signal.loc["hard_exit", "sample_count"] == 1
    assert signal.loc["hard_exit", "avg_future_5d_return"] == -0.12
    assert signal.loc["reduce_watch", "avg_future_10d_max_drawdown"] == -0.15
    reason = result["exit_reason_effectiveness"]
    assert "withdrawal_lhb" in set(reason["exit_reason"])
    assert "failure_structure" in set(reason["exit_reason"])
    assert result["false_positive_audit"].iloc[0]["sample_count"] == 1
    assert result["false_positive_audit"].iloc[0]["strong_follow_count"] == 1
    assert Path(result["paths"]["exit_signal_effectiveness"]).exists()
    assert Path(result["paths"]["exit_reason_effectiveness"]).exists()
    assert Path(result["paths"]["false_positive_audit"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_daily_lhb_shortline_watchlist_outputs_four_watch_groups(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "ts_code": "600726.SH",
                "stock_name": "Follow",
                "short_market_state": "mainline_market",
                "short_allowed": True,
                "mainline_flag": True,
                "dragon_role": "dragon_leader",
                "entry_window_v2": "breakout_entry",
                "event_structure": "second_wave",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "lhb_replay_reason": "positive_lhb_confirmed_structure",
                "lhb_risk_score": 0.25,
                "lhb_risk_level": "low",
                "exit_signal": "",
                "exit_reason": "",
            },
            {
                "trade_date": "2026-05-20",
                "ts_code": "000001.SZ",
                "stock_name": "Elastic",
                "short_market_state": "mainline_market",
                "short_allowed": True,
                "mainline_flag": True,
                "dragon_role": "early_potential",
                "entry_window_v2": "acceleration_entry",
                "event_structure": "weak_to_strong",
                "lhb_behavior_type": "high_elasticity",
                "lhb_replay_action": "high_elasticity_follow",
                "lhb_replay_reason": "high_elasticity_pump",
                "lhb_risk_score": 0.45,
                "lhb_risk_level": "medium",
                "exit_signal": "",
                "exit_reason": "",
            },
            {
                "trade_date": "2026-05-20",
                "ts_code": "000002.SZ",
                "stock_name": "Avoid",
                "short_market_state": "high_position_risk",
                "short_allowed": False,
                "mainline_flag": False,
                "dragon_role": "cooling_down",
                "entry_window_v2": "overheat_avoid",
                "event_structure": "a_kill_failure",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "lhb_replay_reason": "withdrawal_lhb",
                "lhb_risk_score": 0.85,
                "lhb_risk_level": "high",
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb,failure_structure",
            },
            {
                "trade_date": "2026-05-20",
                "ts_code": "000017.SZ",
                "stock_name": "Exit",
                "short_market_state": "rotation_market",
                "short_allowed": True,
                "mainline_flag": False,
                "dragon_role": "follower",
                "entry_window_v2": "overheat_avoid",
                "event_structure": "failed_second_wave",
                "lhb_behavior_type": "attention",
                "lhb_replay_action": "exit_confirmation",
                "lhb_replay_reason": "failure_structure",
                "lhb_risk_score": 0.55,
                "lhb_risk_level": "medium",
                "exit_signal": "reduce_watch",
                "exit_reason": "failure_structure,after_event_attention",
            },
        ]
    )
    recommendations = pd.DataFrame(
        [
            {
                "rule_recommendation": "follow_watch",
                "lhb_replay_action": "follow_candidate",
                "lhb_behavior_type": "support",
                "event_structure": "second_wave",
                "dragon_role": "dragon_leader",
                "entry_window_v2": "breakout_entry",
                "short_market_state": "mainline_market",
                "mainline_flag": True,
                "reason": "positive_follow_effectiveness",
            },
            {
                "rule_recommendation": "high_elasticity_watch",
                "lhb_replay_action": "high_elasticity_follow",
                "lhb_behavior_type": "high_elasticity",
                "event_structure": "weak_to_strong",
                "dragon_role": "early_potential",
                "entry_window_v2": "acceleration_entry",
                "short_market_state": "mainline_market",
                "mainline_flag": True,
                "reason": "positive_elasticity_with_controlled_drawdown",
            },
        ]
    )

    result = lhb_data.build_daily_lhb_shortline_watchlist_v1(
        event_replay=event_replay,
        rule_recommendations=recommendations,
        trade_date="2026-05-20",
        output_dir=tmp_path,
    )

    watchlist = result["watchlist"].set_index("ts_code")
    assert watchlist.loc["600726.SH", "watch_group"] == "follow_watch"
    assert watchlist.loc["000001.SZ", "watch_group"] == "high_elasticity_watch"
    assert watchlist.loc["000002.SZ", "watch_group"] == "avoid_watch"
    assert watchlist.loc["000017.SZ", "watch_group"] == "exit_watch"
    assert "positive_follow_effectiveness" in watchlist.loc["600726.SH", "watch_reason"]
    assert "withdrawal_lhb" in watchlist.loc["000002.SZ", "exit_reason"]
    assert Path(result["paths"]["watchlist"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_daily_lhb_shortline_watchlist_omits_literal_nan_reason(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-13",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "lhb_behavior_type": "attention",
                "lhb_replay_action": "exit_confirmation",
                "lhb_replay_reason": "insufficient_confirmation",
                "event_structure": "failed_second_wave",
                "dragon_role": "follower",
                "entry_window_v2": "overheat_avoid",
                "short_market_state": "rotation_market",
                "mainline_flag": False,
                "exit_signal": "",
                "exit_reason": "",
            }
        ]
    )
    recommendations = pd.DataFrame(
        [
            {
                "rule_recommendation": "watch_only",
                "lhb_replay_action": "exit_confirmation",
                "lhb_behavior_type": "attention",
                "event_structure": "failed_second_wave",
                "dragon_role": "follower",
                "entry_window_v2": "overheat_avoid",
                "short_market_state": "rotation_market",
                "mainline_flag": False,
                "reason": pd.NA,
            }
        ]
    )

    result = lhb_data.build_daily_lhb_shortline_watchlist_v1(
        event_replay=event_replay,
        rule_recommendations=recommendations,
        trade_date="2026-05-13",
        output_dir=tmp_path,
    )

    reason = result["watchlist"].iloc[0]["watch_reason"]
    assert reason == "insufficient_confirmation"
    assert "nan" not in reason.lower()


def test_build_daily_lhb_shortline_watchlist_applies_rule_registry_downgrade(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "ts_code": "000002.SZ",
                "stock_name": "Avoid",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "lhb_replay_reason": "withdrawal_lhb",
                "event_structure": "second_wave",
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb",
            }
        ]
    )
    rule_registry = pd.DataFrame(
        [
            {
                "rule_id": "LHB-EXIT-003",
                "rule_scope": "exit",
                "lhb_shortline_rule_version": "lhb_shortline_rules_v1_1",
                "rule_recommendation": "downgrade_to_reduce_watch",
                "lhb_shortline_rule_confidence": "medium",
                "lhb_shortline_rule_sample_count": 28,
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb",
            }
        ]
    )

    result = lhb_data.build_daily_lhb_shortline_watchlist_v1(
        event_replay=event_replay,
        rule_recommendations=pd.DataFrame(),
        rule_registry=rule_registry,
        trade_date="2026-05-20",
        output_dir=tmp_path,
    )

    row = result["watchlist"].iloc[0]
    assert row["watch_group"] == "exit_watch"
    assert row["exit_signal"] == "reduce_watch"
    assert row["lhb_shortline_rule_version"] == "lhb_shortline_rules_v1_1"
    assert row["lhb_shortline_exit_rule_id"] == "LHB-EXIT-003"
    assert row["rule_calibration_action"] == "downgrade_to_reduce_watch"
    assert row["lhb_shortline_rule_confidence"] == "medium"
    assert row["lhb_shortline_rule_sample_count"] == 28


def test_build_lhb_shortline_strategy_effectiveness_v1_outputs_phase6_review(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "ts_code": "600726.SH",
                "stock_name": "Follow",
                "short_market_state": "mainline_market",
                "market_risk_level": "low",
                "mainline_flag": True,
                "entry_window_v2": "breakout_entry",
                "event_structure": "second_wave",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "exit_signal": "",
                "exit_reason": "",
                "future_1d_return": 0.02,
                "future_3d_return": 0.05,
                "future_5d_return": 0.12,
                "future_10d_return": 0.18,
                "future_5d_max_drawdown": -0.03,
                "future_10d_max_drawdown": -0.04,
                "limit_up_within_5d": True,
                "a_kill_within_5d": False,
                "second_wave_success": True,
                "success_or_failure": "success",
            },
            {
                "trade_date": "2026-05-20",
                "ts_code": "000001.SZ",
                "stock_name": "Elastic",
                "short_market_state": "mainline_market",
                "market_risk_level": "medium",
                "mainline_flag": True,
                "entry_window_v2": "acceleration_entry",
                "event_structure": "weak_to_strong",
                "lhb_behavior_type": "high_elasticity",
                "lhb_replay_action": "high_elasticity_follow",
                "exit_signal": "",
                "exit_reason": "",
                "future_1d_return": -0.01,
                "future_3d_return": 0.03,
                "future_5d_return": 0.08,
                "future_10d_return": 0.02,
                "future_5d_max_drawdown": -0.07,
                "future_10d_max_drawdown": -0.11,
                "limit_up_within_5d": True,
                "a_kill_within_5d": False,
                "second_wave_success": False,
                "success_or_failure": "success",
            },
            {
                "trade_date": "2026-05-20",
                "ts_code": "000002.SZ",
                "stock_name": "Avoid",
                "short_market_state": "high_position_risk",
                "market_risk_level": "high",
                "mainline_flag": False,
                "entry_window_v2": "overheat_avoid",
                "event_structure": "a_kill_failure",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb,failure_structure",
                "future_1d_return": -0.04,
                "future_3d_return": -0.09,
                "future_5d_return": -0.16,
                "future_10d_return": -0.22,
                "future_5d_max_drawdown": -0.20,
                "future_10d_max_drawdown": -0.28,
                "limit_up_within_5d": False,
                "a_kill_within_5d": True,
                "second_wave_success": False,
                "success_or_failure": "failure",
            },
        ]
    )
    daily_watchlist = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "ts_code": "600726.SH", "watch_group": "follow_watch"},
            {"trade_date": "2026-05-20", "ts_code": "000001.SZ", "watch_group": "high_elasticity_watch"},
            {"trade_date": "2026-05-20", "ts_code": "000002.SZ", "watch_group": "avoid_watch"},
        ]
    )

    result = lhb_data.build_lhb_shortline_strategy_effectiveness_v1(
        event_replay=event_replay,
        daily_watchlist=daily_watchlist,
        output_dir=tmp_path,
        min_sample_count=2,
    )

    detail = result["detail"].set_index("ts_code")
    assert detail.loc["600726.SH", "watch_group"] == "follow_watch"
    assert detail.loc["000001.SZ", "watch_group"] == "high_elasticity_watch"
    assert detail.loc["000002.SZ", "watch_group"] == "avoid_watch"
    assert detail.loc["000002.SZ", "exit_hit"] is True

    summary = result["summary"].set_index("watch_group")
    assert summary.loc["follow_watch", "avg_future_5d_return"] == 0.12
    assert summary.loc["avoid_watch", "a_kill_rate_5d"] == 1.0
    assert summary.loc["follow_watch", "low_sample_flag"] is True

    follow_combo = result["follow_combo_effectiveness"]
    assert set(follow_combo["watch_group"]) == {"follow_watch", "high_elasticity_watch"}
    exit_combo = result["exit_combo_effectiveness"]
    assert "withdrawal_lhb" in set(exit_combo["exit_reason"])
    assert exit_combo.set_index("exit_reason").loc["withdrawal_lhb", "exit_hit_rate"] == 1.0

    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["follow_combo_effectiveness"]).exists()
    assert Path(result["paths"]["exit_combo_effectiveness"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Shortline Strategy Effectiveness v1" in report
    assert "Top Follow / Elasticity Combos" in report


def test_build_lhb_shortline_rule_calibration_v1_versions_follow_and_exit_rules(tmp_path):
    follow_combo = pd.DataFrame(
        [
            {
                "watch_group": "follow_watch",
                "lhb_behavior_type": "support",
                "event_structure": "second_wave",
                "entry_window_v2": "breakout_entry",
                "mainline_flag": True,
                "short_market_state": "mainline_market",
                "sample_count": 13,
                "avg_future_5d_return": 0.34,
                "win_rate_5d": 0.84,
                "avg_future_5d_max_drawdown": -0.03,
                "a_kill_rate_5d": 0.0,
                "low_sample_flag": False,
            },
            {
                "watch_group": "high_elasticity_watch",
                "lhb_behavior_type": "high_elasticity",
                "event_structure": "weak_to_strong",
                "entry_window_v2": "acceleration_entry",
                "mainline_flag": True,
                "short_market_state": "mainline_market",
                "sample_count": 3,
                "avg_future_5d_return": 0.04,
                "win_rate_5d": 0.67,
                "avg_future_5d_max_drawdown": -0.08,
                "a_kill_rate_5d": 0.0,
                "low_sample_flag": True,
            },
        ]
    )
    exit_combo = pd.DataFrame(
        [
            {
                "exit_signal": "reduce_watch",
                "exit_reason": "failure_structure",
                "sample_count": 126,
                "avg_future_5d_return": -0.11,
                "win_rate_5d": 0.05,
                "avg_future_5d_max_drawdown": -0.15,
                "exit_hit_rate": 0.95,
                "low_sample_flag": False,
            },
            {
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb",
                "sample_count": 28,
                "avg_future_5d_return": 0.15,
                "win_rate_5d": 0.54,
                "avg_future_5d_max_drawdown": -0.04,
                "exit_hit_rate": 0.46,
                "low_sample_flag": False,
            },
        ]
    )

    result = lhb_data.build_lhb_shortline_rule_calibration_v1(
        follow_combo=follow_combo,
        exit_combo=exit_combo,
        output_dir=tmp_path,
        rule_version="lhb_shortline_rules_v1_1",
        min_sample_count=10,
    )

    registry = result["rule_registry"].set_index("rule_id")
    assert registry.loc["LHB-FOLLOW-001", "lhb_shortline_rule_version"] == "lhb_shortline_rules_v1_1"
    assert registry.loc["LHB-FOLLOW-001", "rule_recommendation"] == "keep_follow_watch"
    assert registry.loc["LHB-FOLLOW-001", "lhb_shortline_rule_confidence"] == "high"
    assert registry.loc["LHB-FOLLOW-001", "lhb_shortline_rule_sample_count"] == 13
    assert registry.loc["LHB-FOLLOW-002", "rule_recommendation"] == "review_sparse"
    assert registry.loc["LHB-EXIT-001", "rule_recommendation"] == "keep_reduce_watch"
    assert registry.loc["LHB-EXIT-002", "rule_recommendation"] == "downgrade_to_reduce_watch"
    assert "positive_after_exit" in registry.loc["LHB-EXIT-002", "calibration_reason"]
    assert Path(result["paths"]["rule_registry"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Shortline Rule Calibration v1" in report
    assert "hard_exit" in report


def test_build_lhb_shortline_manual_review_v1_merges_operator_decisions_and_outcomes(tmp_path):
    daily_watchlist = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-13",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "watch_group": "follow_watch",
                "watch_reason": "positive_follow_effectiveness",
                "exit_signal": "",
                "exit_reason": "",
                "lhb_shortline_follow_rule_id": "LHB-FOLLOW-001",
            },
            {
                "trade_date": "2026-05-13",
                "ts_code": "300476.SZ",
                "stock_name": "胜宏科技",
                "watch_group": "exit_watch",
                "watch_reason": "failure_structure",
                "exit_signal": "reduce_watch",
                "exit_reason": "failure_structure",
                "lhb_shortline_exit_rule_id": "LHB-EXIT-001",
            },
        ]
    )
    effectiveness_detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-13",
                "ts_code": "600726.SH",
                "future_1d_return": 0.03,
                "future_3d_return": 0.06,
                "future_5d_return": 0.12,
                "a_kill_within_5d": False,
                "second_wave_success": True,
            },
            {
                "trade_date": "2026-05-13",
                "ts_code": "300476.SZ",
                "future_1d_return": -0.02,
                "future_3d_return": -0.08,
                "future_5d_return": -0.15,
                "a_kill_within_5d": True,
                "second_wave_success": False,
            },
        ]
    )
    manual_review = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-13",
                "ts_code": "600726.SH",
                "manual_follow_decision": "focus",
                "manual_exit_decision": "",
                "manual_decision_reason": "承接二波继续观察",
                "next_day_confirmation_review": "confirmed",
                "post_review_label": "system_hit",
                "operator_notes": "次日强确认",
            },
            {
                "trade_date": "2026-05-13",
                "ts_code": "300476.SZ",
                "manual_follow_decision": "",
                "manual_exit_decision": "accept_exit",
                "manual_decision_reason": "失败结构认可撤退",
                "next_day_confirmation_review": "confirmed",
                "post_review_label": "exit_hit",
                "operator_notes": "减少回撤",
            },
        ]
    )

    result = lhb_data.build_lhb_shortline_manual_review_v1(
        daily_watchlist=daily_watchlist,
        effectiveness_detail=effectiveness_detail,
        manual_review=manual_review,
        trade_date="2026-05-13",
        output_dir=tmp_path,
    )

    review = result["manual_review"].set_index("ts_code")
    assert review.loc["600726.SH", "manual_follow_decision"] == "focus"
    assert review.loc["600726.SH", "future_5d_return"] == 0.12
    assert review.loc["300476.SZ", "manual_exit_decision"] == "accept_exit"
    assert review.loc["300476.SZ", "a_kill_within_5d"] is True
    summary = result["summary"].set_index("metric")
    assert summary.loc["total_rows", "value"] == 2
    assert summary.loc["manual_follow_focus_count", "value"] == 1
    assert summary.loc["manual_exit_accept_count", "value"] == 1
    assert summary.loc["exit_hit_label_count", "value"] == 1
    assert Path(result["paths"]["manual_review"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Shortline Manual Review v1" in report
    assert "人工纸面交易复盘" in report


def test_build_lhb_shortline_manual_review_v1_omits_literal_nan_in_report(tmp_path):
    daily_watchlist = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-13",
                "ts_code": "600726.SH",
                "stock_name": "华电能源",
                "watch_group": "exit_watch",
                "watch_reason": "insufficient_confirmation",
                "exit_signal": float("nan"),
                "exit_reason": float("nan"),
                "lhb_shortline_follow_rule_id": float("nan"),
                "lhb_shortline_exit_rule_id": float("nan"),
            }
        ]
    )

    result = lhb_data.build_lhb_shortline_manual_review_v1(
        daily_watchlist=daily_watchlist,
        trade_date="2026-05-13",
        output_dir=tmp_path,
    )

    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "nan" not in report.lower()


def test_build_lhb_shortline_shadow_backtest_v1_filters_dates_dedups_and_scores_topn(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2024-12-31",
                "ts_code": "000000.SZ",
                "stock_name": "Old",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 1,
                "dragon_entry_score": 99,
                "future_1d_return": 0.5,
                "future_3d_return": 0.5,
                "future_5d_return": 0.5,
                "future_10d_return": 0.5,
                "future_5d_max_drawdown": -0.01,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000001.SZ",
                "stock_name": "Best",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 1,
                "dragon_entry_score": 90,
                "industry_focus_score_v2": 80,
                "future_1d_return": 0.02,
                "future_3d_return": 0.04,
                "future_5d_return": 0.10,
                "future_10d_return": 0.12,
                "future_5d_max_drawdown": -0.02,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000001.SZ",
                "stock_name": "Best Duplicate",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 1,
                "dragon_entry_score": 50,
                "industry_focus_score_v2": 50,
                "future_1d_return": -0.20,
                "future_3d_return": -0.20,
                "future_5d_return": -0.20,
                "future_10d_return": -0.20,
                "future_5d_max_drawdown": -0.30,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000002.SZ",
                "stock_name": "Second",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 3,
                "dragon_entry_score": 95,
                "industry_focus_score_v2": 60,
                "future_1d_return": -0.01,
                "future_3d_return": 0.01,
                "future_5d_return": 0.04,
                "future_10d_return": 0.05,
                "future_5d_max_drawdown": -0.05,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000003.SZ",
                "stock_name": "Third",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "event_structure": "second_wave",
                "lhb_risk_score": 0,
                "dragon_entry_score": 100,
                "future_1d_return": 0.30,
                "future_3d_return": 0.30,
                "future_5d_return": 0.30,
                "future_10d_return": 0.30,
                "future_5d_max_drawdown": -0.01,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "000004.SZ",
                "stock_name": "Next",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 2,
                "dragon_entry_score": 70,
                "industry_focus_score_v2": 70,
                "future_1d_return": 0.03,
                "future_3d_return": 0.05,
                "future_5d_return": 0.08,
                "future_10d_return": 0.09,
                "future_5d_max_drawdown": -0.03,
            },
        ]
    )

    result = lhb_data.build_lhb_shortline_shadow_backtest_v1(
        event_replay=event_replay,
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n_values=[1, 2],
        output_dir=tmp_path,
    )

    selected = result["selected_trades"]
    assert set(selected["top_n"]) == {1, 2}
    top1_codes = selected[selected["top_n"].eq(1)]["ts_code"].tolist()
    assert top1_codes == ["000001.SZ", "000004.SZ"]
    assert selected[selected["ts_code"].eq("000001.SZ")].shape[0] == 2
    assert "000003.SZ" not in set(selected["ts_code"])

    summary = result["summary"].set_index("top_n")
    assert summary.loc[1, "signal_day_count"] == 2
    assert summary.loc[1, "selected_trade_count"] == 2
    assert summary.loc[1, "avg_daily_5d_return"] == 0.09
    assert summary.loc[2, "selected_trade_count"] == 3
    assert round(float(summary.loc[2, "avg_trade_5d_return"]), 6) == round((0.10 + 0.04 + 0.08) / 3, 6)

    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["selected_trades"]).exists()
    assert Path(result["paths"]["daily_curve"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Shortline Shadow Backtest v1" in report
    assert "Top-N Summary" in report


def test_build_lhb_shortline_shadow_backtest_v1_support_attention_pool_expands_candidates(tmp_path):
    event_replay = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "000001.SZ",
                "stock_name": "Strict",
                "lhb_behavior_type": "support",
                "lhb_replay_action": "follow_candidate",
                "event_structure": "second_wave",
                "lhb_risk_score": 0.2,
                "future_5d_return": 0.10,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000002.SZ",
                "stock_name": "Attention",
                "lhb_behavior_type": "attention",
                "lhb_replay_action": "exit_confirmation",
                "event_structure": "failed_second_wave",
                "exit_signal": "reduce_watch",
                "lhb_risk_score": 0.4,
                "future_5d_return": -0.05,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "000003.SZ",
                "stock_name": "Withdraw",
                "lhb_behavior_type": "withdrawal",
                "lhb_replay_action": "avoid_withdrawal",
                "event_structure": "second_wave",
                "exit_signal": "hard_exit",
                "lhb_risk_score": 0.8,
                "future_5d_return": -0.20,
            },
        ]
    )

    strict = lhb_data.build_lhb_shortline_shadow_backtest_v1(
        event_replay=event_replay,
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n_values=[5],
        output_dir=tmp_path / "strict",
    )
    expanded = lhb_data.build_lhb_shortline_shadow_backtest_v1(
        event_replay=event_replay,
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n_values=[5],
        output_dir=tmp_path / "expanded",
        pool_mode="support_attention",
    )

    assert strict["selected_trades"]["ts_code"].tolist() == ["000001.SZ"]
    assert set(expanded["selected_trades"]["ts_code"]) == {"000001.SZ", "000002.SZ"}
    assert "000003.SZ" not in set(expanded["selected_trades"]["ts_code"])
    assert expanded["summary"].iloc[0]["pool_mode"] == "support_attention"


def test_build_lhb_full_market_pool_backtest_v1_scores_daily_lhb_topn(tmp_path):
    lhb_features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "pct_chg": 2.0,
                "stored_is_st": False,
                "stored_status_quality": "trusted",
                "lhb_net_buy_amount": 1000.0,
                "lhb_net_buy_ratio": 0.10,
                "institution_net_buy": 100.0,
                "top_seat_concentration": 0.20,
                "repeat_on_list_count_3d": 1,
                "lhb_after_limit_up": True,
                "lhb_after_break_limit": False,
                "lhb_one_day_pump_risk": 0.2,
            },
            {
                "trade_date": "2026-01-02",
                "ts_code": "000002.SZ",
                "stock_name": "万科A",
                "pct_chg": 1.0,
                "stored_is_st": False,
                "stored_status_quality": "trusted",
                "lhb_net_buy_amount": 200.0,
                "lhb_net_buy_ratio": 0.03,
                "institution_net_buy": 0.0,
                "top_seat_concentration": 0.10,
                "repeat_on_list_count_3d": 1,
                "lhb_after_limit_up": False,
                "lhb_after_break_limit": False,
                "lhb_one_day_pump_risk": 0.1,
            },
            {
                "trade_date": "2026-01-02",
                "ts_code": "000003.SZ",
                "stock_name": "国华网安",
                "pct_chg": -1.0,
                "stored_is_st": False,
                "stored_status_quality": "trusted",
                "lhb_net_buy_amount": -500.0,
                "lhb_net_buy_ratio": -0.08,
                "institution_net_buy": -50.0,
                "top_seat_concentration": 0.30,
                "repeat_on_list_count_3d": 1,
                "lhb_after_limit_up": False,
                "lhb_after_break_limit": True,
                "lhb_one_day_pump_risk": 0.7,
            },
        ]
    )
    daily_bars = pd.DataFrame(
        [
            {"trade_date": trade_date, "ts_code": ts_code, "close": close, "low": low}
            for ts_code, closes in {
                "000001.SZ": [10.0, 10.5, 11.0, 11.5, 12.0, 13.0],
                "000002.SZ": [20.0, 19.5, 20.5, 21.0, 21.5, 22.0],
                "000003.SZ": [30.0, 29.0, 28.0, 27.0, 26.0, 25.0],
            }.items()
            for trade_date, close, low in zip(
                ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"],
                closes,
                [value * 0.98 for value in closes],
                strict=True,
            )
        ]
    )

    result = lhb_data.build_lhb_full_market_pool_backtest_v1(
        lhb_features=lhb_features,
        daily_bars=daily_bars,
        start_date="2026-01-01",
        end_date="2026-01-09",
        top_n_values=[1, 2],
        pool_mode="raw_lhb_positive",
        output_dir=tmp_path,
    )

    selected = result["selected_trades"]
    assert selected[selected["top_n"].eq(1)]["ts_code"].tolist() == ["000001.SZ"]
    assert set(selected[selected["top_n"].eq(2)]["ts_code"]) == {"000001.SZ", "000002.SZ"}
    assert "000003.SZ" not in set(selected["ts_code"])
    best = selected[selected["ts_code"].eq("000001.SZ")].iloc[0]
    assert round(float(best["future_5d_return"]), 6) == 0.30

    summary = result["summary"].set_index("top_n")
    assert summary.loc[1, "selected_trade_count"] == 1
    assert summary.loc[2, "selected_trade_count"] == 2
    assert summary.loc[1, "pool_mode"] == "raw_lhb_positive"
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["selected_trades"]).exists()
    assert Path(result["paths"]["daily_curve"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_full_market_pool_backtest_v1_applies_shared_eligibility_before_ranking(tmp_path):
    base = {
        "trade_date": "2026-07-14",
        "lhb_net_buy_amount": 1000.0,
        "lhb_net_buy_ratio": 0.10,
        "institution_net_buy": 100.0,
        "top_seat_concentration": 0.20,
        "repeat_on_list_count_3d": 1,
        "repeat_on_list_count_5d": 1,
        "lhb_after_limit_up": False,
        "lhb_after_break_limit": False,
        "lhb_after_reversal": False,
        "stored_is_st": False,
        "stored_status_quality": "trusted",
        "high_to_close_drawdown": 0.02,
    }
    lhb_features = pd.DataFrame(
        [
            {
                **base,
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "lhb_reason": "日涨幅偏离值达到7%的前5只证券",
                "pct_chg": 2.0,
                "lhb_one_day_pump_risk": 0.20,
            },
            {
                **base,
                "ts_code": "000004.SZ",
                "stock_name": "退市测试",
                "lhb_reason": "退市整理期",
                "pct_chg": -2.0,
                "lhb_one_day_pump_risk": 0.20,
            },
            {
                **base,
                "ts_code": "001399.SZ",
                "stock_name": "惠科股份",
                "lhb_reason": "日跌幅偏离值达到7%的前5只证券",
                "pct_chg": -9.991,
                "lhb_one_day_pump_risk": 0.30,
            },
            {
                **base,
                "ts_code": "000080.SZ",
                "stock_name": "高弹性测试",
                "lhb_reason": "日涨幅偏离值达到7%的前5只证券",
                "pct_chg": 3.0,
                "lhb_one_day_pump_risk": 0.80,
            },
            {
                **base,
                "ts_code": "000090.SZ",
                "stock_name": "极端拉升测试",
                "lhb_reason": "日涨幅偏离值达到7%的前5只证券",
                "pct_chg": 4.0,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    daily_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": ts_code,
                "close": 10.0,
                "low": 9.8,
            }
            for ts_code in lhb_features["ts_code"]
        ]
    )

    result = lhb_data.build_lhb_full_market_pool_backtest_v1(
        lhb_features=lhb_features,
        daily_bars=daily_bars,
        start_date="2026-07-14",
        end_date="2026-07-14",
        top_n_values=[10],
        output_dir=tmp_path,
        pool_mode="raw_lhb_positive",
    )

    selected = result["selected_trades"]
    eligible_candidates = result["eligible_candidates"]
    rejected = result["rejected_events"]
    assert "000004.SZ" not in set(selected["ts_code"])
    assert "001399.SZ" not in set(selected["ts_code"])
    assert "000080.SZ" in set(selected["ts_code"])
    assert "000090.SZ" not in set(selected["ts_code"])
    assert set(eligible_candidates["ts_code"]) == {"000001.SZ", "000080.SZ"}
    assert set(rejected["eligibility_status"]) == {"hard_reject", "risk_watch"}
    assert rejected["eligibility_reason_codes"].str.contains("delisting_period").any()
    assert rejected["eligibility_reason_codes"].str.contains("near_limit_down_followthrough_risk").any()
    assert selected["eligibility_contract_version"].eq("lhb_eligibility_v2").all()
    warning = selected[selected["ts_code"].eq("000080.SZ")].iloc[0]
    assert "high_elasticity_pump_risk" in warning["eligibility_warning_codes"]
    assert Path(result["paths"]["rejected_events"]).exists()
    assert Path(result["paths"]["eligible_candidates"]).exists()


def test_build_lhb_intraday_filtered_topn_comparison_v1_compares_actions(tmp_path):
    selected_trades = pd.DataFrame(
        [
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 5,
                "trade_date": "2026-01-02",
                "ts_code": "000001.SZ",
                "future_1d_return": 0.02,
                "future_3d_return": 0.04,
                "future_5d_return": 0.10,
                "future_10d_return": 0.12,
                "future_5d_max_drawdown": -0.02,
            },
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 5,
                "trade_date": "2026-01-02",
                "ts_code": "000002.SZ",
                "future_1d_return": -0.03,
                "future_3d_return": -0.05,
                "future_5d_return": -0.12,
                "future_10d_return": -0.15,
                "future_5d_max_drawdown": -0.16,
            },
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 10,
                "trade_date": "2026-01-02",
                "ts_code": "000001.SZ",
                "future_1d_return": 0.02,
                "future_3d_return": 0.04,
                "future_5d_return": 0.10,
                "future_10d_return": 0.12,
                "future_5d_max_drawdown": -0.02,
            },
        ]
    )
    intraday_detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "ts_code": "000001.SZ",
                "intraday_confirmation_action": "confirm_follow",
            },
            {
                "trade_date": "2026-01-02",
                "ts_code": "000002.SZ",
                "intraday_confirmation_action": "reject_follow",
            },
        ]
    )

    result = lhb_data.build_lhb_intraday_filtered_topn_comparison_v1(
        selected_trades=selected_trades,
        intraday_detail=intraday_detail,
        output_dir=tmp_path,
    )

    comparison = result["comparison"].set_index(["top_n", "candidate_set"])
    assert comparison.loc[(5, "raw_topn"), "selected_trade_count"] == 2
    assert comparison.loc[(5, "intraday_confirm_follow"), "selected_trade_count"] == 1
    assert comparison.loc[(5, "intraday_confirm_follow"), "avg_future_5d_return"] == 0.10
    assert comparison.loc[(5, "intraday_reject_follow"), "avg_future_5d_return"] == -0.12
    assert comparison.loc[(10, "intraday_confirm_follow"), "selected_trade_count"] == 1
    action_effectiveness = result["action_effectiveness"].set_index("intraday_confirmation_action")
    assert action_effectiveness.loc["confirm_follow", "candidate_count"] == 1
    assert action_effectiveness.loc["reject_follow", "candidate_count"] == 1
    assert Path(result["paths"]["comparison"]).exists()
    assert Path(result["paths"]["action_effectiveness"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_shortline_intraday_confirmation_v1_scores_next_day_confirmation(tmp_path):
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-20",
                "ts_code": "600726.SH",
                "stock_name": "Confirm",
                "top_n": 5,
                "lhb_replay_action": "follow_candidate",
                "lhb_behavior_type": "support",
                "event_structure": "second_wave",
            },
            {
                "trade_date": "2026-03-20",
                "ts_code": "002081.SZ",
                "stock_name": "Reject",
                "top_n": 5,
                "lhb_replay_action": "follow_candidate",
                "lhb_behavior_type": "support",
                "event_structure": "second_wave",
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount,
            }
            for trade_date, ts_code, rows in [
                (
                    "2026-03-23",
                    "600726.SH",
                    [
                        ("2026-03-23 09:35:00", 10.00, 10.20, 9.95, 10.15, 1000, 10150),
                        ("2026-03-23 10:30:00", 10.15, 10.60, 10.10, 10.55, 2000, 21100),
                        ("2026-03-23 14:55:00", 10.55, 10.90, 10.50, 10.85, 3000, 32550),
                    ],
                ),
                (
                    "2026-03-23",
                    "002081.SZ",
                    [
                        ("2026-03-23 09:35:00", 10.00, 10.60, 9.90, 10.50, 1000, 10500),
                        ("2026-03-23 10:30:00", 10.50, 10.55, 9.80, 9.90, 2000, 19800),
                        ("2026-03-23 14:55:00", 9.90, 10.00, 9.40, 9.50, 3000, 28500),
                    ],
                ),
            ]
            for trade_time, open_, high, low, close, volume, amount in rows
        ]
    )

    result = lhb_data.build_lhb_shortline_intraday_confirmation_v1(
        candidates=candidates,
        minute_bars=minute_bars,
        output_dir=tmp_path,
    )

    detail = result["detail"].set_index("ts_code")
    assert detail.loc["600726.SH", "confirmation_trade_date"] == "2026-03-23"
    assert detail.loc["600726.SH", "intraday_confirmation_action"] == "confirm_follow"
    assert detail.loc["600726.SH", "first_60m_return"] > 0
    assert detail.loc["600726.SH", "close_to_vwap"] > 0
    assert detail.loc["002081.SZ", "intraday_confirmation_action"] == "reject_follow"
    assert "morning_fade" in detail.loc["002081.SZ", "intraday_confirmation_reason"]

    summary = result["summary"].set_index("intraday_confirmation_action")
    assert summary.loc["confirm_follow", "candidate_count"] == 1
    assert summary.loc["reject_follow", "candidate_count"] == 1
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_shortline_intraday_confirmation_marks_chase_control_instead_of_reject(tmp_path):
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-20",
                "ts_code": "600726.SH",
                "stock_name": "Huadian",
                "lhb_replay_action": "follow_candidate",
                "lhb_behavior_type": "support",
                "event_structure": "second_wave",
            }
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-23",
                "ts_code": "600726.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount,
            }
            for trade_time, open_, high, low, close, volume, amount in [
                ("2026-03-23 09:35:00", 5.31, 5.50, 5.31, 5.46, 1000, 5460),
                ("2026-03-23 09:40:00", 5.47, 5.68, 5.40, 5.56, 1000, 5560),
                ("2026-03-23 10:30:00", 5.56, 5.64, 5.56, 5.58, 1000, 5580),
                ("2026-03-23 14:30:00", 5.27, 5.28, 5.14, 5.17, 1000, 5170),
                ("2026-03-23 15:00:00", 5.29, 5.32, 5.26, 5.32, 1000, 5320),
            ]
        ]
    )

    result = lhb_data.build_lhb_shortline_intraday_confirmation_v1(
        candidates=candidates,
        minute_bars=minute_bars,
        output_dir=tmp_path,
    )

    row = result["detail"].iloc[0]
    assert row["intraday_confirmation_action"] == "confirm_but_chase_control"
    assert "morning_fade_chase_control" in row["intraday_confirmation_reason"]
    assert row["first_60m_return"] > 0
    assert row["intraday_return"] >= 0


def test_lhb_shortline_intraday_confirmation_marks_pullback_confirm_when_weak_open_recovers(tmp_path):
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-16",
                "ts_code": "600726.SH",
                "stock_name": "Huadian",
                "lhb_replay_action": "no_follow",
                "lhb_behavior_type": "attention",
                "event_structure": "second_wave",
            }
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-17",
                "ts_code": "600726.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000,
                "amount": close * 1000,
            }
            for trade_time, open_, high, low, close in [
                ("2026-03-17 09:35:00", 5.00, 5.02, 4.90, 4.92),
                ("2026-03-17 10:30:00", 4.92, 4.95, 4.85, 4.88),
                ("2026-03-17 14:30:00", 4.88, 5.08, 4.88, 5.05),
                ("2026-03-17 15:00:00", 5.05, 5.12, 5.02, 5.10),
            ]
        ]
    )

    result = lhb_data.build_lhb_shortline_intraday_confirmation_v1(
        candidates=candidates,
        minute_bars=minute_bars,
        output_dir=tmp_path,
    )

    row = result["detail"].iloc[0]
    assert row["intraday_confirmation_action"] == "watch_pullback_confirm"
    assert "weak_first_60m_recovered" in row["intraday_confirmation_reason"]
    assert row["close_to_vwap"] > 0


def test_build_lhb_phase12a_multi_context_decision_v1_maps_context_and_confirmation(tmp_path):
    selected_trades = pd.DataFrame(
        [
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 5,
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "selection_rank": 1,
                "selection_score": 90,
                "future_1d_return": 0.05,
                "future_3d_return": 0.08,
                "future_5d_return": 0.12,
                "future_10d_return": 0.15,
                "future_5d_max_drawdown": -0.02,
            },
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 5,
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "selection_rank": 2,
                "selection_score": 80,
                "future_1d_return": -0.03,
                "future_3d_return": -0.05,
                "future_5d_return": -0.08,
                "future_10d_return": -0.10,
                "future_5d_max_drawdown": -0.12,
            },
            {
                "pool_mode": "raw_lhb_positive",
                "top_n": 5,
                "trade_date": "2026-03-05",
                "ts_code": "600003.SH",
                "selection_rank": 3,
                "selection_score": 70,
                "future_1d_return": 0.01,
                "future_3d_return": 0.00,
                "future_5d_return": -0.01,
                "future_10d_return": -0.02,
                "future_5d_max_drawdown": -0.08,
            },
        ]
    )
    intraday_detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "intraday_confirmation_action": "confirm_follow",
                "intraday_confirmation_reason": "first_60m_and_vwap_confirmed",
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "intraday_confirmation_action": "reject_follow",
                "intraday_confirmation_reason": "weak_first_60m",
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600003.SH",
                "intraday_confirmation_action": "confirm_but_chase_control",
                "intraday_confirmation_reason": "morning_fade_chase_control",
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000,
                "amount": close * 1000,
            }
            for trade_date, ts_code, rows in [
                (
                    "2026-03-04",
                    "600001.SH",
                    [
                        ("2026-03-04 09:35:00", 10.0, 10.1, 9.9, 10.0),
                        ("2026-03-04 15:00:00", 10.0, 10.6, 10.0, 10.5),
                    ],
                ),
                (
                    "2026-03-05",
                    "600001.SH",
                    [
                        ("2026-03-05 09:35:00", 10.6, 10.8, 10.5, 10.7),
                        ("2026-03-05 15:00:00", 10.7, 11.3, 10.7, 11.2),
                    ],
                ),
                (
                    "2026-03-05",
                    "600002.SH",
                    [
                        ("2026-03-05 09:35:00", 10.0, 10.8, 9.9, 10.6),
                        ("2026-03-05 15:00:00", 10.6, 10.7, 9.4, 9.5),
                    ],
                ),
                (
                    "2026-03-05",
                    "600003.SH",
                    [
                        ("2026-03-05 09:35:00", 10.0, 10.3, 9.9, 10.2),
                        ("2026-03-05 15:00:00", 10.2, 10.5, 10.0, 10.1),
                    ],
                ),
            ]
            for trade_time, open_, high, low, close in rows
        ]
    )

    result = lhb_data.build_lhb_phase12a_multi_context_decision_v1(
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        intraday_detail=intraday_detail,
        output_dir=tmp_path,
    )

    decision = result["decision"].set_index("ts_code")
    assert decision.loc["600001.SH", "pre_event_context_type"] == "preheated"
    assert decision.loc["600001.SH", "event_day_context_type"] == "event_day_strong"
    assert decision.loc["600001.SH", "lhb_phase12a_decision"] == "follow_pool"
    assert decision.loc["600001.SH", "can_follow"] is True
    assert decision.loc["600002.SH", "event_day_context_type"] == "event_day_failed"
    assert decision.loc["600002.SH", "lhb_phase12a_decision"] == "retreat_signal"
    assert decision.loc["600002.SH", "should_retreat"] is True
    assert decision.loc["600003.SH", "lhb_phase12a_decision"] == "chase_control_pool"
    assert "no_chase" in decision.loc["600003.SH", "position_note"]

    summary = result["summary"].set_index("lhb_phase12a_decision")
    assert summary.loc["follow_pool", "candidate_count"] == 1
    assert summary.loc["retreat_signal", "avg_future_5d_return"] == -0.08
    assert Path(result["paths"]["decision"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase12a_rule_decision_v1_splits_follow_and_risk_layers(tmp_path):
    phase12a_decision = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "lhb_phase12a_decision": "follow_pool",
                "pre_event_context_type": "preheated",
                "event_day_context_type": "event_day_strong",
                "intraday_confirmation_action": "confirm_follow",
                "future_1d_return": 0.08,
                "future_3d_return": 0.11,
                "future_5d_return": 0.15,
                "future_10d_return": 0.20,
                "future_5d_max_drawdown": -0.03,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 5,
                "lhb_phase12a_decision": "follow_pool",
                "pre_event_context_type": "quiet_pre_event",
                "event_day_context_type": "event_day_neutral",
                "intraday_confirmation_action": "confirm_follow",
                "future_1d_return": 0.03,
                "future_3d_return": 0.04,
                "future_5d_return": 0.06,
                "future_10d_return": 0.07,
                "future_5d_max_drawdown": -0.02,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600003.SH",
                "top_n": 5,
                "lhb_phase12a_decision": "follow_pool",
                "pre_event_context_type": "pre_event_weak",
                "event_day_context_type": "event_day_strong",
                "intraday_confirmation_action": "confirm_follow",
                "future_1d_return": 0.01,
                "future_3d_return": 0.02,
                "future_5d_return": 0.03,
                "future_10d_return": 0.02,
                "future_5d_max_drawdown": -0.05,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600004.SH",
                "top_n": 5,
                "lhb_phase12a_decision": "retreat_signal",
                "pre_event_context_type": "preheated",
                "event_day_context_type": "event_day_strong",
                "intraday_confirmation_action": "reject_follow",
                "future_1d_return": -0.03,
                "future_3d_return": -0.04,
                "future_5d_return": -0.08,
                "future_10d_return": -0.09,
                "future_5d_max_drawdown": -0.12,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600005.SH",
                "top_n": 5,
                "lhb_phase12a_decision": "chase_control_pool",
                "pre_event_context_type": "preheated",
                "event_day_context_type": "event_day_strong",
                "intraday_confirmation_action": "confirm_but_chase_control",
                "future_1d_return": 0.02,
                "future_3d_return": 0.01,
                "future_5d_return": 0.01,
                "future_10d_return": -0.02,
                "future_5d_max_drawdown": -0.08,
            },
        ]
    )

    result = lhb_data.build_lhb_phase12a_rule_decision_v1(
        phase12a_decision=phase12a_decision,
        output_dir=tmp_path,
    )

    decision = result["rule_decision"].set_index("ts_code")
    assert decision.loc["600001.SH", "phase12a_rule_layer"] == "follow_pool_high_confidence"
    assert decision.loc["600002.SH", "phase12a_rule_layer"] == "follow_pool_low_drawdown"
    assert decision.loc["600003.SH", "phase12a_rule_layer"] == "follow_pool_core"
    assert decision.loc["600004.SH", "phase12a_rule_layer"] == "retreat_hard"
    assert decision.loc["600005.SH", "phase12a_rule_layer"] == "chase_control"
    assert decision.loc["600001.SH", "phase12a_rule_action"] == "follow_allowed"
    assert decision.loc["600004.SH", "phase12a_rule_action"] == "retreat"
    assert decision.loc["600005.SH", "phase12a_rule_action"] == "no_chase_watch_pullback"

    summary = result["summary"].set_index("phase12a_rule_layer")
    assert summary.loc["follow_pool_high_confidence", "candidate_count"] == 1
    assert summary.loc["retreat_hard", "avg_future_5d_return"] == -0.08
    assert Path(result["paths"]["rule_decision"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase12a_real_entry_backtest_v1_uses_next_bar_entry(tmp_path):
    rule_decision = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "phase12a_rule_action": "follow_allowed",
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 5,
                "phase12a_rule_layer": "retreat_hard",
                "phase12a_rule_action": "retreat",
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-06",
                "ts_code": "600001.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount,
            }
            for trade_time, open_, high, low, close, volume, amount in [
                ("2026-03-06 09:35:00", 10.00, 10.20, 9.95, 10.10, 1000, 10100),
                ("2026-03-06 10:30:00", 10.10, 10.50, 10.10, 10.40, 1000, 10400),
                ("2026-03-06 10:35:00", 10.50, 10.80, 10.45, 10.70, 1000, 10700),
            ]
        ]
    )
    daily_bars = pd.DataFrame(
        [
            {"trade_date": "2026-03-06", "ts_code": "600001.SH", "close": 11.00},
            {"trade_date": "2026-03-09", "ts_code": "600001.SH", "close": 12.00},
            {"trade_date": "2026-03-10", "ts_code": "600001.SH", "close": 10.00},
        ]
    )

    result = lhb_data.build_lhb_phase12a_real_entry_backtest_v1(
        rule_decision=rule_decision,
        minute_bars=minute_bars,
        daily_bars=daily_bars,
        output_dir=tmp_path,
        entry_start_time="10:30:00",
    )

    trades = result["trades"].set_index("ts_code")
    assert trades.loc["600001.SH", "fill_status"] == "filled"
    assert trades.loc["600001.SH", "entry_signal_time"] == "10:30:00"
    assert trades.loc["600001.SH", "entry_time"] == "10:35:00"
    assert trades.loc["600001.SH", "entry_price"] == 10.50
    assert round(float(trades.loc["600001.SH", "exit_0d_return"]), 6) == round(11.00 / 10.50 - 1.0, 6)
    assert round(float(trades.loc["600001.SH", "exit_1d_return"]), 6) == round(12.00 / 10.50 - 1.0, 6)
    assert trades.loc["600002.SH", "fill_status"] == "not_follow_allowed"

    summary = result["summary"].set_index("phase12a_rule_layer")
    assert summary.loc["follow_pool_high_confidence", "filled_count"] == 1
    assert summary.loc["follow_pool_high_confidence", "avg_exit_1d_return"] == trades.loc["600001.SH", "exit_1d_return"]
    assert Path(result["paths"]["trades"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_phase12a_real_entry_skips_locked_limit_up_execution(tmp_path):
    rule_decision = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-06",
                "ts_code": "600001.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": close * volume,
            }
            for trade_time, open_, high, low, close, volume in [
                ("2026-03-06 09:35:00", 10.00, 10.20, 9.95, 10.10, 1000),
                ("2026-03-06 10:30:00", 10.10, 10.60, 10.10, 10.50, 1000),
                ("2026-03-06 10:35:00", 11.00, 11.00, 11.00, 11.00, 0),
            ]
        ]
    )

    result = lhb_data.build_lhb_phase12a_real_entry_backtest_v1(
        rule_decision=rule_decision,
        minute_bars=minute_bars,
        daily_bars=pd.DataFrame(),
        output_dir=tmp_path,
        entry_start_time="10:30:00",
    )

    trade = result["trades"].iloc[0]
    assert trade["fill_status"] == "entry_signal_locked_limit_up"
    assert trade["blocked_entry_bar_count"] == 1


def test_build_lhb_phase12b_signal_exit_v1_starts_after_entry_day_and_exits_next_bar(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 10.50,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "no_entry_signal",
                "confirmation_trade_date": "",
                "entry_time": "",
                "entry_price": pd.NA,
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": "600001.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000,
                "amount": close * 1000,
            }
            for trade_date, rows in [
                (
                    "2026-03-06",
                    [
                        ("2026-03-06 14:55:00", 10.4, 10.6, 10.3, 10.4),
                        ("2026-03-06 15:00:00", 10.4, 10.5, 10.3, 10.4),
                    ],
                ),
                (
                    "2026-03-09",
                    [
                        ("2026-03-09 09:35:00", 10.8, 10.9, 10.6, 10.7),
                        ("2026-03-09 10:30:00", 10.7, 10.8, 10.2, 10.3),
                        ("2026-03-09 10:35:00", 10.2, 10.3, 10.0, 10.1),
                    ],
                ),
            ]
            for trade_time, open_, high, low, close in rows
        ]
    )

    result = lhb_data.build_lhb_phase12b_signal_exit_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
        max_hold_days=5,
    )

    exits = result["exit_trades"].set_index("ts_code")
    assert exits.loc["600001.SH", "exit_status"] == "signal_exit"
    assert exits.loc["600001.SH", "exit_signal"] == "break_entry_price"
    assert exits.loc["600001.SH", "exit_signal_trade_date"] == "2026-03-09"
    assert exits.loc["600001.SH", "exit_signal_time"] == "10:30:00"
    assert exits.loc["600001.SH", "exit_trade_date"] == "2026-03-09"
    assert exits.loc["600001.SH", "exit_time"] == "10:35:00"
    assert exits.loc["600001.SH", "exit_price"] == 10.2
    assert round(float(exits.loc["600001.SH", "realized_return"]), 6) == round(10.2 / 10.5 - 1.0, 6)
    assert exits.loc["600002.SH", "exit_status"] == "not_filled"

    summary = result["summary"].set_index("phase12a_rule_layer")
    assert summary.loc["follow_pool_high_confidence", "signal_exit_count"] == 1
    assert summary.loc["follow_pool_high_confidence", "avg_realized_return"] == exits.loc["600001.SH", "realized_return"]
    assert Path(result["paths"]["exit_trades"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_phase14_lifecycle_exit_blocks_locked_limit_down_until_open(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 10.00,
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": "600001.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": close * volume,
            }
            for trade_date, rows in [
                (
                    "2026-03-09",
                    [
                        ("2026-03-09 09:35:00", 9.00, 9.00, 9.00, 9.00, 0),
                        ("2026-03-09 09:40:00", 9.00, 9.00, 9.00, 9.00, 0),
                        ("2026-03-09 09:45:00", 9.00, 9.05, 8.95, 9.02, 1000),
                        ("2026-03-09 09:50:00", 9.03, 9.10, 9.00, 9.08, 1000),
                    ],
                ),
            ]
            for trade_time, open_, high, low, close, volume in rows
        ]
    )

    result = lhb_data.build_lhb_phase14_lifecycle_exit_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
        max_hold_days=5,
    )

    trade = result["lifecycle_trades"].iloc[0]
    assert trade["exit_status"] == "signal_exit"
    assert trade["exit_signal"] == "break_entry_price"
    assert trade["exit_trade_date"] == "2026-03-09"
    assert trade["exit_time"] == "09:50:00"
    assert trade["exit_price"] == 9.03
    assert trade["blocked_exit_bar_count"] == 2
    assert trade["blocked_exit_reason"] == "locked_limit_down"


def test_build_lhb_phase14_lifecycle_exit_v1_uses_t1_exit_signals(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 10.50,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 20.00,
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": close * volume,
            }
            for ts_code, days in [
                (
                    "600001.SH",
                    [
                        (
                            "2026-03-06",
                            [
                                ("2026-03-06 14:55:00", 10.6, 10.7, 10.4, 10.6, 1000),
                            ],
                        ),
                        (
                            "2026-03-09",
                            [
                                ("2026-03-09 09:35:00", 11.50, 11.60, 11.30, 11.50, 5000),
                                ("2026-03-09 10:30:00", 11.40, 11.45, 10.80, 10.90, 4000),
                                ("2026-03-09 10:35:00", 10.85, 10.90, 10.50, 10.60, 3000),
                            ],
                        ),
                    ],
                ),
                (
                    "600002.SH",
                    [
                        (
                            "2026-03-09",
                            [
                                ("2026-03-09 09:35:00", 20.20, 20.40, 20.10, 20.30, 1000),
                                ("2026-03-09 14:55:00", 20.30, 20.35, 20.20, 20.30, 1000),
                                ("2026-03-09 15:00:00", 20.30, 20.40, 20.20, 20.35, 1000),
                            ],
                        ),
                    ],
                ),
            ]
            for trade_date, rows in days
            for trade_time, open_, high, low, close, volume in rows
        ]
    )

    result = lhb_data.build_lhb_phase14_lifecycle_exit_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
        max_hold_days=2,
    )

    trades = result["lifecycle_trades"].set_index("ts_code")
    assert trades.loc["600001.SH", "exit_status"] == "signal_exit"
    assert trades.loc["600001.SH", "exit_signal"] == "vwap_break_with_distribution"
    assert trades.loc["600001.SH", "exit_signal_trade_date"] == "2026-03-09"
    assert trades.loc["600001.SH", "exit_time"] == "10:35:00"
    assert trades.loc["600001.SH", "exit_price"] == 10.85
    assert round(float(trades.loc["600001.SH", "realized_return"]), 6) == round(10.85 / 10.50 - 1.0, 6)
    assert trades.loc["600002.SH", "exit_status"] == "max_hold_exit"
    assert trades.loc["600002.SH", "exit_signal"] == "max_hold_days"

    summary = result["summary"].set_index("phase12a_rule_layer")
    assert summary.loc["follow_pool_high_confidence", "signal_exit_count"] == 1
    assert summary.loc["follow_pool_core", "fallback_exit_count"] == 1
    assert Path(result["paths"]["lifecycle_trades"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase14b_threshold_scan_v1_ranks_profiles(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 10.00,
            }
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-09",
                "ts_code": "600001.SH",
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": close * volume,
            }
            for trade_time, open_, high, low, close, volume in [
                ("2026-03-09 09:35:00", 10.20, 10.30, 10.10, 10.25, 1000),
                ("2026-03-09 10:30:00", 10.25, 10.30, 10.00, 10.05, 1000),
                ("2026-03-09 10:35:00", 10.00, 10.05, 9.80, 9.90, 1000),
            ]
        ]
    )

    result = lhb_data.build_lhb_phase14b_threshold_scan_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
        max_hold_days=5,
    )

    ranking = result["profile_ranking"]
    assert not ranking.empty
    assert {"sensitive_vwap", "base_v1"}.issubset(set(ranking["threshold_profile"]))
    assert ranking.iloc[0]["rank_score"] >= ranking.iloc[-1]["rank_score"]
    best_trades = result["best_lifecycle_trades"]
    assert best_trades["threshold_profile"].nunique() == 1
    assert Path(result["paths"]["profile_ranking"]).exists()
    assert Path(result["paths"]["threshold_summary"]).exists()
    assert Path(result["paths"]["best_lifecycle_trades"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase14c_lifecycle_portfolio_v1_uses_sensitive_default_and_curve(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 10.00,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "phase12a_rule_action": "follow_allowed",
                "fill_status": "filled",
                "confirmation_trade_date": "2026-03-06",
                "entry_time": "10:35:00",
                "entry_price": 20.00,
            },
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "trade_time": trade_time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000,
                "amount": close * 1000,
            }
            for ts_code, rows in [
                (
                    "600001.SH",
                    [
                        ("2026-03-09", "2026-03-09 09:35:00", 10.20, 10.30, 10.10, 10.25),
                        ("2026-03-09", "2026-03-09 10:30:00", 10.25, 10.30, 10.00, 10.05),
                        ("2026-03-09", "2026-03-09 10:35:00", 10.00, 10.05, 9.80, 9.90),
                    ],
                ),
                (
                    "600002.SH",
                    [
                        ("2026-03-09", "2026-03-09 09:35:00", 20.20, 20.40, 20.10, 20.30),
                        ("2026-03-09", "2026-03-09 15:00:00", 20.30, 20.40, 20.20, 20.35),
                    ],
                ),
            ]
            for trade_date, trade_time, open_, high, low, close in rows
        ]
    )

    result = lhb_data.build_lhb_phase14c_lifecycle_portfolio_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
        max_hold_days=5,
    )

    trades = result["lifecycle_trades"]
    assert trades["threshold_profile"].unique().tolist() == ["sensitive_entry_buffer"]
    assert set(trades["exit_status"]) == {"signal_exit", "max_hold_exit"}
    curve = result["daily_curve"]
    assert curve.loc[0, "top_n"] == 5
    assert curve.loc[0, "exit_trade_date"] == "2026-03-09"
    assert curve.loc[0, "closed_trade_count"] == 2
    assert curve.loc[0, "equity"] == 1.0 + curve.loc[0, "daily_realized_return"]
    summary = result["summary"].set_index("top_n")
    assert summary.loc[5, "filled_count"] == 2
    assert summary.loc[5, "final_equity"] == curve.loc[0, "equity"]
    assert Path(result["paths"]["lifecycle_trades"]).exists()
    assert Path(result["paths"]["daily_curve"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase14e_limit_lock_filter_v1_audits_and_ranks_filters(tmp_path):
    entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "blocked_entry_bar_count": 0,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "entry_signal_locked_limit_up",
                "blocked_entry_bar_count": 36,
                "blocked_entry_reason": "locked_limit_up",
            },
        ]
    )
    lifecycle_trades = pd.DataFrame(
        [
            {
                "threshold_profile": "sensitive_entry_buffer",
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "exit_status": "signal_exit",
                "realized_return": 0.08,
                "holding_trade_days": 1,
                "exit_trade_date": "2026-03-09",
                "blocked_exit_bar_count": 0,
            },
            {
                "threshold_profile": "sensitive_entry_buffer",
                "trade_date": "2026-03-06",
                "ts_code": "600003.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "exit_status": "signal_exit",
                "realized_return": -0.16,
                "holding_trade_days": 2,
                "exit_trade_date": "2026-03-10",
                "blocked_exit_bar_count": 48,
                "blocked_exit_reason": "locked_limit_down",
            },
        ]
    )

    result = lhb_data.build_lhb_phase14e_limit_lock_filter_v1(
        entry_trades=entry_trades,
        lifecycle_trades=lifecycle_trades,
        output_dir=tmp_path,
    )

    audit = result["risk_audit"].set_index("risk_type")
    assert audit.loc["blocked_entry_locked_limit_up", "event_count"] == 1
    assert audit.loc["blocked_exit_locked_limit_down", "event_count"] == 1

    ranking = result["filter_ranking"]
    assert {"baseline", "exclude_blocked_exit_history"}.issubset(set(ranking["filter_profile"]))
    assert ranking.iloc[0]["rank_score"] >= ranking.iloc[-1]["rank_score"]
    best_summary = result["best_summary"].set_index("top_n")
    assert best_summary.loc[10, "closed_trade_count"] == 1
    assert best_summary.loc[10, "max_drawdown"] == 0.0
    assert Path(result["paths"]["risk_audit"]).exists()
    assert Path(result["paths"]["filter_ranking"]).exists()
    assert Path(result["paths"]["best_trades"]).exists()
    assert Path(result["paths"]["best_summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase15_cash_account_backtest_v1_uses_cash_and_skips_duplicate_positions(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.00,
                "exit_trade_date": "2026-03-09",
                "exit_price": 11.00,
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-07",
                "entry_price": 10.50,
                "exit_trade_date": "2026-03-10",
                "exit_price": 11.50,
                "realized_return": 0.095238,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 20.00,
                "exit_trade_date": "2026-03-10",
                "exit_price": 18.00,
                "realized_return": -0.10,
            },
        ]
    )

    result = lhb_data.build_lhb_phase15_cash_account_backtest_v1(
        lifecycle_trades=lifecycle_trades,
        output_dir=tmp_path,
        max_positions=10,
        position_pct=0.10,
    )

    trades = result["account_trades"]
    assert trades["account_trade_status"].tolist() == ["filled", "duplicate_position_skipped", "filled"]
    curve = result["account_curve"].set_index("trade_date")
    assert round(float(curve.loc["2026-03-06", "cash"]), 6) == 0.90
    assert round(float(curve.loc["2026-03-09", "equity"]), 6) == 1.01
    assert round(float(curve.loc["2026-03-10", "equity"]), 6) == 0.9999
    summary = result["summary"].iloc[0]
    assert summary["filled_trade_count"] == 2
    assert summary["skipped_duplicate_count"] == 1
    assert Path(result["paths"]["account_trades"]).exists()
    assert Path(result["paths"]["account_curve"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase16_quality_improvement_diagnostics_v1_flags_bad_buys_and_early_exits(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "exit_status": "signal_exit",
                "exit_signal": "break_entry_price",
                "exit_reason": "close_below_entry_price_after_t1",
                "exit_trade_date": "2026-03-07",
                "realized_return": -0.02,
                "blocked_exit_bar_count": 0,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "exit_status": "signal_exit",
                "exit_signal": "vwap_break_with_distribution",
                "exit_reason": "close_below_vwap_after_intraday_fade",
                "exit_trade_date": "2026-03-07",
                "realized_return": 0.08,
                "blocked_exit_bar_count": 0,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600003.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_low_drawdown",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "exit_status": "signal_exit",
                "exit_signal": "break_entry_price",
                "exit_reason": "close_below_entry_price_after_t1",
                "exit_trade_date": "2026-03-10",
                "realized_return": -0.06,
                "blocked_exit_bar_count": 0,
            },
        ]
    )
    real_entry_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "exit_5d_return": 0.12, "max_drawdown_to_5d": -0.03},
            {"trade_date": "2026-03-05", "ts_code": "600002.SH", "exit_5d_return": 0.09, "max_drawdown_to_5d": -0.02},
            {"trade_date": "2026-03-06", "ts_code": "600003.SH", "exit_5d_return": -0.10, "max_drawdown_to_5d": -0.12},
        ]
    )
    selected_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "selection_score": 50.0,
                "lhb_net_buy_ratio": 0.10,
                "lhb_one_day_pump_risk": 0.80,
                "lhb_after_break_limit": True,
                "lhb_after_reversal": False,
            },
            {
                "trade_date": "2026-03-05",
                "ts_code": "600002.SH",
                "selection_score": 500.0,
                "lhb_net_buy_ratio": 0.60,
                "lhb_one_day_pump_risk": 0.10,
                "lhb_after_break_limit": False,
                "lhb_after_reversal": False,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600003.SH",
                "selection_score": 100.0,
                "lhb_net_buy_ratio": 0.20,
                "lhb_one_day_pump_risk": 0.60,
                "lhb_after_break_limit": True,
                "lhb_after_reversal": True,
            },
        ]
    )

    result = lhb_data.build_lhb_phase16_quality_improvement_diagnostics_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=tmp_path,
        min_group_count=1,
    )

    low_quality = result["low_quality_buy_diagnostics"]
    pump_row = low_quality[low_quality["diagnostic_group"].eq("lhb_one_day_pump_risk_high")].iloc[0]
    assert pump_row["closed_trade_count"] == 2
    assert pump_row["win_rate"] == 0.0
    exit_mistakes = result["exit_mistake_diagnostics"].set_index("ts_code")
    assert exit_mistakes.loc["600001.SH", "exit_mistake_type"] == "early_exit_positive_5d"
    assert round(float(exit_mistakes.loc["600001.SH", "missed_return_vs_5d"]), 6) == 0.14
    scan = result["filter_scan"].set_index("filter_profile")
    assert scan.loc["baseline", "closed_trade_count"] == 3
    assert scan.loc["exclude_high_pump_risk", "closed_trade_count"] == 1
    assert scan.loc["exclude_high_pump_risk", "win_rate"] > scan.loc["baseline", "win_rate"]
    assert Path(result["paths"]["low_quality_buy_diagnostics"]).exists()
    assert Path(result["paths"]["exit_mistake_diagnostics"]).exists()
    assert Path(result["paths"]["filter_scan"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase16b_limit_break_failed_exit_replay_v1_compares_hold_horizons(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.0,
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "exit_reason": "intraday_high_near_limit_but_failed_close_below_vwap",
                "exit_trade_date": "2026-03-07",
                "exit_price": 11.0,
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 20.0,
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "exit_reason": "intraday_high_near_limit_but_failed_close_below_vwap",
                "exit_trade_date": "2026-03-10",
                "exit_price": 22.0,
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600003.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 30.0,
                "exit_status": "signal_exit",
                "exit_signal": "break_entry_price",
                "exit_reason": "close_below_entry_price_after_t1",
                "exit_trade_date": "2026-03-10",
                "exit_price": 29.0,
                "realized_return": -0.033333,
            },
        ]
    )
    real_entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "exit_1d_return": 0.12,
                "exit_2d_return": 0.25,
                "exit_3d_return": 0.20,
                "exit_5d_return": 0.18,
                "max_drawdown_to_5d": -0.02,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "exit_1d_return": 0.08,
                "exit_2d_return": 0.05,
                "exit_3d_return": 0.02,
                "exit_5d_return": -0.02,
                "max_drawdown_to_5d": -0.08,
            },
        ]
    )
    selected_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "selection_score": 600.0, "lhb_net_buy_ratio": 0.50},
            {"trade_date": "2026-03-06", "ts_code": "600002.SH", "selection_score": 100.0, "lhb_net_buy_ratio": 0.10},
        ]
    )

    result = lhb_data.build_lhb_phase16b_limit_break_failed_exit_replay_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=tmp_path,
    )

    opportunities = result["opportunity_trades"].set_index("ts_code")
    assert set(opportunities.index) == {"600001.SH", "600002.SH"}
    assert round(float(opportunities.loc["600001.SH", "missed_return_to_2d"]), 6) == 0.15
    strategy = result["strategy_summary"].set_index("strategy")
    assert strategy.loc["current_exit", "avg_return"] == 0.10
    assert strategy.loc["hold_to_2d", "avg_return"] == 0.15
    assert strategy.loc["hold_to_5d", "avg_return"] == 0.08
    candidate = result["candidate_summary"].set_index("candidate_profile")
    assert candidate.loc["strong_lhb_quality", "trade_count"] == 1
    assert candidate.loc["strong_lhb_quality", "avg_missed_return_to_2d"] == 0.15
    assert Path(result["paths"]["opportunity_trades"]).exists()
    assert Path(result["paths"]["strategy_summary"]).exists()
    assert Path(result["paths"]["candidate_summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase16c_limit_break_failed_rule_scan_v1_tests_full_strategy_replacement(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "exit_signal": "limit_break_failed",
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "exit_signal": "break_entry_price",
                "realized_return": -0.05,
            },
        ]
    )
    real_entry_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "exit_2d_return": 0.20,
                "exit_3d_return": 0.30,
                "exit_5d_return": 0.15,
            }
        ]
    )
    selected_trades = pd.DataFrame(
        [{"trade_date": "2026-03-05", "ts_code": "600001.SH", "selection_score": 500.0, "lhb_net_buy_ratio": 0.50}]
    )

    result = lhb_data.build_lhb_phase16c_limit_break_failed_rule_scan_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=tmp_path,
    )

    summary = result["rule_scan_summary"].set_index("rule_profile")
    assert summary.loc["baseline_current_exit", "closed_trade_count"] == 2
    assert summary.loc["baseline_current_exit", "avg_realized_return"] == 0.025
    assert summary.loc["delay_all_limit_break_failed_to_3d", "avg_realized_return"] == 0.125
    assert summary.loc["delay_all_limit_break_failed_to_3d", "adjusted_trade_count"] == 1
    adjusted = result["adjusted_trades"]
    row = adjusted[adjusted["rule_profile"].eq("delay_all_limit_break_failed_to_3d") & adjusted["ts_code"].eq("600001.SH")].iloc[0]
    assert row["realized_return"] == 0.30
    assert row["original_realized_return"] == 0.10
    assert row["phase16c_adjust_reason"] == "limit_break_failed_delay_to_3d"
    assert Path(result["paths"]["adjusted_trades"]).exists()
    assert Path(result["paths"]["rule_scan_summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase16d_limit_break_failed_indicator_discovery_v1_finds_hold_indicators(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.0,
                "exit_trade_date": "2026-03-07",
                "exit_price": 11.0,
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 20.0,
                "exit_trade_date": "2026-03-10",
                "exit_price": 21.0,
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "realized_return": 0.05,
            },
        ]
    )
    real_entry_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "exit_3d_return": 0.25, "exit_5d_return": 0.20},
            {"trade_date": "2026-03-06", "ts_code": "600002.SH", "exit_3d_return": 0.00, "exit_5d_return": -0.05},
        ]
    )
    selected_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "selection_score": 500.0, "lhb_net_buy_ratio": 0.50},
            {"trade_date": "2026-03-06", "ts_code": "600002.SH", "selection_score": 120.0, "lhb_net_buy_ratio": 0.10},
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {"trade_date": "2026-03-07", "ts_code": "600001.SH", "trade_time": "2026-03-07 09:35:00", "open": 10.8, "high": 11.0, "low": 10.7, "close": 10.9, "volume": 100, "amount": 1090},
            {"trade_date": "2026-03-07", "ts_code": "600001.SH", "trade_time": "2026-03-07 14:55:00", "open": 10.9, "high": 11.5, "low": 10.8, "close": 11.4, "volume": 100, "amount": 1140},
            {"trade_date": "2026-03-08", "ts_code": "600001.SH", "trade_time": "2026-03-08 09:35:00", "open": 11.5, "high": 11.8, "low": 11.4, "close": 11.7, "volume": 100, "amount": 1170},
            {"trade_date": "2026-03-10", "ts_code": "600002.SH", "trade_time": "2026-03-10 09:35:00", "open": 21.0, "high": 21.2, "low": 20.5, "close": 20.6, "volume": 100, "amount": 2060},
            {"trade_date": "2026-03-10", "ts_code": "600002.SH", "trade_time": "2026-03-10 14:55:00", "open": 20.6, "high": 20.7, "low": 19.8, "close": 20.0, "volume": 100, "amount": 2000},
            {"trade_date": "2026-03-11", "ts_code": "600002.SH", "trade_time": "2026-03-11 09:35:00", "open": 19.9, "high": 20.0, "low": 19.5, "close": 19.6, "volume": 100, "amount": 1960},
        ]
    )

    result = lhb_data.build_lhb_phase16d_limit_break_failed_indicator_discovery_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
    )

    detail = result["indicator_detail"].set_index("ts_code")
    assert detail.loc["600001.SH", "hold_label"] == "good_hold"
    assert detail.loc["600002.SH", "hold_label"] == "should_exit"
    assert detail.loc["600001.SH", "exit_day_close_position"] > detail.loc["600002.SH", "exit_day_close_position"]
    summary = result["indicator_summary"].set_index("indicator_rule")
    assert summary.loc["exit_day_close_position_ge_0_70", "matched_count"] == 1
    assert summary.loc["exit_day_close_position_ge_0_70", "good_hold_rate"] == 1.0
    assert Path(result["paths"]["indicator_detail"]).exists()
    assert Path(result["paths"]["indicator_summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_build_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1_tests_vwap_rule(tmp_path):
    lifecycle_trades = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.0,
                "exit_trade_date": "2026-03-07",
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "realized_return": 0.10,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600002.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 20.0,
                "exit_trade_date": "2026-03-10",
                "exit_status": "signal_exit",
                "exit_signal": "limit_break_failed",
                "realized_return": 0.05,
            },
            {
                "trade_date": "2026-03-06",
                "ts_code": "600003.SH",
                "top_n": 10,
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-03-09",
                "entry_price": 30.0,
                "exit_trade_date": "2026-03-10",
                "exit_status": "signal_exit",
                "exit_signal": "break_entry_price",
                "realized_return": -0.05,
            },
        ]
    )
    real_entry_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "exit_3d_return": 0.30},
            {"trade_date": "2026-03-06", "ts_code": "600002.SH", "exit_3d_return": 0.20},
        ]
    )
    selected_trades = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "ts_code": "600001.SH", "selection_score": 500.0, "lhb_net_buy_ratio": 0.50},
            {"trade_date": "2026-03-06", "ts_code": "600002.SH", "selection_score": 100.0, "lhb_net_buy_ratio": 0.10},
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {"trade_date": "2026-03-07", "ts_code": "600001.SH", "trade_time": "2026-03-07 09:35:00", "open": 10.8, "high": 11.0, "low": 10.7, "close": 10.9, "volume": 100, "amount": 1090},
            {"trade_date": "2026-03-07", "ts_code": "600001.SH", "trade_time": "2026-03-07 14:55:00", "open": 10.9, "high": 11.5, "low": 10.8, "close": 11.4, "volume": 100, "amount": 1140},
            {"trade_date": "2026-03-10", "ts_code": "600002.SH", "trade_time": "2026-03-10 09:35:00", "open": 21.0, "high": 21.2, "low": 20.5, "close": 20.6, "volume": 100, "amount": 2060},
            {"trade_date": "2026-03-10", "ts_code": "600002.SH", "trade_time": "2026-03-10 14:55:00", "open": 20.6, "high": 20.7, "low": 19.8, "close": 20.0, "volume": 100, "amount": 2000},
        ]
    )

    result = lhb_data.build_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        output_dir=tmp_path,
    )

    summary = result["rule_scan_summary"].set_index("rule_profile")
    assert summary.loc["baseline_current_exit", "avg_realized_return"] == round((0.10 + 0.05 - 0.05) / 3, 6)
    assert summary.loc["delay_if_exit_day_close_vs_vwap_ge_0_to_3d", "adjusted_trade_count"] == 1
    assert summary.loc["delay_if_exit_day_close_vs_vwap_ge_0_to_3d", "avg_realized_return"] == round((0.30 + 0.05 - 0.05) / 3, 6)
    adjusted = result["adjusted_trades"]
    row = adjusted[
        adjusted["rule_profile"].eq("delay_if_exit_day_close_vs_vwap_ge_0_to_3d")
        & adjusted["ts_code"].eq("600001.SH")
    ].iloc[0]
    assert row["phase16e_adjust_reason"] == "exit_day_close_vs_vwap_ge_0_delay_to_3d"
    assert row["realized_return"] == 0.30
    assert Path(result["paths"]["adjusted_trades"]).exists()
    assert Path(result["paths"]["rule_scan_summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_dragon_cross_handles_missing_optional_files(tmp_path):
    result = lhb_data.run_lhb_risk_feature_diagnostics(
        case_path=_write_csv(tmp_path, "cases.csv", _sample_lhb_curated()),
        lhb_features_path=_write_csv(tmp_path, "features.csv", _sample_lhb_features()),
        alignment_path=_write_csv(tmp_path, "alignment.csv", _sample_lhb_alignment()),
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["dragon_risk_cross_diagnostics"]).exists()
    assert result["warnings"]
    assert result["dragon_risk_cross_diagnostics"].empty


def test_lhb_coverage_failure_plan_prioritizes_failure_gaps(tmp_path):
    result = lhb_data.build_lhb_coverage_and_failure_rule_plan(
        coverage_gaps=_sample_lhb_coverage_gaps(),
        curated=_sample_lhb_curated_extended(),
        case_factor_snapshot=_sample_case_factor_snapshot(),
        output_dir=tmp_path,
    )
    plan = result["coverage_expansion_plan"]

    assert plan.iloc[0]["verified_case_type"] == "a_kill_failure"
    assert plan.iloc[0]["priority_for_lhb_backfill"] < plan[plan["verified_case_type"] == "second_wave"].iloc[0]["priority_for_lhb_backfill"]
    a_kill = plan[plan["verified_case_type"] == "a_kill_failure"].iloc[0]
    failed_wave = plan[plan["verified_case_type"] == "failed_second_wave"].iloc[0]
    assert a_kill["query_window_days_after"] == 10
    assert failed_wave["query_window_days_after"] == 10
    assert Path(result["paths"]["coverage_expansion_plan"]).exists()


def test_lhb_coverage_failure_plan_outputs_summary_script_audit_and_suggestions(tmp_path):
    result = lhb_data.build_lhb_coverage_and_failure_rule_plan(
        coverage_gaps=_sample_lhb_coverage_gaps(),
        curated=_sample_lhb_curated_extended(),
        case_factor_snapshot=_sample_case_factor_snapshot(),
        output_dir=tmp_path,
    )

    assert not result["coverage_expansion_summary"].empty
    script = Path(result["paths"]["next_commands"]).read_text(encoding="utf-8")
    assert "Top 5 priority cases" in script
    assert "# stock-research lhb-sample-import" in script
    assert "TODO: do not run full-market LHB backfill" in script
    assert not result["failure_rule_audit"].empty
    suggestions = result["failure_rule_suggestions"]
    assert {"failed_reversal", "high_open_low_close_failure", "one_day_pump"}.issubset(set(suggestions["case_type"]))
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "LHB Coverage Expansion & Failure Rule Refinement Plan v1" in report
    assert "## 6. 规则修正建议" in report


def test_lhb_coverage_failure_plan_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_coverage_and_failure_rule_plan",
        lambda **kwargs: {
            "paths": {
                "coverage_expansion_plan": "/tmp/plan.csv",
                "coverage_expansion_summary": "/tmp/summary.csv",
                "next_commands": "/tmp/commands.sh",
                "failure_rule_audit": "/tmp/audit.csv",
                "failure_rule_suggestions": "/tmp/suggestions.csv",
                "markdown_report": "/tmp/report.md",
            },
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-coverage-failure-plan",
            "--coverage-gap-path",
            "/tmp/gaps.csv",
            "--case-path",
            "/tmp/cases.csv",
            "--snapshot-path",
            "/tmp/snapshot.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_coverage_failure_plan|coverage_expansion_plan|/tmp/plan.csv" in out
    assert "lhb_coverage_failure_plan|report|/tmp/report.md" in out


def test_lhb_after_failure_rule_v21_outputs_suffixed_files(tmp_path):
    curated = _sample_lhb_curated_extended()
    failure_view = pd.DataFrame(
        [
            {"case_id": "c_success", "verified_case_type_v2_1": "second_wave", "old_verified_case_type": "second_wave", "event_date": "2026-05-12", "event_type": "second_wave_start", "label_change_reason": "keep", "confidence": 0.5, "source_origin": "web_seed_verified", "web_source_available": True, "local_event_verified": True, "future_5d_return": 0.12, "future_10d_return": 0.20, "future_10d_max_drawdown": -0.05},
            {"case_id": "c_failed_wave", "verified_case_type_v2_1": "failed_second_wave", "old_verified_case_type": "failed_second_wave", "event_date": "2024-01-24", "event_type": "second_wave_start", "label_change_reason": "keep", "confidence": 0.78, "source_origin": "web_seed_verified", "web_source_available": True, "local_event_verified": True, "future_5d_return": -0.05, "future_10d_return": -0.10, "future_10d_max_drawdown": -0.15},
            {"case_id": "c_a_kill", "verified_case_type_v2_1": "a_kill_failure", "old_verified_case_type": "a_kill_failure", "event_date": "2025-09-18", "event_type": "a_kill_start", "label_change_reason": "keep", "confidence": 0.90, "source_origin": "local_auto_candidate", "web_source_available": False, "local_event_verified": True, "future_5d_return": -0.12, "future_10d_return": -0.20, "future_10d_max_drawdown": -0.25},
        ]
    )
    old_detail = lhb_data.build_lhb_case_difference_report(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
    )["case_event_detail"]
    old_risk = lhb_data.build_lhb_risk_feature_diagnostics(
        curated=_sample_lhb_curated(),
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        output_dir=tmp_path,
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={},
    )["risk_feature_case_detail"]
    old_detail.to_csv(tmp_path / "lhb_case_event_detail.csv", index=False)
    old_risk.to_csv(tmp_path / "lhb_risk_feature_case_detail.csv", index=False)

    result = lhb_data.build_lhb_diagnostics_after_failure_rule_v21(
        curated=curated,
        failure_v21_view=failure_view,
        lhb_features=_sample_lhb_features(),
        alignment_audit=_sample_lhb_alignment(),
        factor_review=_sample_lhb_factor_review(),
        optional_diagnostics={},
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["curated_failure_v21"]).exists()
    assert Path(result["paths"]["case_type_difference_summary"]).name.endswith("_v2_1.csv")
    assert Path(result["paths"]["risk_feature_case_detail"]).name.endswith("_v2_1.csv")
    assert Path(result["paths"]["comparison"]).exists()
    assert "verified_case_type_v2_1" in result["curated_failure_v21"].columns
    assert "metric" in result["comparison"].columns


def test_lhb_after_failure_rule_v21_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_diagnostics_after_failure_rule_v21",
        lambda **kwargs: {
            "paths": {
                "curated_failure_v21": "/tmp/view.csv",
                "transition_matrix": "/tmp/transitions.csv",
                "case_type_difference_summary": "/tmp/case_type_v2_1.csv",
                "risk_feature_case_detail": "/tmp/risk_v2_1.csv",
                "comparison": "/tmp/compare.csv",
                "markdown_report": "/tmp/report.md",
            },
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-risk-diagnostics-after-failure-rule-v2-1",
            "--case-path",
            "/tmp/cases.csv",
            "--failure-audit-path",
            "/tmp/failure_audit.csv",
            "--snapshot-path",
            "/tmp/snapshot.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_after_failure_rule_v2_1|curated_failure_v21|/tmp/view.csv" in out
    assert "lhb_after_failure_rule_v2_1|report|/tmp/report.md" in out


def test_lhb_sample_import_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_sample_import",
        lambda **kwargs: {
            "paths": {"top_list": "/tmp/top_list.csv", "top_inst": "/tmp/top_inst.csv"},
            "top_list": pd.DataFrame([1]),
            "top_inst": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-sample-import",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-13",
            "--ts-codes",
            "600726.SH",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_sample_import|top_list|/tmp/top_list.csv" in out


def test_lhb_sample_import_cli_supports_provider(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_sample_import",
        lambda **kwargs: {
            "paths": {"top_list": "/tmp/top_list.csv", "top_inst": "/tmp/top_inst.csv"},
            "top_list": pd.DataFrame([1]),
            "top_inst": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-sample-import",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-13",
            "--ts-codes",
            "600726.SH",
            "--provider",
            "akshare",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_sample_import|top_list|/tmp/top_list.csv" in out


def test_lhb_alignment_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_dragon_case_lhb_alignment_audit",
        lambda **kwargs: {
            "paths": {"alignment_audit": "/tmp/lhb_audit.csv"},
            "alignment_audit": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "dragon-case-lhb-alignment-audit",
            "--curated-path",
            "/tmp/curated.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "dragon_case_lhb_alignment_audit|alignment_audit|/tmp/lhb_audit.csv" in out


def test_lhb_event_features_build_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_event_features_build",
        lambda **kwargs: {
            "paths": {"lhb_event_features": "/tmp/lhb_event_features.csv"},
            "lhb_event_features": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-build-event-features",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-13",
            "--ts-codes",
            "600726.SH",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_event_features_build|lhb_event_features|/tmp/lhb_event_features.csv" in out


def test_dragon_case_lhb_summary_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_dragon_case_lhb_summary_report",
        lambda **kwargs: {
            "paths": {
                "summary": "/tmp/lhb_summary.csv",
                "comparison": "/tmp/lhb_comparison.csv",
                "markdown_report": "/tmp/lhb_report.md",
            },
            "summary": pd.DataFrame([1]),
            "comparison": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "dragon-case-lhb-summary",
            "--curated-path",
            "/tmp/curated.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "dragon_case_lhb_summary|summary|/tmp/lhb_summary.csv" in out
    assert "dragon_case_lhb_summary|report|/tmp/lhb_report.md" in out


def test_lhb_case_difference_report_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_case_difference_report",
        lambda **kwargs: {
            "paths": {
                "case_type_difference_summary": "/tmp/case_type.csv",
                "event_window_difference": "/tmp/window.csv",
                "risk_signal_effectiveness": "/tmp/risk.csv",
                "positive_signal_effectiveness": "/tmp/positive.csv",
                "case_event_detail": "/tmp/detail.csv",
                "coverage_summary": "/tmp/coverage.csv",
                "markdown_report": "/tmp/report.md",
            },
            "case_type_difference_summary": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-case-difference-report",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_case_difference_report|case_type_difference_summary|/tmp/case_type.csv" in out
    assert "lhb_case_difference_report|report|/tmp/report.md" in out


def test_lhb_risk_feature_diagnostics_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_risk_feature_diagnostics",
        lambda **kwargs: {
            "paths": {
                "risk_feature_case_detail": "/tmp/detail.csv",
                "risk_score_bucket_effectiveness": "/tmp/bucket.csv",
                "risk_failure_type_cross": "/tmp/cross.csv",
                "dragon_risk_cross_diagnostics": "/tmp/dragon.csv",
                "coverage_gap_recommendations": "/tmp/gaps.csv",
                "markdown_report": "/tmp/report.md",
            },
            "risk_feature_case_detail": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-risk-feature-diagnostics",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_risk_feature_diagnostics|risk_feature_case_detail|/tmp/detail.csv" in out
    assert "lhb_risk_feature_diagnostics|report|/tmp/report.md" in out


def test_lhb_follow_exit_replay_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_follow_exit_replay_v1",
        lambda **kwargs: {
            "paths": {
                "replay_detail": "/tmp/replay_detail.csv",
                "replay_effectiveness": "/tmp/replay_effectiveness.csv",
                "markdown_report": "/tmp/replay_report.md",
            },
            "replay_detail": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-follow-exit-replay-v1",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_follow_exit_replay_v1|replay_detail|/tmp/replay_detail.csv" in out
    assert "lhb_follow_exit_replay_v1|report|/tmp/replay_report.md" in out


def test_lhb_shortline_event_replay_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_event_replay_v1",
        lambda **kwargs: {
            "paths": {
                "event_replay": "/tmp/event_replay.csv",
                "markdown_report": "/tmp/event_replay.md",
            },
            "event_replay": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-event-replay-v1",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--market-path",
            "/tmp/market.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_shortline_event_replay_v1|event_replay|/tmp/event_replay.csv" in out
    assert "lhb_shortline_event_replay_v1|report|/tmp/event_replay.md" in out


def test_lhb_follow_avoid_rule_audit_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_follow_avoid_rule_audit_v1",
        lambda **kwargs: {
            "paths": {
                "action_effectiveness": "/tmp/action.csv",
                "rule_matrix": "/tmp/rule.csv",
                "rule_recommendations": "/tmp/recs.csv",
                "markdown_report": "/tmp/report.md",
            },
            "action_effectiveness": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-follow-avoid-rule-audit-v1",
            "--event-replay-path",
            "/tmp/event_replay.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_follow_avoid_rule_audit_v1|action_effectiveness|/tmp/action.csv" in out
    assert "lhb_follow_avoid_rule_audit_v1|report|/tmp/report.md" in out


def test_lhb_exit_rule_audit_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_lhb_exit_rule_audit_v1",
        lambda **kwargs: {
            "paths": {
                "exit_signal_effectiveness": "/tmp/exit_signal.csv",
                "exit_reason_effectiveness": "/tmp/exit_reason.csv",
                "false_positive_audit": "/tmp/false_positive.csv",
                "markdown_report": "/tmp/exit_report.md",
            },
            "exit_signal_effectiveness": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-exit-rule-audit-v1",
            "--event-replay-path",
            "/tmp/event_replay.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "lhb_exit_rule_audit_v1|exit_signal_effectiveness|/tmp/exit_signal.csv" in out
    assert "lhb_exit_rule_audit_v1|report|/tmp/exit_report.md" in out


def test_daily_lhb_shortline_watchlist_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_daily_lhb_shortline_watchlist_v1(**kwargs):
        calls["daily"] = kwargs
        return {
            "paths": {
                "watchlist": "/tmp/daily.csv",
                "markdown_report": "/tmp/daily.md",
            },
            "watchlist": pd.DataFrame([1]),
        }

    monkeypatch.setattr(
        cli,
        "run_daily_lhb_shortline_watchlist_v1",
        fake_run_daily_lhb_shortline_watchlist_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "daily-lhb-shortline-watchlist-v1",
            "--event-replay-path",
            "/tmp/event_replay.csv",
            "--rule-recommendations-path",
            "/tmp/recs.csv",
            "--rule-registry-path",
            "/tmp/rules.csv",
            "--trade-date",
            "2026-05-20",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "rule_registry_path" in calls["daily"]
    assert calls["daily"]["rule_registry_path"] == "/tmp/rules.csv"
    assert "daily_lhb_shortline_watchlist_v1|watchlist|/tmp/daily.csv" in out
    assert "daily_lhb_shortline_watchlist_v1|report|/tmp/daily.md" in out


def test_lhb_shortline_strategy_effectiveness_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_strategy_effectiveness_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "detail": "/tmp/detail.csv",
                "summary": "/tmp/summary.csv",
                "follow_combo_effectiveness": "/tmp/follow.csv",
                "exit_combo_effectiveness": "/tmp/exit.csv",
                "markdown_report": "/tmp/effectiveness.md",
            },
            "detail": pd.DataFrame([1]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_strategy_effectiveness_v1",
        fake_run_lhb_shortline_strategy_effectiveness_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-strategy-effectiveness-v1",
            "--event-replay-path",
            "/tmp/event_replay.csv",
            "--daily-watchlist-path",
            "/tmp/daily.csv",
            "--min-sample-count",
            "3",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "event_replay_path": "/tmp/event_replay.csv",
        "daily_watchlist_path": "/tmp/daily.csv",
        "min_sample_count": 3,
        "output_dir": "/tmp",
    }
    assert "lhb_shortline_strategy_effectiveness_v1|detail|/tmp/detail.csv" in out
    assert "lhb_shortline_strategy_effectiveness_v1|summary|/tmp/summary.csv" in out
    assert "lhb_shortline_strategy_effectiveness_v1|follow_combo|/tmp/follow.csv" in out
    assert "lhb_shortline_strategy_effectiveness_v1|exit_combo|/tmp/exit.csv" in out
    assert "lhb_shortline_strategy_effectiveness_v1|report|/tmp/effectiveness.md" in out


def test_lhb_shortline_rule_calibration_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_rule_calibration_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "rule_registry": "/tmp/rules.csv",
                "markdown_report": "/tmp/rules.md",
            },
            "rule_registry": pd.DataFrame([1]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_rule_calibration_v1",
        fake_run_lhb_shortline_rule_calibration_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-rule-calibration-v1",
            "--follow-combo-path",
            "/tmp/follow.csv",
            "--exit-combo-path",
            "/tmp/exit.csv",
            "--rule-version",
            "lhb_shortline_rules_v1_1",
            "--min-sample-count",
            "10",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "follow_combo_path": "/tmp/follow.csv",
        "exit_combo_path": "/tmp/exit.csv",
        "rule_version": "lhb_shortline_rules_v1_1",
        "min_sample_count": 10,
        "output_dir": "/tmp",
    }
    assert "lhb_shortline_rule_calibration_v1|rule_registry|/tmp/rules.csv" in out
    assert "lhb_shortline_rule_calibration_v1|report|/tmp/rules.md" in out


def test_lhb_shortline_shadow_backtest_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_shadow_backtest_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "summary": "/tmp/shadow_summary.csv",
                "selected_trades": "/tmp/shadow_trades.csv",
                "daily_curve": "/tmp/shadow_curve.csv",
                "markdown_report": "/tmp/shadow.md",
            },
            "summary": pd.DataFrame([{"top_n": 5}]),
            "selected_trades": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "daily_curve": pd.DataFrame([{"trade_date": "2025-01-02"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_shadow_backtest_v1",
        fake_run_lhb_shortline_shadow_backtest_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-shadow-backtest-v1",
            "--event-replay-path",
            "/tmp/event_replay.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-08",
            "--top-n",
            "5,10,20",
            "--pool-mode",
            "support_attention",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "event_replay_path": "/tmp/event_replay.csv",
        "start_date": "2025-01-01",
        "end_date": "2026-06-08",
        "top_n_values": [5, 10, 20],
        "pool_mode": "support_attention",
        "output_dir": "/tmp",
    }
    assert "lhb_shortline_shadow_backtest_v1|summary|/tmp/shadow_summary.csv" in out
    assert "lhb_shortline_shadow_backtest_v1|selected_trades|/tmp/shadow_trades.csv" in out
    assert "lhb_shortline_shadow_backtest_v1|daily_curve|/tmp/shadow_curve.csv" in out
    assert "lhb_shortline_shadow_backtest_v1|report|/tmp/shadow.md" in out


def test_lhb_shortline_intraday_confirmation_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_intraday_confirmation_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "detail": "/tmp/intraday_detail.csv",
                "summary": "/tmp/intraday_summary.csv",
                "markdown_report": "/tmp/intraday.md",
            },
            "detail": pd.DataFrame([{"ts_code": "600726.SH"}]),
            "summary": pd.DataFrame([{"intraday_confirmation_action": "confirm_follow"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_intraday_confirmation_v1",
        fake_run_lhb_shortline_intraday_confirmation_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-intraday-confirmation-v1",
            "--candidate-path",
            "/tmp/lhb_candidates.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--freq",
            "5min",
            "--adjust-type",
            "raw",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "candidate_path": "/tmp/lhb_candidates.csv",
        "minute_bars_path": "/tmp/minute.csv",
        "freq": "5min",
        "adjust_type": "raw",
        "output_dir": "/tmp",
    }
    assert "lhb_shortline_intraday_confirmation_v1|detail|/tmp/intraday_detail.csv" in out
    assert "lhb_shortline_intraday_confirmation_v1|summary|/tmp/intraday_summary.csv" in out
    assert "lhb_shortline_intraday_confirmation_v1|report|/tmp/intraday.md" in out


def test_lhb_phase12a_multi_context_decision_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase12a_multi_context_decision_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "decision": "/tmp/phase12a_decision.csv",
                "summary": "/tmp/phase12a_summary.csv",
                "markdown_report": "/tmp/phase12a.md",
            },
            "decision": pd.DataFrame([{"lhb_phase12a_decision": "follow_pool"}]),
            "summary": pd.DataFrame([{"lhb_phase12a_decision": "follow_pool"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_phase12a_multi_context_decision_v1",
        fake_run_lhb_phase12a_multi_context_decision_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase12a-multi-context-decision-v1",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--intraday-detail-path",
            "/tmp/intraday.csv",
            "--pre-context-days",
            "3",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "selected_trades_path": "/tmp/selected.csv",
        "minute_bars_path": "/tmp/minute.csv",
        "intraday_detail_path": "/tmp/intraday.csv",
        "pre_context_days": 3,
        "output_dir": "/tmp",
    }
    assert "lhb_phase12a_multi_context_decision_v1|decision|/tmp/phase12a_decision.csv" in out
    assert "lhb_phase12a_multi_context_decision_v1|summary|/tmp/phase12a_summary.csv" in out
    assert "lhb_phase12a_multi_context_decision_v1|report|/tmp/phase12a.md" in out


def test_lhb_phase12a_rule_decision_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase12a_rule_decision_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "rule_decision": "/tmp/phase12a_rule_decision.csv",
                "summary": "/tmp/phase12a_rule_summary.csv",
                "markdown_report": "/tmp/phase12a_rule.md",
            },
            "rule_decision": pd.DataFrame([{"phase12a_rule_layer": "follow_pool_core"}]),
            "summary": pd.DataFrame([{"phase12a_rule_layer": "follow_pool_core"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_phase12a_rule_decision_v1",
        fake_run_lhb_phase12a_rule_decision_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase12a-rule-decision-v1",
            "--phase12a-decision-path",
            "/tmp/phase12a_decision.csv",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "phase12a_decision_path": "/tmp/phase12a_decision.csv",
        "output_dir": "/tmp",
    }
    assert "lhb_phase12a_rule_decision_v1|rule_decision|/tmp/phase12a_rule_decision.csv" in out
    assert "lhb_phase12a_rule_decision_v1|summary|/tmp/phase12a_rule_summary.csv" in out
    assert "lhb_phase12a_rule_decision_v1|report|/tmp/phase12a_rule.md" in out


def test_lhb_phase12a_real_entry_backtest_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase12a_real_entry_backtest_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "trades": "/tmp/real_entry_trades.csv",
                "summary": "/tmp/real_entry_summary.csv",
                "markdown_report": "/tmp/real_entry.md",
            },
            "trades": pd.DataFrame([{"fill_status": "filled"}]),
            "summary": pd.DataFrame([{"phase12a_rule_layer": "follow_pool_core"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_phase12a_real_entry_backtest_v1",
        fake_run_lhb_phase12a_real_entry_backtest_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase12a-real-entry-backtest-v1",
            "--rule-decision-path",
            "/tmp/rules.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--daily-bars-path",
            "/tmp/daily.csv",
            "--entry-start-time",
            "10:30:00",
            "--slippage-bps",
            "5",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "rule_decision_path": "/tmp/rules.csv",
        "minute_bars_path": "/tmp/minute.csv",
        "daily_bars_path": "/tmp/daily.csv",
        "entry_start_time": "10:30:00",
        "slippage_bps": 5.0,
        "output_dir": "/tmp",
    }
    assert "lhb_phase12a_real_entry_backtest_v1|trades|/tmp/real_entry_trades.csv" in out
    assert "lhb_phase12a_real_entry_backtest_v1|summary|/tmp/real_entry_summary.csv" in out
    assert "lhb_phase12a_real_entry_backtest_v1|report|/tmp/real_entry.md" in out


def test_lhb_phase12b_signal_exit_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase12b_signal_exit_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "exit_trades": "/tmp/signal_exit_trades.csv",
                "summary": "/tmp/signal_exit_summary.csv",
                "markdown_report": "/tmp/signal_exit.md",
            },
            "exit_trades": pd.DataFrame([{"exit_status": "signal_exit"}]),
            "summary": pd.DataFrame([{"phase12a_rule_layer": "follow_pool_high_confidence"}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase12b_signal_exit_v1", fake_run_lhb_phase12b_signal_exit_v1)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase12b-signal-exit-v1",
            "--entry-trades-path",
            "/tmp/entry.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--max-hold-days",
            "5",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "entry_trades_path": "/tmp/entry.csv",
        "minute_bars_path": "/tmp/minute.csv",
        "max_hold_days": 5,
        "output_dir": "/tmp",
    }
    assert "lhb_phase12b_signal_exit_v1|exit_trades|/tmp/signal_exit_trades.csv" in out
    assert "lhb_phase12b_signal_exit_v1|summary|/tmp/signal_exit_summary.csv" in out
    assert "lhb_phase12b_signal_exit_v1|report|/tmp/signal_exit.md" in out


def test_build_lhb_phase13_two_stage_follow_pool_v1_classifies_observe_follow_and_reject(tmp_path):
    event_features = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "t1_trade_date": "2026-05-13",
                "ts_code": "000001.SZ",
                "stock_name": "RelayStrong",
                "event_family": "limit_relay",
                "prev_limit_up_streak": 3,
                "event_close_position": 0.96,
                "event_high_to_close_drawdown": -0.005,
                "amount_vs_20d": 2.0,
                "lhb_net_amount": 1000.0,
                "post_5d_return": 0.18,
                "post_5d_max_drawdown": -0.03,
            },
            {
                "trade_date": "2026-05-12",
                "t1_trade_date": "2026-05-13",
                "ts_code": "000002.SZ",
                "stock_name": "RelayReject",
                "event_family": "limit_relay",
                "prev_limit_up_streak": 2,
                "event_close_position": 0.92,
                "event_high_to_close_drawdown": -0.01,
                "amount_vs_20d": 1.8,
                "lhb_net_amount": -200.0,
                "post_5d_return": -0.12,
                "post_5d_max_drawdown": -0.18,
            },
            {
                "trade_date": "2026-05-12",
                "t1_trade_date": "2026-05-13",
                "ts_code": "000003.SZ",
                "stock_name": "Other",
                "event_family": "other_lhb",
                "prev_limit_up_streak": 0,
                "event_close_position": 0.90,
                "event_high_to_close_drawdown": -0.01,
                "amount_vs_20d": 2.0,
                "post_5d_return": 0.10,
                "post_5d_max_drawdown": -0.03,
            },
        ]
    )
    t1_features = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "000001.SZ",
                "t1_trade_date": "2026-05-13",
                "t1_midday_return": 0.02,
                "t1_close_vs_vwap": 0.015,
                "t1_final_close_position": 0.88,
                "t1_weak_close_like": False,
                "t1_retreat_proxy": False,
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "000002.SZ",
                "t1_trade_date": "2026-05-13",
                "t1_midday_return": -0.03,
                "t1_close_vs_vwap": -0.02,
                "t1_final_close_position": 0.20,
                "t1_weak_close_like": True,
                "t1_retreat_proxy": True,
            },
        ]
    )

    result = lhb_data.build_lhb_phase13_two_stage_follow_pool_v1(
        event_features=event_features,
        t1_features=t1_features,
        output_dir=tmp_path,
    )

    observe = result["observe_pool"].set_index("ts_code")
    assert list(observe.index) == ["000001.SZ", "000002.SZ"]
    assert observe.loc["000001.SZ", "phase13_observe_signal"] == "observe_pool"
    assert "limit_relay_core" in observe.loc["000001.SZ", "phase13_observe_reason"]

    follow = result["follow_pool"].set_index("ts_code")
    assert list(follow.index) == ["000001.SZ"]
    assert follow.loc["000001.SZ", "phase13_follow_signal"] == "t1_strong_confirm"
    assert "t1_strong_confirmation" in follow.loc["000001.SZ", "phase13_follow_reason"]

    reject = result["reject_pool"].set_index("ts_code")
    assert list(reject.index) == ["000002.SZ"]
    assert reject.loc["000002.SZ", "phase13_reject_signal"] == "t1_retreat_reject"
    assert "t1_retreat_proxy" in reject.loc["000002.SZ", "phase13_reject_reason"]

    summary = result["summary"].set_index("metric")
    assert summary.loc["event_rows", "value"] == 3
    assert summary.loc["observe_pool_rows", "value"] == 2
    assert summary.loc["follow_pool_rows", "value"] == 1
    assert summary.loc["reject_pool_rows", "value"] == 1
    assert Path(result["paths"]["observe_pool"]).exists()
    assert Path(result["paths"]["follow_pool"]).exists()
    assert Path(result["paths"]["reject_pool"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_phase13_two_stage_follow_pool_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase13_two_stage_follow_pool_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "observe_pool": "/tmp/observe.csv",
                "follow_pool": "/tmp/follow.csv",
                "reject_pool": "/tmp/reject.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase13.md",
            },
            "observe_pool": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "follow_pool": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "reject_pool": pd.DataFrame([{"ts_code": "000002.SZ"}]),
            "summary": pd.DataFrame([{"metric": "event_rows", "value": 2}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase13_two_stage_follow_pool_v1", fake_run_lhb_phase13_two_stage_follow_pool_v1)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase13-two-stage-follow-pool-v1",
            "--event-features-path",
            "/tmp/events.csv",
            "--t1-features-path",
            "/tmp/t1.csv",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "event_features_path": "/tmp/events.csv",
        "t1_features_path": "/tmp/t1.csv",
        "output_dir": "/tmp",
    }
    assert "lhb_phase13_two_stage_follow_pool_v1|observe_pool|/tmp/observe.csv" in out
    assert "lhb_phase13_two_stage_follow_pool_v1|follow_pool|/tmp/follow.csv" in out
    assert "lhb_phase13_two_stage_follow_pool_v1|reject_pool|/tmp/reject.csv" in out
    assert "lhb_phase13_two_stage_follow_pool_v1|summary|/tmp/summary.csv" in out
    assert "lhb_phase13_two_stage_follow_pool_v1|report|/tmp/phase13.md" in out


def test_build_lhb_phase13b_topn_filter_v1_scores_daily_topn(tmp_path):
    decision = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-12",
                "ts_code": "000001.SZ",
                "stock_name": "Best",
                "phase13_observe_signal": "observe_pool",
                "phase13_follow_signal": "t1_strong_confirm",
                "phase13_reject_signal": float("nan"),
                "prev_limit_up_streak": 4,
                "event_close_position": 1.0,
                "amount_vs_20d": 4.0,
                "lhb_net_amount": 200000000.0,
                "t1_midday_return": 0.05,
                "t1_close_vs_vwap": 0.03,
                "t1_final_close_position": 1.0,
                "post_5d_return": 0.20,
                "post_5d_max_drawdown": -0.02,
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "000002.SZ",
                "stock_name": "Second",
                "phase13_observe_signal": "observe_pool",
                "phase13_follow_signal": "t1_strong_confirm",
                "phase13_reject_signal": float("nan"),
                "prev_limit_up_streak": 2,
                "event_close_position": 0.90,
                "amount_vs_20d": 1.5,
                "lhb_net_amount": 10000000.0,
                "t1_midday_return": 0.01,
                "t1_close_vs_vwap": 0.005,
                "t1_final_close_position": 0.80,
                "post_5d_return": 0.05,
                "post_5d_max_drawdown": -0.05,
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "000003.SZ",
                "stock_name": "Reject",
                "phase13_observe_signal": "observe_pool",
                "phase13_follow_signal": float("nan"),
                "phase13_reject_signal": "t1_retreat_reject",
                "prev_limit_up_streak": 5,
                "event_close_position": 1.0,
                "amount_vs_20d": 5.0,
                "lhb_net_amount": 300000000.0,
                "t1_midday_return": -0.04,
                "t1_close_vs_vwap": -0.03,
                "t1_final_close_position": 0.1,
                "post_5d_return": -0.20,
                "post_5d_max_drawdown": -0.25,
            },
            {
                "trade_date": "2026-05-13",
                "ts_code": "000004.SZ",
                "stock_name": "NextDay",
                "phase13_observe_signal": "observe_pool",
                "phase13_follow_signal": "t1_strong_confirm",
                "phase13_reject_signal": float("nan"),
                "prev_limit_up_streak": 1,
                "event_close_position": 0.85,
                "amount_vs_20d": 1.2,
                "lhb_net_amount": 0.0,
                "t1_midday_return": 0.0,
                "t1_close_vs_vwap": 0.0,
                "t1_final_close_position": 0.76,
                "post_5d_return": 0.08,
                "post_5d_max_drawdown": -0.04,
            },
        ]
    )

    result = lhb_data.build_lhb_phase13b_topn_filter_v1(
        phase13_decision=decision,
        output_dir=tmp_path,
        top_n_values=[1, 2],
    )

    scored = result["scored"].set_index("ts_code")
    assert scored.loc["000001.SZ", "phase13b_score"] > scored.loc["000002.SZ", "phase13b_score"]
    assert scored.loc["000003.SZ", "phase13b_pool"] == "reject_pool"

    selected = result["selected"]
    top1_follow = selected[(selected["pool_mode"] == "follow_pool") & (selected["top_n"] == 1)]
    assert list(top1_follow["ts_code"]) == ["000001.SZ", "000004.SZ"]
    assert list(top1_follow["phase13b_rank"]) == [1, 1]

    summary = result["summary"].set_index(["pool_mode", "top_n"])
    assert summary.loc[("follow_pool", 1), "selected_count"] == 2
    assert summary.loc[("follow_pool", 1), "signal_day_count"] == 2
    assert summary.loc[("follow_pool", 1), "avg_post_5d_return"] == 0.14
    assert Path(result["paths"]["scored"]).exists()
    assert Path(result["paths"]["selected"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()


def test_lhb_phase13b_topn_filter_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_phase13b_topn_filter_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "scored": "/tmp/scored.csv",
                "selected": "/tmp/selected.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase13b.md",
            },
            "scored": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "selected": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "summary": pd.DataFrame([{"pool_mode": "follow_pool"}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase13b_topn_filter_v1", fake_run_lhb_phase13b_topn_filter_v1)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-phase13b-topn-filter-v1",
            "--phase13-decision-path",
            "/tmp/decision.csv",
            "--top-n",
            "5,10,20",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "phase13_decision_path": "/tmp/decision.csv",
        "top_n": "5,10,20",
        "output_dir": "/tmp",
    }
    assert "lhb_phase13b_topn_filter_v1|scored|/tmp/scored.csv" in out
    assert "lhb_phase13b_topn_filter_v1|selected|/tmp/selected.csv" in out
    assert "lhb_phase13b_topn_filter_v1|summary|/tmp/summary.csv" in out
    assert "lhb_phase13b_topn_filter_v1|report|/tmp/phase13b.md" in out


def test_lhb_phase14_lifecycle_exit_cli(monkeypatch, capsys):
    def fake_run_lhb_phase14_lifecycle_exit_v1(**kwargs):
        assert kwargs == {
            "entry_trades_path": "/tmp/entry.csv",
            "minute_bars_path": "/tmp/minute.csv",
            "max_hold_days": 7,
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "lifecycle_trades": "/tmp/lifecycle.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase14.md",
            },
            "lifecycle_trades": pd.DataFrame([{"exit_status": "signal_exit"}]),
            "summary": pd.DataFrame([{"phase12a_rule_layer": "follow_pool_core"}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase14_lifecycle_exit_v1", fake_run_lhb_phase14_lifecycle_exit_v1)

    cli.main(
        [
            "lhb-phase14-lifecycle-exit-v1",
            "--entry-trades-path",
            "/tmp/entry.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--max-hold-days",
            "7",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase14_lifecycle_exit_v1|lifecycle_trades|/tmp/lifecycle.csv" in out
    assert "lhb_phase14_lifecycle_exit_v1|summary|/tmp/summary.csv" in out
    assert "lhb_phase14_lifecycle_exit_v1|report|/tmp/phase14.md" in out


def test_lhb_phase14b_threshold_scan_cli(monkeypatch, capsys):
    def fake_run_lhb_phase14b_threshold_scan_v1(**kwargs):
        assert kwargs == {
            "entry_trades_path": "/tmp/entry.csv",
            "minute_bars_path": "/tmp/minute.csv",
            "max_hold_days": 7,
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "profile_ranking": "/tmp/ranking.csv",
                "threshold_summary": "/tmp/summary.csv",
                "best_lifecycle_trades": "/tmp/best.csv",
                "markdown_report": "/tmp/phase14b.md",
            },
            "profile_ranking": pd.DataFrame([{"threshold_profile": "sensitive_vwap"}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase14b_threshold_scan_v1", fake_run_lhb_phase14b_threshold_scan_v1)

    cli.main(
        [
            "lhb-phase14b-threshold-scan-v1",
            "--entry-trades-path",
            "/tmp/entry.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--max-hold-days",
            "7",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase14b_threshold_scan_v1|profile_ranking|/tmp/ranking.csv" in out
    assert "lhb_phase14b_threshold_scan_v1|threshold_summary|/tmp/summary.csv" in out
    assert "lhb_phase14b_threshold_scan_v1|best_lifecycle_trades|/tmp/best.csv" in out
    assert "lhb_phase14b_threshold_scan_v1|report|/tmp/phase14b.md" in out


def test_lhb_phase14c_lifecycle_portfolio_cli(monkeypatch, capsys):
    def fake_run_lhb_phase14c_lifecycle_portfolio_v1(**kwargs):
        assert kwargs == {
            "entry_trades_path": "/tmp/entry.csv",
            "minute_bars_path": "/tmp/minute.csv",
            "max_hold_days": 7,
            "threshold_profile": "sensitive_entry_buffer",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "lifecycle_trades": "/tmp/trades.csv",
                "daily_curve": "/tmp/curve.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase14c.md",
            },
            "summary": pd.DataFrame([{"top_n": 5}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase14c_lifecycle_portfolio_v1", fake_run_lhb_phase14c_lifecycle_portfolio_v1)

    cli.main(
        [
            "lhb-phase14c-lifecycle-portfolio-v1",
            "--entry-trades-path",
            "/tmp/entry.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--max-hold-days",
            "7",
            "--threshold-profile",
            "sensitive_entry_buffer",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase14c_lifecycle_portfolio_v1|lifecycle_trades|/tmp/trades.csv" in out
    assert "lhb_phase14c_lifecycle_portfolio_v1|daily_curve|/tmp/curve.csv" in out
    assert "lhb_phase14c_lifecycle_portfolio_v1|summary|/tmp/summary.csv" in out
    assert "lhb_phase14c_lifecycle_portfolio_v1|report|/tmp/phase14c.md" in out


def test_lhb_phase14e_limit_lock_filter_cli(monkeypatch, capsys):
    def fake_run_lhb_phase14e_limit_lock_filter_v1(**kwargs):
        assert kwargs == {
            "entry_trades_path": "/tmp/entry.csv",
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "risk_audit": "/tmp/audit.csv",
                "filter_ranking": "/tmp/ranking.csv",
                "best_trades": "/tmp/best.csv",
                "best_curve": "/tmp/curve.csv",
                "best_summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase14e.md",
            },
            "filter_ranking": pd.DataFrame([{"filter_profile": "baseline"}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase14e_limit_lock_filter_v1", fake_run_lhb_phase14e_limit_lock_filter_v1)

    cli.main(
        [
            "lhb-phase14e-limit-lock-filter-v1",
            "--entry-trades-path",
            "/tmp/entry.csv",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase14e_limit_lock_filter_v1|risk_audit|/tmp/audit.csv" in out
    assert "lhb_phase14e_limit_lock_filter_v1|filter_ranking|/tmp/ranking.csv" in out
    assert "lhb_phase14e_limit_lock_filter_v1|best_trades|/tmp/best.csv" in out
    assert "lhb_phase14e_limit_lock_filter_v1|best_curve|/tmp/curve.csv" in out
    assert "lhb_phase14e_limit_lock_filter_v1|best_summary|/tmp/summary.csv" in out
    assert "lhb_phase14e_limit_lock_filter_v1|report|/tmp/phase14e.md" in out


def test_lhb_phase15_cash_account_backtest_cli(monkeypatch, capsys):
    def fake_run_lhb_phase15_cash_account_backtest_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "max_positions": 10,
            "position_pct": 0.1,
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "account_trades": "/tmp/trades.csv",
                "account_curve": "/tmp/curve.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase15.md",
            },
            "summary": pd.DataFrame([{"final_equity": 1.2}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase15_cash_account_backtest_v1", fake_run_lhb_phase15_cash_account_backtest_v1)

    cli.main(
        [
            "lhb-phase15-cash-account-backtest-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--max-positions",
            "10",
            "--position-pct",
            "0.1",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase15_cash_account_backtest_v1|account_trades|/tmp/trades.csv" in out
    assert "lhb_phase15_cash_account_backtest_v1|account_curve|/tmp/curve.csv" in out
    assert "lhb_phase15_cash_account_backtest_v1|summary|/tmp/summary.csv" in out
    assert "lhb_phase15_cash_account_backtest_v1|report|/tmp/phase15.md" in out


def test_lhb_phase15_cash_account_backtest_blocks_stale_input_when_cutoff_enabled(tmp_path):
    lifecycle_path = tmp_path / "lhb_phase14e_best_trades_v1.csv"
    lifecycle_path.write_text(
        "\n".join(
            [
                "filter_profile,trade_date,ts_code,top_n,phase12a_rule_layer,fill_status,entry_trade_date,entry_price,exit_trade_date,exit_price,realized_return",
                "exclude_blocked_exit_history,2026-06-05,300001.SZ,10,follow_pool_core,filled,2026-06-08,10,2026-06-09,11,0.10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        lhb_data.run_lhb_phase15_cash_account_backtest_v1(
            lifecycle_trades_path=lifecycle_path,
            max_positions=10,
            position_pct=0.1,
            output_dir=tmp_path / "out",
            cutoff_start_date="2025-01-01",
            cutoff_end_date="2026-06-12",
            strict_cutoff_audit=True,
        )
    except ValueError as exc:
        assert "lhb_phase15_cutoff_audit_failed" in str(exc)
    else:
        raise AssertionError("Expected stale LHB input to fail strict cutoff audit")

    audit_path = tmp_path / "out" / "cutoff_audit" / "lhb_cutoff_audit_v1.csv"
    assert audit_path.exists()
    audit = pd.read_csv(audit_path)
    assert set(audit["issue_code"]) >= {
        "date_coverage_shortfall",
        "phase14e_best_profile_in_sample_selection",
    }


def test_lhb_phase15_cash_account_backtest_cli_accepts_cutoff_audit_args(monkeypatch, capsys):
    def fake_run_lhb_phase15_cash_account_backtest_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "max_positions": 10,
            "position_pct": 0.1,
            "output_dir": "/tmp/out",
            "cutoff_start_date": "2025-01-01",
            "cutoff_end_date": "2026-06-12",
            "strict_cutoff_audit": True,
            "allow_phase14e_best": False,
        }
        return {
            "paths": {
                "account_trades": "/tmp/trades.csv",
                "account_curve": "/tmp/curve.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase15.md",
            },
            "summary": pd.DataFrame([{"final_equity": 1.2}]),
        }

    monkeypatch.setattr(cli, "run_lhb_phase15_cash_account_backtest_v1", fake_run_lhb_phase15_cash_account_backtest_v1)

    cli.main(
        [
            "lhb-phase15-cash-account-backtest-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--max-positions",
            "10",
            "--position-pct",
            "0.1",
            "--cutoff-start-date",
            "2025-01-01",
            "--cutoff-end-date",
            "2026-06-12",
            "--strict-cutoff-audit",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase15_cash_account_backtest_v1|summary|/tmp/summary.csv" in out


def test_lhb_cutoff_audit_flags_stale_phase14e_best_profile(tmp_path):
    trades_path = tmp_path / "lhb_phase14e_best_trades_v1.csv"
    trades_path.write_text(
        "\n".join(
            [
                "filter_profile,trade_date,ts_code,fill_status,entry_trade_date,exit_trade_date,realized_return",
                "exclude_blocked_exit_history,2025-01-02,300001.SZ,filled,2025-01-03,2025-01-06,0.05",
                "exclude_blocked_exit_history,2026-06-05,300002.SZ,filled,2026-06-08,2026-06-09,0.02",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = lhb_data.build_lhb_cutoff_audit_v1(
        paths=[trades_path],
        start_date="2025-01-01",
        end_date="2026-06-12",
        strict=True,
        forbid_phase14e_best=True,
        output_dir=tmp_path / "audit",
    )

    assert result["status"] == "fail"
    audit = result["audit"]
    assert set(audit["issue_code"]) >= {
        "date_coverage_shortfall",
        "phase14e_best_profile_in_sample_selection",
    }
    assert audit.loc[audit["issue_code"].eq("date_coverage_shortfall"), "actual_max_date"].iloc[0] == "2026-06-09"
    assert result["paths"]["audit"].endswith("lhb_cutoff_audit_v1.csv")


def test_lhb_cutoff_audit_cli(monkeypatch, capsys):
    def fake_run_lhb_cutoff_audit_v1(**kwargs):
        assert kwargs == {
            "paths": ["/tmp/trades.csv"],
            "start_date": "2025-01-01",
            "end_date": "2026-06-12",
            "output_dir": "/tmp/out",
            "strict": True,
            "forbid_phase14e_best": True,
        }
        return {
            "status": "fail",
            "audit": pd.DataFrame([{"issue_code": "date_coverage_shortfall"}]),
            "paths": {
                "audit": "/tmp/out/lhb_cutoff_audit_v1.csv",
                "summary": "/tmp/out/lhb_cutoff_audit_summary_v1.csv",
                "markdown_report": "/tmp/out/lhb_cutoff_audit_v1.md",
            },
        }

    monkeypatch.setattr(cli, "run_lhb_cutoff_audit_v1", fake_run_lhb_cutoff_audit_v1)

    cli.main(
        [
            "lhb-cutoff-audit-v1",
            "--path",
            "/tmp/trades.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-12",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_cutoff_audit_v1|status|fail" in out
    assert "lhb_cutoff_audit_v1|audit|/tmp/out/lhb_cutoff_audit_v1.csv" in out
    assert "lhb_cutoff_audit_v1|summary|/tmp/out/lhb_cutoff_audit_summary_v1.csv" in out
    assert "lhb_cutoff_audit_v1|report|/tmp/out/lhb_cutoff_audit_v1.md" in out


def test_lhb_phase16_quality_improvement_diagnostics_cli(monkeypatch, capsys):
    def fake_run_lhb_phase16_quality_improvement_diagnostics_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "real_entry_trades_path": "/tmp/real_entry.csv",
            "selected_trades_path": "/tmp/selected.csv",
            "min_group_count": 5,
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "low_quality_buy_diagnostics": "/tmp/low_quality.csv",
                "exit_mistake_diagnostics": "/tmp/exits.csv",
                "filter_scan": "/tmp/filter.csv",
                "markdown_report": "/tmp/phase16.md",
            }
        }

    monkeypatch.setattr(cli, "run_lhb_phase16_quality_improvement_diagnostics_v1", fake_run_lhb_phase16_quality_improvement_diagnostics_v1)

    cli.main(
        [
            "lhb-phase16-quality-improvement-diagnostics-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--real-entry-trades-path",
            "/tmp/real_entry.csv",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--min-group-count",
            "5",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase16_quality_improvement_diagnostics_v1|low_quality_buy_diagnostics|/tmp/low_quality.csv" in out
    assert "lhb_phase16_quality_improvement_diagnostics_v1|exit_mistake_diagnostics|/tmp/exits.csv" in out
    assert "lhb_phase16_quality_improvement_diagnostics_v1|filter_scan|/tmp/filter.csv" in out
    assert "lhb_phase16_quality_improvement_diagnostics_v1|report|/tmp/phase16.md" in out


def test_lhb_phase16b_limit_break_failed_exit_replay_cli(monkeypatch, capsys):
    def fake_run_lhb_phase16b_limit_break_failed_exit_replay_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "real_entry_trades_path": "/tmp/real_entry.csv",
            "selected_trades_path": "/tmp/selected.csv",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "opportunity_trades": "/tmp/opps.csv",
                "strategy_summary": "/tmp/strategy.csv",
                "candidate_summary": "/tmp/candidate.csv",
                "markdown_report": "/tmp/phase16b.md",
            }
        }

    monkeypatch.setattr(cli, "run_lhb_phase16b_limit_break_failed_exit_replay_v1", fake_run_lhb_phase16b_limit_break_failed_exit_replay_v1)

    cli.main(
        [
            "lhb-phase16b-limit-break-failed-exit-replay-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--real-entry-trades-path",
            "/tmp/real_entry.csv",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase16b_limit_break_failed_exit_replay_v1|opportunity_trades|/tmp/opps.csv" in out
    assert "lhb_phase16b_limit_break_failed_exit_replay_v1|strategy_summary|/tmp/strategy.csv" in out
    assert "lhb_phase16b_limit_break_failed_exit_replay_v1|candidate_summary|/tmp/candidate.csv" in out
    assert "lhb_phase16b_limit_break_failed_exit_replay_v1|report|/tmp/phase16b.md" in out


def test_lhb_phase16c_limit_break_failed_rule_scan_cli(monkeypatch, capsys):
    def fake_run_lhb_phase16c_limit_break_failed_rule_scan_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "real_entry_trades_path": "/tmp/real_entry.csv",
            "selected_trades_path": "/tmp/selected.csv",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "adjusted_trades": "/tmp/adjusted.csv",
                "rule_scan_summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase16c.md",
            }
        }

    monkeypatch.setattr(cli, "run_lhb_phase16c_limit_break_failed_rule_scan_v1", fake_run_lhb_phase16c_limit_break_failed_rule_scan_v1)

    cli.main(
        [
            "lhb-phase16c-limit-break-failed-rule-scan-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--real-entry-trades-path",
            "/tmp/real_entry.csv",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase16c_limit_break_failed_rule_scan_v1|adjusted_trades|/tmp/adjusted.csv" in out
    assert "lhb_phase16c_limit_break_failed_rule_scan_v1|rule_scan_summary|/tmp/summary.csv" in out
    assert "lhb_phase16c_limit_break_failed_rule_scan_v1|report|/tmp/phase16c.md" in out


def test_lhb_phase16d_limit_break_failed_indicator_discovery_cli(monkeypatch, capsys):
    def fake_run_lhb_phase16d_limit_break_failed_indicator_discovery_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "real_entry_trades_path": "/tmp/real_entry.csv",
            "selected_trades_path": "/tmp/selected.csv",
            "minute_bars_path": "/tmp/minute.csv",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "indicator_detail": "/tmp/detail.csv",
                "indicator_summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase16d.md",
            }
        }

    monkeypatch.setattr(cli, "run_lhb_phase16d_limit_break_failed_indicator_discovery_v1", fake_run_lhb_phase16d_limit_break_failed_indicator_discovery_v1)

    cli.main(
        [
            "lhb-phase16d-limit-break-failed-indicator-discovery-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--real-entry-trades-path",
            "/tmp/real_entry.csv",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase16d_limit_break_failed_indicator_discovery_v1|indicator_detail|/tmp/detail.csv" in out
    assert "lhb_phase16d_limit_break_failed_indicator_discovery_v1|indicator_summary|/tmp/summary.csv" in out
    assert "lhb_phase16d_limit_break_failed_indicator_discovery_v1|report|/tmp/phase16d.md" in out


def test_lhb_phase16e_limit_break_failed_indicator_rule_scan_cli(monkeypatch, capsys):
    def fake_run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(**kwargs):
        assert kwargs == {
            "lifecycle_trades_path": "/tmp/lifecycle.csv",
            "real_entry_trades_path": "/tmp/real_entry.csv",
            "selected_trades_path": "/tmp/selected.csv",
            "minute_bars_path": "/tmp/minute.csv",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "adjusted_trades": "/tmp/adjusted.csv",
                "rule_scan_summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/phase16e.md",
            }
        }

    monkeypatch.setattr(cli, "run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1", fake_run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1)

    cli.main(
        [
            "lhb-phase16e-limit-break-failed-indicator-rule-scan-v1",
            "--lifecycle-trades-path",
            "/tmp/lifecycle.csv",
            "--real-entry-trades-path",
            "/tmp/real_entry.csv",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--minute-bars-path",
            "/tmp/minute.csv",
            "--output-dir",
            "/tmp/out",
        ]
    )

    out = capsys.readouterr().out
    assert "lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|adjusted_trades|/tmp/adjusted.csv" in out
    assert "lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|rule_scan_summary|/tmp/summary.csv" in out
    assert "lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|report|/tmp/phase16e.md" in out


def test_lhb_full_market_pool_backtest_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_full_market_pool_backtest_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "summary": "/tmp/full_summary.csv",
                "selected_trades": "/tmp/full_selected.csv",
                "daily_curve": "/tmp/full_curve.csv",
                "markdown_report": "/tmp/full.md",
            },
            "summary": pd.DataFrame([{"top_n": 5}]),
            "selected_trades": pd.DataFrame([{"ts_code": "000001.SZ"}]),
            "daily_curve": pd.DataFrame([{"trade_date": "2026-01-02"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_full_market_pool_backtest_v1",
        fake_run_lhb_full_market_pool_backtest_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-full-market-pool-backtest-v1",
            "--lhb-features-path",
            "/tmp/lhb.csv",
            "--daily-bars-path",
            "/tmp/bars.csv",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-06-08",
            "--top-n",
            "5,10,20",
            "--pool-mode",
            "raw_lhb_positive",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "lhb_features_path": "/tmp/lhb.csv",
        "daily_bars_path": "/tmp/bars.csv",
        "start_date": "2026-01-01",
        "end_date": "2026-06-08",
        "top_n_values": [5, 10, 20],
        "pool_mode": "raw_lhb_positive",
        "output_dir": "/tmp",
    }
    assert "lhb_full_market_pool_backtest_v1|summary|/tmp/full_summary.csv" in out
    assert "lhb_full_market_pool_backtest_v1|selected_trades|/tmp/full_selected.csv" in out
    assert "lhb_full_market_pool_backtest_v1|daily_curve|/tmp/full_curve.csv" in out
    assert "lhb_full_market_pool_backtest_v1|report|/tmp/full.md" in out


def test_lhb_intraday_filtered_topn_comparison_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_intraday_filtered_topn_comparison_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "comparison": "/tmp/comparison.csv",
                "action_effectiveness": "/tmp/action.csv",
                "markdown_report": "/tmp/comparison.md",
            },
            "comparison": pd.DataFrame([{"candidate_set": "raw_topn"}]),
            "action_effectiveness": pd.DataFrame([{"intraday_confirmation_action": "confirm_follow"}]),
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_intraday_filtered_topn_comparison_v1",
        fake_run_lhb_intraday_filtered_topn_comparison_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-intraday-filtered-topn-comparison-v1",
            "--selected-trades-path",
            "/tmp/selected.csv",
            "--intraday-detail-path",
            "/tmp/intraday.csv",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "selected_trades_path": "/tmp/selected.csv",
        "intraday_detail_path": "/tmp/intraday.csv",
        "output_dir": "/tmp",
    }
    assert "lhb_intraday_filtered_topn_comparison_v1|comparison|/tmp/comparison.csv" in out
    assert "lhb_intraday_filtered_topn_comparison_v1|action_effectiveness|/tmp/action.csv" in out
    assert "lhb_intraday_filtered_topn_comparison_v1|report|/tmp/comparison.md" in out


def test_lhb_shortline_daily_pipeline_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_daily_pipeline_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "event_replay": "/tmp/event_replay.csv",
                "daily_watchlist": "/tmp/daily.csv",
                "rule_registry": "/tmp/rules.csv",
                "effectiveness_report": "/tmp/effectiveness.md",
                "run_summary": "/tmp/summary.json",
            },
            "summary": {"daily_watchlist_rows": 8},
        }

    monkeypatch.setattr(
        cli,
        "run_lhb_shortline_daily_pipeline_v1",
        fake_run_lhb_shortline_daily_pipeline_v1,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-lhb-shortline-daily-v1",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--trade-date",
            "2026-05-13",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "case_path": "/tmp/cases.csv",
        "lhb_features_path": "/tmp/features.csv",
        "alignment_path": "/tmp/alignment.csv",
        "trade_date": "2026-05-13",
        "output_dir": "/tmp",
        "market_path": None,
        "min_sample_count": 10,
        "rule_version": "lhb_shortline_rules_v1_1",
    }
    assert "lhb_shortline_daily_v1|event_replay|/tmp/event_replay.csv" in out
    assert "lhb_shortline_daily_v1|daily_watchlist|/tmp/daily.csv" in out
    assert "lhb_shortline_daily_v1|run_summary|/tmp/summary.json" in out


def test_lhb_shortline_daily_pipeline_cli_can_build_watchlist_diagnostics(monkeypatch, capsys, tmp_path):
    calls = {}
    summary_path = tmp_path / "summary.json"
    summary_path.write_text('{"summary": {}, "paths": {}}', encoding="utf-8")

    def fake_run_lhb_shortline_daily_pipeline_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "event_replay": "/tmp/event_replay.csv",
                "daily_watchlist": "/tmp/daily.csv",
                "rule_registry": "/tmp/rules.csv",
                "effectiveness_report": "/tmp/effectiveness.md",
                "run_summary": str(summary_path),
            },
            "summary": {"daily_watchlist_rows": 8},
        }

    def fake_build_watchlist_diagnostics_snapshot(**kwargs):
        calls["diagnostics"] = kwargs
        return {
            "full": pd.DataFrame([{"asset_id": "A"}]),
            "must_watch": pd.DataFrame([{"asset_id": "A"}]),
        }

    def fake_write_watchlist_diagnostics_report(**kwargs):
        calls["report"] = kwargs
        return {
            "full_csv_path": "/tmp/full.csv",
            "must_watch_csv_path": "/tmp/must.csv",
            "markdown_path": "/tmp/watchlist.md",
        }

    def fake_store_watchlist_diagnostics_signals(frame):
        calls["store"] = frame.copy()
        return len(frame)

    monkeypatch.setattr(cli, "run_lhb_shortline_daily_pipeline_v1", fake_run_lhb_shortline_daily_pipeline_v1)
    monkeypatch.setattr(cli, "build_watchlist_diagnostics_snapshot", fake_build_watchlist_diagnostics_snapshot)
    monkeypatch.setattr(cli, "write_watchlist_diagnostics_report", fake_write_watchlist_diagnostics_report)
    monkeypatch.setattr(cli, "_store_watchlist_diagnostics_signals", fake_store_watchlist_diagnostics_signals)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-lhb-shortline-daily-v1",
            "--case-path",
            "/tmp/cases.csv",
            "--lhb-features-path",
            "/tmp/features.csv",
            "--alignment-path",
            "/tmp/alignment.csv",
            "--trade-date",
            "2026-05-13",
            "--output-dir",
            "/tmp",
            "--build-watchlist-diagnostics",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["diagnostics"]["trade_date"] == "2026-05-13"
    assert calls["diagnostics"]["lhb_shortline_path"] == "/tmp/daily.csv"
    assert calls["report"]["full_rows"].equals(pd.DataFrame([{"asset_id": "A"}]))
    assert len(calls["store"]) == 1
    assert "lhb_shortline_daily_v1|watchlist_diagnostics|/tmp/full.csv" in out
    assert "lhb_shortline_daily_v1|watchlist_diagnostics_must_watch|/tmp/must.csv" in out
    assert "lhb_shortline_daily_v1|watchlist_diagnostics_markdown|/tmp/watchlist.md" in out
    assert "lhb_shortline_daily_v1|watchlist_diagnostics_stored|1" in out


def test_lhb_shortline_manual_review_cli(monkeypatch, capsys):
    calls = {}

    def fake_run_lhb_shortline_manual_review_v1(**kwargs):
        calls["run"] = kwargs
        return {
            "paths": {
                "manual_review": "/tmp/manual.csv",
                "summary": "/tmp/summary.csv",
                "markdown_report": "/tmp/manual.md",
            },
            "manual_review": pd.DataFrame([1]),
            "summary": pd.DataFrame([1]),
        }

    monkeypatch.setattr(cli, "run_lhb_shortline_manual_review_v1", fake_run_lhb_shortline_manual_review_v1)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "lhb-shortline-manual-review-v1",
            "--daily-watchlist-path",
            "/tmp/daily.csv",
            "--effectiveness-detail-path",
            "/tmp/detail.csv",
            "--manual-review-path",
            "/tmp/manual_input.csv",
            "--trade-date",
            "2026-05-13",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls["run"] == {
        "daily_watchlist_path": "/tmp/daily.csv",
        "effectiveness_detail_path": "/tmp/detail.csv",
        "manual_review_path": "/tmp/manual_input.csv",
        "trade_date": "2026-05-13",
        "output_dir": "/tmp",
    }
    assert "lhb_shortline_manual_review_v1|manual_review|/tmp/manual.csv" in out
    assert "lhb_shortline_manual_review_v1|summary|/tmp/summary.csv" in out
    assert "lhb_shortline_manual_review_v1|report|/tmp/manual.md" in out


def test_fetch_lhb_sample_supports_akshare_provider(monkeypatch):
    class FakeAk:
        @staticmethod
        def stock_lhb_detail_em(start_date: str, end_date: str):
            return pd.DataFrame(
                [
                    {
                        "代码": "600726",
                        "名称": "华电能源",
                        "上榜日": "2026-05-12",
                        "收盘价": 10.5,
                        "涨跌幅": 9.98,
                        "龙虎榜净买额": 200.0,
                        "龙虎榜买入额": 1200.0,
                        "龙虎榜卖出额": 1000.0,
                        "龙虎榜成交额": 2200.0,
                        "市场总成交额": 5000.0,
                        "净买额占总成交比": 0.04,
                        "成交额占总成交比": 0.44,
                        "换手率": 12.3,
                        "流通市值": 1000000.0,
                        "上榜原因": "日涨幅偏离值达7%",
                    }
                ]
            )

        @staticmethod
        def stock_lhb_jgmmtj_em(start_date: str, end_date: str):
            return pd.DataFrame(
                [
                    {
                        "代码": "600726",
                        "名称": "华电能源",
                        "上榜日期": "2026-05-12",
                        "机构买入总额": 500.0,
                        "机构卖出总额": 100.0,
                        "机构买入净额": 400.0,
                        "上榜原因": "日涨幅偏离值达7%",
                    }
                ]
            )

    monkeypatch.setattr(lhb_data, "build_akshare_client", lambda: FakeAk())
    top_list, top_inst = lhb_data.fetch_lhb_sample(
        start_date="2026-05-01",
        end_date="2026-05-13",
        ts_codes=["600726.SH"],
        provider="akshare",
    )

    assert len(top_list) == 1
    assert top_list.iloc[0]["ts_code"] == "600726.SH"
    assert top_list.iloc[0]["source"] == "akshare"
    assert len(top_inst) == 1
    assert top_inst.iloc[0]["exalter"] == "机构汇总"


def _sample_lhb_curated() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c_success",
                "ts_code": "600726.SH",
                "stock_name": "SuccessWave",
                "case_year": 2026,
                "case_type": "second_wave",
                "verified_case_type": "second_wave",
                "success_or_failure": "success",
                "role": "theme_leader",
            },
            {
                "case_id": "c_failed_wave",
                "ts_code": "000017.SZ",
                "stock_name": "FailedWave",
                "case_year": 2024,
                "case_type": "failed_second_wave",
                "verified_case_type": "failed_second_wave",
                "success_or_failure": "failure",
                "role": "failed_leader",
            },
            {
                "case_id": "c_a_kill",
                "ts_code": "000002.SZ",
                "stock_name": "AKill",
                "case_year": 2025,
                "case_type": "a_kill_failure",
                "verified_case_type": "a_kill_failure",
                "success_or_failure": "failure",
                "role": "failed_leader",
            },
        ]
    )


def _sample_lhb_curated_extended() -> pd.DataFrame:
    base = _sample_lhb_curated()
    extra = pd.DataFrame(
        [
            {
                "case_id": "c_failed_reversal",
                "ts_code": "000003.SZ",
                "stock_name": "FailedReversal",
                "case_year": 2025,
                "case_type": "failed_reversal",
                "verified_case_type": "failed_reversal",
                "success_or_failure": "failure",
                "role": "failed_leader",
            },
            {
                "case_id": "c_hocl",
                "ts_code": "000004.SZ",
                "stock_name": "HOCL",
                "case_year": 2026,
                "case_type": "high_open_low_close_failure",
                "verified_case_type": "high_open_low_close_failure",
                "success_or_failure": "failure",
                "role": "failed_leader",
            },
            {
                "case_id": "c_pump",
                "ts_code": "000005.SZ",
                "stock_name": "Pump",
                "case_year": 2026,
                "case_type": "one_day_pump",
                "verified_case_type": "one_day_pump",
                "success_or_failure": "failure",
                "role": "follower",
            },
        ]
    )
    return pd.concat([base, extra], ignore_index=True)


def _sample_lhb_coverage_gaps() -> pd.DataFrame:
    rows = []
    for case in _sample_lhb_curated_extended().to_dict("records"):
        rows.append(
            {
                "case_id": case["case_id"],
                "ts_code": case["ts_code"],
                "stock_name": case["stock_name"],
                "case_year": case["case_year"],
                "verified_case_type": case["verified_case_type"],
                "success_or_failure": case["success_or_failure"],
                "event_date": {
                    "c_success": "2026-05-12",
                    "c_failed_wave": "2024-01-24",
                    "c_a_kill": "2025-09-18",
                    "c_failed_reversal": "2025-11-18",
                    "c_hocl": "2026-05-08",
                    "c_pump": "2026-05-09",
                }[case["case_id"]],
                "has_lhb": False,
                "missing_reason": "no_lhb_within_event_window",
                "priority_for_lhb_backfill": 9,
                "suggested_lhb_query_start_date": "2026-05-01",
                "suggested_lhb_query_end_date": "2026-05-13",
                "notes": "gap",
            }
        )
    return pd.DataFrame(rows)


def _sample_case_factor_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c_failed_reversal",
                "ts_code": "000003.SZ",
                "stock_name": "FailedReversal",
                "event_type": "reversal",
                "event_date": "2025-11-18",
                "relative_day": 0,
                "trade_date": "2025-11-18",
                "pre_3d_return": 0.08,
                "pre_5d_return": 0.18,
                "amount_vs_20d": 2.4,
                "high_to_close_drawdown": 0.06,
                "close_position_in_day": 0.30,
                "is_limit_up_day": True,
                "is_break_limit_event": False,
                "is_reversal_event": True,
                "is_second_wave_event": False,
                "is_a_kill_event": False,
                "future_1d_return": -0.03,
                "future_3d_return": -0.08,
                "future_5d_return": -0.12,
                "future_10d_return": -0.18,
                "future_5d_max_drawdown": -0.15,
                "future_10d_max_drawdown": -0.22,
            },
            {
                "case_id": "c_hocl",
                "ts_code": "000004.SZ",
                "stock_name": "HOCL",
                "event_type": "peak",
                "event_date": "2026-05-08",
                "relative_day": 0,
                "trade_date": "2026-05-08",
                "pre_3d_return": 0.10,
                "pre_5d_return": 0.28,
                "amount_vs_20d": 3.2,
                "high_to_close_drawdown": 0.12,
                "close_position_in_day": 0.15,
                "is_limit_up_day": False,
                "is_break_limit_event": True,
                "is_reversal_event": False,
                "is_second_wave_event": False,
                "is_a_kill_event": False,
                "future_1d_return": -0.04,
                "future_3d_return": -0.09,
                "future_5d_return": -0.14,
                "future_10d_return": -0.16,
                "future_5d_max_drawdown": -0.16,
                "future_10d_max_drawdown": -0.20,
            },
            {
                "case_id": "c_pump",
                "ts_code": "000005.SZ",
                "stock_name": "Pump",
                "event_type": "first_limit_up",
                "event_date": "2026-05-09",
                "relative_day": 0,
                "trade_date": "2026-05-09",
                "pre_3d_return": 0.02,
                "pre_5d_return": 0.04,
                "amount_vs_20d": 4.0,
                "high_to_close_drawdown": 0.08,
                "close_position_in_day": 0.25,
                "is_limit_up_day": True,
                "is_break_limit_event": False,
                "is_reversal_event": False,
                "is_second_wave_event": False,
                "is_a_kill_event": False,
                "limit_up_count_before_event": 0,
                "future_1d_return": -0.05,
                "future_3d_return": -0.10,
                "future_5d_return": -0.11,
                "future_10d_return": -0.09,
                "future_5d_max_drawdown": -0.12,
                "future_10d_max_drawdown": -0.13,
            },
            {
                "case_id": "c_failed_wave",
                "ts_code": "000017.SZ",
                "stock_name": "FailedWave",
                "event_type": "second_wave_start",
                "event_date": "2024-01-24",
                "relative_day": 0,
                "trade_date": "2024-01-24",
                "pre_3d_return": 0.16,
                "pre_5d_return": 0.30,
                "amount_vs_20d": 2.0,
                "high_to_close_drawdown": 0.07,
                "close_position_in_day": 0.45,
                "is_limit_up_day": False,
                "is_break_limit_event": True,
                "is_reversal_event": False,
                "is_second_wave_event": True,
                "is_a_kill_event": False,
                "future_1d_return": -0.02,
                "future_3d_return": -0.03,
                "future_5d_return": -0.09,
                "future_10d_return": -0.14,
                "future_5d_max_drawdown": -0.12,
                "future_10d_max_drawdown": -0.18,
            },
            {
                "case_id": "c_a_kill",
                "ts_code": "000002.SZ",
                "stock_name": "AKill",
                "event_type": "a_kill_start",
                "event_date": "2025-09-18",
                "relative_day": 0,
                "trade_date": "2025-09-18",
                "pre_3d_return": 0.20,
                "pre_5d_return": 0.42,
                "amount_vs_20d": 2.8,
                "high_to_close_drawdown": 0.10,
                "close_position_in_day": 0.20,
                "is_limit_up_day": False,
                "is_break_limit_event": True,
                "is_reversal_event": False,
                "is_second_wave_event": False,
                "is_a_kill_event": True,
                "future_1d_return": -0.06,
                "future_3d_return": -0.12,
                "future_5d_return": -0.18,
                "future_10d_return": -0.25,
                "future_5d_max_drawdown": -0.20,
                "future_10d_max_drawdown": -0.30,
            },
        ]
    )


def _sample_lhb_alignment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c_success",
                "ts_code": "600726.SH",
                "stock_name": "SuccessWave",
                "case_type": "second_wave",
                "event_type": "second_wave_start",
                "event_date": "2026-05-12",
                "lhb_on_event_date": True,
                "lhb_before_event_3d": True,
                "lhb_after_event_3d": False,
                "lhb_reason": "日涨幅偏离值达7%",
                "lhb_net_buy_amount": 500.0,
                "institution_net_buy": 300.0,
                "top_seat_concentration": 0.2,
                "repeat_on_list_count_3d": 2,
                "repeat_on_list_count_5d": 3,
                "lhb_one_day_pump_risk": 0.3,
                "lhb_alignment_status": "matched",
            },
            {
                "case_id": "c_failed_wave",
                "ts_code": "000017.SZ",
                "stock_name": "FailedWave",
                "case_type": "failed_second_wave",
                "event_type": "second_wave_start",
                "event_date": "2024-01-24",
                "lhb_on_event_date": False,
                "lhb_before_event_3d": False,
                "lhb_after_event_3d": True,
                "lhb_reason": "",
                "lhb_net_buy_amount": None,
                "institution_net_buy": None,
                "top_seat_concentration": None,
                "repeat_on_list_count_3d": 0,
                "repeat_on_list_count_5d": 0,
                "lhb_one_day_pump_risk": None,
                "lhb_alignment_status": "matched",
            },
            {
                "case_id": "c_a_kill",
                "ts_code": "000002.SZ",
                "stock_name": "AKill",
                "case_type": "a_kill_failure",
                "event_type": "a_kill_start",
                "event_date": "2025-09-18",
                "lhb_on_event_date": True,
                "lhb_before_event_3d": True,
                "lhb_after_event_3d": True,
                "lhb_reason": "日换手率达20%",
                "lhb_net_buy_amount": -900.0,
                "institution_net_buy": -200.0,
                "top_seat_concentration": 0.7,
                "repeat_on_list_count_3d": 3,
                "repeat_on_list_count_5d": 4,
                "lhb_one_day_pump_risk": 0.9,
                "lhb_alignment_status": "matched",
            },
        ]
    ).reindex(columns=lhb_data.LHB_ALIGNMENT_COLUMNS)


def _sample_lhb_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-05-10",
                "ts_code": "600726.SH",
                "on_lhb": True,
                "lhb_reason": "日涨幅偏离值达7%",
                "lhb_net_buy_amount": 200.0,
                "lhb_net_buy_ratio": 0.04,
                "lhb_buy_amount": 1200.0,
                "lhb_sell_amount": 1000.0,
                "institution_net_buy": 100.0,
                "top_seat_concentration": 0.2,
                "repeat_on_list_count_3d": 1,
                "repeat_on_list_count_5d": 1,
                "lhb_after_limit_up": True,
                "lhb_after_break_limit": False,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.2,
                "source": "akshare",
            },
            {
                "trade_date": "2026-05-12",
                "ts_code": "600726.SH",
                "on_lhb": True,
                "lhb_reason": "日涨幅偏离值达7%",
                "lhb_net_buy_amount": 500.0,
                "lhb_net_buy_ratio": 0.06,
                "lhb_buy_amount": 1500.0,
                "lhb_sell_amount": 1000.0,
                "institution_net_buy": 300.0,
                "top_seat_concentration": 0.2,
                "repeat_on_list_count_3d": 2,
                "repeat_on_list_count_5d": 3,
                "lhb_after_limit_up": True,
                "lhb_after_break_limit": False,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.3,
                "source": "akshare",
            },
            {
                "trade_date": "2024-01-26",
                "ts_code": "000017.SZ",
                "on_lhb": True,
                "lhb_reason": "日振幅达15%",
                "lhb_net_buy_amount": -100.0,
                "lhb_net_buy_ratio": -0.03,
                "lhb_buy_amount": 900.0,
                "lhb_sell_amount": 1000.0,
                "institution_net_buy": -50.0,
                "top_seat_concentration": 0.4,
                "repeat_on_list_count_3d": 1,
                "repeat_on_list_count_5d": 2,
                "lhb_after_limit_up": False,
                "lhb_after_break_limit": True,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.7,
                "source": "akshare",
            },
            {
                "trade_date": "2025-09-18",
                "ts_code": "000002.SZ",
                "on_lhb": True,
                "lhb_reason": "日换手率达20%",
                "lhb_net_buy_amount": -900.0,
                "lhb_net_buy_ratio": -0.12,
                "lhb_buy_amount": 1000.0,
                "lhb_sell_amount": 1900.0,
                "institution_net_buy": -200.0,
                "top_seat_concentration": 0.7,
                "repeat_on_list_count_3d": 3,
                "repeat_on_list_count_5d": 4,
                "lhb_after_limit_up": False,
                "lhb_after_break_limit": False,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.9,
                "source": "akshare",
            },
        ]
    ).reindex(columns=lhb_data.LHB_EVENT_FEATURE_COLUMNS)


def _sample_lhb_factor_review() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c_success",
                "ts_code": "600726.SH",
                "event_type": "second_wave_start",
                "event_date": "2026-05-12",
                "relative_day": 0,
                "future_3d_return": 0.08,
                "future_5d_return": 0.12,
                "future_10d_return": 0.20,
                "future_5d_max_drawdown": -0.03,
                "future_10d_max_drawdown": -0.05,
            },
            {
                "case_id": "c_failed_wave",
                "ts_code": "000017.SZ",
                "event_type": "second_wave_start",
                "event_date": "2024-01-24",
                "relative_day": 0,
                "future_3d_return": -0.02,
                "future_5d_return": -0.05,
                "future_10d_return": -0.10,
                "future_5d_max_drawdown": -0.08,
                "future_10d_max_drawdown": -0.15,
            },
            {
                "case_id": "c_a_kill",
                "ts_code": "000002.SZ",
                "event_type": "a_kill_start",
                "event_date": "2025-09-18",
                "relative_day": 0,
                "future_3d_return": -0.08,
                "future_5d_return": -0.12,
                "future_10d_return": -0.20,
                "future_5d_max_drawdown": -0.15,
                "future_10d_max_drawdown": -0.25,
            },
        ]
    )


def _write_csv(tmp_path: Path, name: str, frame: pd.DataFrame) -> Path:
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1_selects_reranked_topn():
    lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "A",
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "fill_status": "filled",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-04",
                "realized_return": -0.10,
                "top_n": 10,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "B",
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-04",
                "realized_return": 0.20,
                "top_n": 10,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "C",
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2025-01-04",
                "exit_trade_date": "2025-01-05",
                "realized_return": 0.10,
                "top_n": 10,
            },
        ]
    )
    scored = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": "A", "auction_enhanced_score": 70.0},
            {"trade_date": "2025-01-02", "ts_code": "B", "auction_enhanced_score": 150.0},
            {"trade_date": "2025-01-03", "ts_code": "C", "auction_enhanced_score": 100.0},
        ]
    )

    result = lhb_data.build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
        lifecycle_trades=lifecycle,
        scored_candidates=scored,
        output_dir="unused",
        top_ns=[1],
        max_positions=10,
        position_pct=0.10,
        write_outputs=False,
    )

    summary = result["summary"]
    baseline = summary[summary["strategy"].eq("baseline_original_order")].iloc[0]
    enhanced = summary[summary["strategy"].eq("auction_enhanced_rerank")].iloc[0]
    assert baseline["filled_trade_count"] == 2
    assert enhanced["filled_trade_count"] == 2
    assert enhanced["final_equity"] > baseline["final_equity"]
    selected = result["selected_trades"]
    enhanced_first_day = selected[
        selected["strategy"].eq("auction_enhanced_rerank")
        & selected["trade_date"].eq("2025-01-02")
    ].iloc[0]
    assert enhanced_first_day["ts_code"] == "B"


def test_build_lhb_phase18f_tradable_joint_exit_replay_v1_uses_t1_5min_exit():
    account_trades = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.0,
                "exit_trade_date": "2026-03-10",
                "exit_price": 11.0,
                "realized_return": 0.10,
                "position_notional": 0.1,
                "pnl": 0.01,
                "strategy": "auction_enhanced_rerank",
            }
        ]
    )
    joint_state = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "weak_open_confirm": True,
            }
        ]
    )
    close_lifecycle_detail = pd.DataFrame(
        [
            {
                "trade_id": 0,
                "trade_date": "2026-03-05",
                "entry_trade_date": "2026-03-06",
                "exit_trade_date": "2026-03-10",
                "ts_code": "600001.SH",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "auction_trade_date": "2026-03-06",
                "close_auction_return": -0.002,
            }
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-06",
                "trade_time": "2026-03-06 09:35:00",
                "ts_code": "600001.SH",
                "open": 9.8,
                "high": 9.9,
                "low": 9.7,
                "close": 9.8,
                "volume": 1000.0,
                "amount": 9800.0,
            },
            {
                "trade_date": "2026-03-09",
                "trade_time": "2026-03-09 09:35:00",
                "ts_code": "600001.SH",
                "open": 10.4,
                "high": 10.5,
                "low": 10.3,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 10500.0,
            },
            {
                "trade_date": "2026-03-09",
                "trade_time": "2026-03-09 09:40:00",
                "ts_code": "600001.SH",
                "open": 10.5,
                "high": 10.6,
                "low": 10.4,
                "close": 10.6,
                "volume": 1000.0,
                "amount": 10600.0,
            },
        ]
    )

    result = lhb_data.build_lhb_phase18f_tradable_joint_exit_replay_v1(
        account_trades=account_trades,
        joint_state_detail=joint_state,
        close_lifecycle_detail=close_lifecycle_detail,
        minute_bars=minute_bars,
    )

    adjusted = result["adjusted_trades"]
    open_profile = adjusted[
        adjusted["phase18f_exit_profile"].eq("priority_exit_next_open_5min")
    ].iloc[0]
    vwap_profile = adjusted[
        adjusted["phase18f_exit_profile"].eq("priority_exit_next_30m_vwap")
    ].iloc[0]
    assert open_profile["phase18f_adjust_reason"] == "weak_open_plus_negative_close_auction"
    assert open_profile["exit_trade_date"] == "2026-03-09"
    assert open_profile["exit_time"] == "09:35:00"
    assert round(open_profile["realized_return"], 6) == 0.05
    assert round(vwap_profile["exit_price"], 6) == 10.55
    assert round(vwap_profile["realized_return"], 6) == 0.055


def test_build_lhb_phase18f_tradable_joint_exit_replay_v1_allows_same_day_earlier_5min_exit():
    account_trades = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2026-03-06",
                "entry_price": 10.0,
                "exit_trade_date": "2026-03-09",
                "exit_time": "10:30:00",
                "exit_price": 9.8,
                "realized_return": -0.02,
                "strategy": "auction_enhanced_rerank",
            }
        ]
    )
    joint_state = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "ts_code": "600001.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "weak_open_confirm": True,
            }
        ]
    )
    close_lifecycle_detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-05",
                "entry_trade_date": "2026-03-06",
                "ts_code": "600001.SH",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "auction_trade_date": "2026-03-06",
                "close_auction_return": -0.002,
            }
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-09",
                "trade_time": "2026-03-09 09:35:00",
                "ts_code": "600001.SH",
                "close": 10.4,
                "volume": 1000.0,
                "amount": 10400.0,
            }
        ]
    )

    result = lhb_data.build_lhb_phase18f_tradable_joint_exit_replay_v1(
        account_trades=account_trades,
        joint_state_detail=joint_state,
        close_lifecycle_detail=close_lifecycle_detail,
        minute_bars=minute_bars,
    )

    open_profile = result["adjusted_trades"][
        result["adjusted_trades"]["phase18f_exit_profile"].eq("priority_exit_next_open_5min")
    ].iloc[0]
    assert open_profile["exit_trade_date"] == "2026-03-09"
    assert open_profile["exit_time"] == "09:35:00"
    assert round(open_profile["realized_return"], 6) == 0.04
