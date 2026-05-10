from pathlib import Path

import pandas as pd

import stock_research.reports.daily_research_report_cli as daily_research_report_cli
from stock_research.reports.daily_research_report_cli import (
    build_parser,
    enrich_top_scores_with_industry,
    load_feature_snapshot,
    load_industry_memberships,
    main,
)


def test_daily_research_report_cli_parser_accepts_arguments():
    args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "20",
            "--index-id",
            "CSI300",
            "--market-lookback-days",
            "90",
            "--industry-system",
            "csrc",
            "--sector-lookback-days",
            "60",
            "--positions-csv",
            "/tmp/positions.csv",
            "--reports-dir",
            "/tmp/reports",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 20
    assert args.index_id == "CSI300"
    assert args.market_lookback_days == 90
    assert args.industry_system == "csrc"
    assert args.sector_lookback_days == 60
    assert args.positions_csv == "/tmp/positions.csv"
    assert args.reports_dir == "/tmp/reports"
    assert args.apply_report_run_schema is True
    assert args.record_run is True


def test_daily_research_report_cli_main_prints_stable_output(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "report_paths": {
                "bundle": {"markdown_path": tmp_path / "bundle.md"},
                "topn": {"markdown_path": tmp_path / "topn.md"},
                "market_state": {"markdown_path": tmp_path / "market.md"},
                "sector_strength": {"markdown_path": tmp_path / "sector.md"},
                "risk_alerts": {"markdown_path": tmp_path / "risk.md"},
                "position_review": {"markdown_path": tmp_path / "positions.md"},
            },
            "risk_alerts": [],
            "position_review": [],
        }

    monkeypatch.setattr(
        "sys.argv",
        [
            "python -m stock_research.reports.daily_research_report_cli",
            "--trade-date",
            "2026-05-08",
            "--top-n",
            "20",
            "--reports-dir",
            str(tmp_path),
        ],
    )

    main(runner=fake_runner)

    assert calls[0]["trade_date"] == "2026-05-08"
    assert calls[0]["top_n"] == 20
    assert calls[0]["reports_dir"] == Path(tmp_path)
    assert calls[0]["apply_report_run_schema_first"] is False
    assert calls[0]["record_run"] is False
    assert capsys.readouterr().out.splitlines() == [
        f"daily_research_report|bundle|{tmp_path / 'bundle.md'}",
        f"daily_research_report|topn|{tmp_path / 'topn.md'}",
        f"daily_research_report|market_state|{tmp_path / 'market.md'}",
        f"daily_research_report|sector_strength|{tmp_path / 'sector.md'}",
        f"daily_research_report|risk_alerts|{tmp_path / 'risk.md'}",
        f"daily_research_report|position_review|{tmp_path / 'positions.md'}",
    ]


