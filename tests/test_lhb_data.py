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