def test_run_daily_research_report_loads_inputs_and_writes_reports(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        daily_research_report_cli,
        "load_top_scores",
        lambda trade_date, score_version, top_n: [{"asset_id": "A", "rank": 1, "score_total": 88.0}],
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "load_industry_memberships",
        lambda trade_date, asset_ids, industry_system: {
            "A": {"industry_code": "TECH", "industry_name": "Technology"}
        },
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "load_market_state_bars",
        lambda start_date, end_date, index_id: pd.DataFrame(
            [{"trade_date": end_date, "index_id": index_id, "close": 100.0, "amount": 1000.0}]
        ),
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "calc_market_state",
        lambda bars, trade_date, index_id: {
            "trade_date": trade_date,
            "index_id": index_id,
            "market_state": "bullish",
            "risk_level": "low",
            "entry_allowed": True,
        },
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "load_sector_strength_bars",
        lambda start_date, end_date, industry_system: pd.DataFrame(
            [{"trade_date": end_date, "industry_system": industry_system, "industry_code": "TECH"}]
        ),
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "calc_sector_strength",
        lambda bars, trade_date, top_n: pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "industry_system": "csrc",
                    "industry_code": "TECH",
                    "industry_name": "Technology",
                    "ret_5d": 0.02,
                    "ret_20d": 0.05,
                    "amount_ratio_5_20": 1.1,
                    "strength_score": 88.0,
                    "strength_rank": 1,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        daily_research_report_cli,
        "load_feature_snapshot",
        lambda trade_date, asset_ids: pd.DataFrame(
            [{"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.1}]
        ),
    )

    def fake_writer(**kwargs):
        calls.update(kwargs)
        return {"report_paths": {"bundle": {"markdown_path": tmp_path / "bundle.md"}}}

    monkeypatch.setattr(daily_research_report_cli, "write_daily_research_reports", fake_writer)
    record_calls = []
    monkeypatch.setattr(daily_research_report_cli, "apply_report_run_schema", lambda: record_calls.append("schema"))
    monkeypatch.setattr(
        daily_research_report_cli,
        "record_report_run",
        lambda **kwargs: record_calls.append(kwargs) or "run-1",
    )

    result = daily_research_report_cli.run_daily_research_report(
        trade_date="2026-05-08",
        score_version="manual_v1",
        top_n=20,
        index_id="CSI300",
        market_lookback_days=90,
        industry_system="csrc",
        sector_lookback_days=60,
        positions_csv=None,
        reports_dir=tmp_path,
        apply_report_run_schema_first=True,
        record_run=True,
    )

    assert result["report_paths"]["bundle"]["markdown_path"] == tmp_path / "bundle.md"
    assert calls["trade_date"] == "2026-05-08"
    assert calls["score_version"] == "manual_v1"
    assert calls["top_scores"][0]["asset_id"] == "A"
    assert calls["top_scores"][0]["industry_code"] == "TECH"
    assert calls["market_state"]["market_state"] == "bullish"
    assert calls["sector_strength"].iloc[0]["industry_code"] == "TECH"
    assert calls["positions"] == []
    assert calls["feature_snapshot"].iloc[0]["feature_name"] == "ret_5d"
    assert calls["output_dir"] == tmp_path
    assert result["report_run_id"] == "run-1"
    assert record_calls[0] == "schema"
    assert record_calls[1]["trade_date"] == "2026-05-08"
    assert record_calls[1]["report_type"] == "daily_research"


def test_load_feature_snapshot_queries_requested_assets(monkeypatch):
    calls = {}

    class _Connection:
        pass

    class _Context:
        def __enter__(self):
            return _Connection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["service"] = service
        return _Context()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = list(params)
        return [{"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.1}]

    monkeypatch.setattr(daily_research_report_cli, "connect", fake_connect)
    monkeypatch.setattr(daily_research_report_cli, "fetch_all", fake_fetch_all)

    result = load_feature_snapshot("2026-05-08", ["A", "B"])

    assert calls["service"] == "stock_research"
    assert "FROM feature_snapshot" in calls["sql"]
    assert "asset_id IN (%s, %s)" in calls["sql"]
    assert calls["params"] == ["2026-05-08", "A", "B"]
    assert result.iloc[0]["feature_name"] == "ret_5d"


def test_load_industry_memberships_queries_point_in_time_memberships(monkeypatch):
    calls = {}

    class _Connection:
        pass

    class _Context:
        def __enter__(self):
            return _Connection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["service"] = service
        return _Context()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = list(params)
        return [
            {
                "asset_id": "A",
                "industry_code": "TECH",
                "industry_name": "Technology",
                "level": 1,
            }
        ]

    monkeypatch.setattr(daily_research_report_cli, "connect", fake_connect)
    monkeypatch.setattr(daily_research_report_cli, "fetch_all", fake_fetch_all)

    result = load_industry_memberships(
        trade_date="2026-05-08",
        asset_ids=["A", "B"],
        industry_system="csrc",
    )

    assert calls["service"] == "stock_research"
    assert "FROM core.industry_membership" in calls["sql"]
    assert "asset_id IN (%s, %s)" in calls["sql"]
    assert calls["params"] == ["csrc", "2026-05-08", "2026-05-08", "A", "B"]
    assert result["A"]["industry_code"] == "TECH"


def test_enrich_top_scores_with_industry_preserves_rows_without_membership():
    result = enrich_top_scores_with_industry(
        top_scores=[
            {"asset_id": "A", "rank": 1},
            {"asset_id": "B", "rank": 2},
        ],
        memberships={"A": {"industry_code": "TECH", "industry_name": "Technology"}},
    )

    assert result[0]["industry_code"] == "TECH"
    assert "industry_code" not in result[1]
