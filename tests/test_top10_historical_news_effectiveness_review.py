from pathlib import Path

import pandas as pd

import stock_research.cli as cli
import stock_research.top10_historical_news_effectiveness_review as review
from stock_research.top10_historical_news_effectiveness_review import (
    build_future_label_frame,
    build_count_bucket_summary,
    build_group_summary,
    build_review_base_frame,
    load_review_inputs,
    run_top10_historical_news_effectiveness_review,
)


def test_load_review_inputs_reads_required_historical_artifacts(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            }
        ]
    ).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "notice_count_3d": 1,
            }
        ]
    ).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    ).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    payload = load_review_inputs(base_dir=base)

    assert list(payload) == ["candidates", "features", "enrichment"]
    assert len(payload["candidates"]) == 1
    assert len(payload["features"]) == 1
    assert len(payload["enrichment"]) == 1


def test_run_top10_historical_news_effectiveness_review_returns_paths_first_contract(tmp_path):
    base = tmp_path / "base"
    out = tmp_path / "out"
    base.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            }
        ]
    ).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "notice_count_3d": 1,
            }
        ]
    ).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    ).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    result = cli.run_top10_historical_news_effectiveness_review(
        base_dir=base,
        adjust_type="qfq",
        output_dir=out,
    )

    assert set(result) >= {"paths", "adjust_type"}
    assert result["adjust_type"] == "qfq"
    assert result["paths"]["base_dir"] == str(base)
    assert result["paths"]["candidates"] == str(base / "historical_top10_candidates.csv")
    assert result["paths"]["features"] == str(base / "historical_news_feature_daily.csv")
    assert result["paths"]["enrichment"] == str(base / "historical_top10_news_enrichment.csv")
    assert result["paths"]["output_dir"] == str(out)
    assert "payload" not in result
    assert "candidates" not in result


def test_run_top10_historical_news_effectiveness_review_uses_market_max_date_for_bars(
    tmp_path, monkeypatch
):
    base = tmp_path / "base"
    out = tmp_path / "out"
    base.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            },
        ]
    ).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "notice_count_3d": 1,
            }
        ]
    ).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    ).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    observed = {}

    def fake_latest_trade_date(*, adjust_type):
        assert adjust_type == "qfq"
        return "2025-01-09"

    def fake_load_daily_bars_for_review(*, asset_ids, end_date, adjust_type):
        observed["asset_ids"] = asset_ids
        observed["end_date"] = end_date
        observed["adjust_type"] = adjust_type
        return pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-02",
                    "close": 10.0,
                    "low": 9.8,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-09",
                    "close": 12.0,
                    "low": 11.5,
                },
            ]
        )

    monkeypatch.setattr(review, "latest_trade_date", fake_latest_trade_date)
    monkeypatch.setattr(review, "load_daily_bars_for_review", fake_load_daily_bars_for_review)

    review.run_top10_historical_news_effectiveness_review(
        base_dir=base,
        adjust_type="qfq",
        output_dir=out,
    )

    assert observed["adjust_type"] == "qfq"
    assert observed["asset_ids"] == ["CN:SH:600919"]
    assert observed["end_date"] == "2025-01-09"
    assert observed["end_date"] != "2025-01-03"


def test_review_top10_historical_news_effectiveness_cli_prints_paths(monkeypatch, capsys):
    def fake_run_top10_historical_news_effectiveness_review(**kwargs):
        assert kwargs == {
            "base_dir": "/tmp/base",
            "adjust_type": "qfq",
            "output_dir": "/tmp/out",
        }
        return {
            "paths": {
                "base_dir": "/tmp/base",
                "candidates": "/tmp/base/historical_top10_candidates.csv",
                "features": "/tmp/base/historical_news_feature_daily.csv",
                "enrichment": "/tmp/base/historical_top10_news_enrichment.csv",
                "output_dir": "/tmp/out",
            },
            "adjust_type": "qfq",
        }

    monkeypatch.setattr(
        "stock_research.cli.run_top10_historical_news_effectiveness_review",
        fake_run_top10_historical_news_effectiveness_review,
    )

    exit_code = cli.main_for_args(
        [
            "review-top10-historical-news-effectiveness",
            "--base-dir",
            "/tmp/base",
            "--adjust-type",
            "qfq",
            "--output-dir",
            "/tmp/out",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        "review_top10_historical_news_effectiveness|base_dir|/tmp/base",
        (
            "review_top10_historical_news_effectiveness|candidates|"
            "/tmp/base/historical_top10_candidates.csv"
        ),
        (
            "review_top10_historical_news_effectiveness|features|"
            "/tmp/base/historical_news_feature_daily.csv"
        ),
        (
            "review_top10_historical_news_effectiveness|enrichment|"
            "/tmp/base/historical_top10_news_enrichment.csv"
        ),
        "review_top10_historical_news_effectiveness|output_dir|/tmp/out",
    ]


def test_build_future_return_labels_from_close_series():
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-02",
                "close": 10.0,
                "low": 9.8,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-03",
                "close": 11.0,
                "low": 10.5,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-06",
                "close": 12.0,
                "low": 11.2,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-07",
                "close": 11.5,
                "low": 10.9,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-08",
                "close": 13.0,
                "low": 12.4,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-09",
                "close": 14.0,
                "low": 13.5,
            },
        ]
    )

    labels = build_future_label_frame(bars=bars)
    row = labels.loc[
        (labels["asset_id"] == "CN:SH:600919")
        & (labels["trade_date"] == "2025-01-02")
    ].iloc[0]

    assert round(row["future_1d_return"], 6) == 0.10
    assert round(row["future_3d_return"], 6) == 0.15
    assert round(row["future_5d_return"], 6) == 0.40
    assert pd.isna(row["future_10d_return"])
    assert pd.isna(row["future_20d_return"])
    assert {
        "future_1d_max_drawdown",
        "future_3d_max_drawdown",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    }.issubset(labels.columns)
    assert round(row["future_1d_max_drawdown"], 6) == 0.05
    assert round(row["future_3d_max_drawdown"], 6) == 0.05
    assert round(row["future_5d_max_drawdown"], 6) == 0.05
    assert round(row["future_10d_max_drawdown"], 6) == 0.05
    assert round(row["future_20d_max_drawdown"], 6) == 0.05


def test_build_future_drawdown_labels_uses_forward_window_lows():
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-02",
                "close": 10.0,
                "low": 9.8,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-03",
                "close": 11.0,
                "low": 8.5,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-06",
                "close": 12.0,
                "low": 9.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-07",
                "close": 11.5,
                "low": 10.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-08",
                "close": 13.0,
                "low": 11.5,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-09",
                "close": 14.0,
                "low": 13.5,
            },
        ]
    )

    labels = build_future_label_frame(bars=bars)
    row = labels.loc[
        (labels["asset_id"] == "CN:SH:600919")
        & (labels["trade_date"] == "2025-01-02")
    ].iloc[0]

    assert {
        "future_1d_max_drawdown",
        "future_3d_max_drawdown",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
        "future_20d_max_drawdown",
    }.issubset(labels.columns)
    assert round(row["future_5d_max_drawdown"], 6) == -0.15
    assert round(row["future_1d_max_drawdown"], 6) == -0.15
    assert round(row["future_3d_max_drawdown"], 6) == -0.15
    assert round(row["future_10d_max_drawdown"], 6) == -0.15
    assert round(row["future_20d_max_drawdown"], 6) == -0.15


def test_build_future_drawdown_labels_ignores_nan_lows_inside_forward_window():
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-02",
                "close": 10.0,
                "low": 9.8,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-03",
                "close": 11.0,
                "low": float("nan"),
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-06",
                "close": 12.0,
                "low": 8.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-07",
                "close": 13.0,
                "low": 12.0,
            },
        ]
    )

    labels = build_future_label_frame(bars=bars)
    row = labels.loc[
        (labels["asset_id"] == "CN:SH:600919")
        & (labels["trade_date"] == "2025-01-02")
    ].iloc[0]

    assert round(row["future_3d_max_drawdown"], 6) == -0.2
    assert round(row["future_5d_max_drawdown"], 6) == -0.2


def test_build_future_drawdown_labels_are_isolated_by_asset():
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-02",
                "close": 10.0,
                "low": 9.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-03",
                "close": 11.0,
                "low": 8.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-06",
                "close": 12.0,
                "low": 7.0,
            },
            {
                "asset_id": "CN:SH:600919",
                "trade_date": "2025-01-07",
                "close": 13.0,
                "low": 6.5,
            },
            {
                "asset_id": "CN:SH:000001",
                "trade_date": "2025-01-02",
                "close": 20.0,
                "low": 19.0,
            },
            {
                "asset_id": "CN:SH:000001",
                "trade_date": "2025-01-03",
                "close": 21.0,
                "low": 18.0,
            },
            {
                "asset_id": "CN:SH:000001",
                "trade_date": "2025-01-06",
                "close": 22.0,
                "low": 17.0,
            },
            {
                "asset_id": "CN:SH:000001",
                "trade_date": "2025-01-07",
                "close": 23.0,
                "low": 16.5,
            },
        ]
    )

    labels = build_future_label_frame(bars=bars)

    sh_row = labels.loc[
        (labels["asset_id"] == "CN:SH:600919")
        & (labels["trade_date"] == "2025-01-02")
    ].iloc[0]
    other_row = labels.loc[
        (labels["asset_id"] == "CN:SH:000001")
        & (labels["trade_date"] == "2025-01-02")
    ].iloc[0]

    assert round(sh_row["future_3d_max_drawdown"], 6) == -0.35
    assert round(other_row["future_3d_max_drawdown"], 6) == -0.175
    assert round(sh_row["future_3d_return"], 6) == 0.3
    assert round(other_row["future_3d_return"], 6) == 0.15


def test_build_review_base_frame_keeps_uncovered_candidates():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": "宇通客车",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "notice_count_3d": 1,
            }
        ]
    )
    enrichment = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    )
    labels = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "future_5d_return": 0.05,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "future_5d_return": -0.01,
            },
        ]
    )

    frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )

    assert len(frame) == 2
    assert frame["asset_id"].tolist() == ["CN:SH:600919", "CN:SH:600066"]
    uncovered = frame.loc[frame["asset_id"] == "CN:SH:600066"].iloc[0]
    assert pd.isna(uncovered["notice_count_3d"])
    assert pd.isna(uncovered["historical_event_summary"])
    assert uncovered["future_5d_return"] == -0.01


def test_build_review_base_frame_dedupes_duplicate_upstream_rows_with_last_row_wins():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "notice_count_3d": 1,
                "news_attention_level": "low",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "notice_count_3d": 7,
                "news_attention_level": "high",
            },
        ]
    )
    enrichment = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "historical_event_summary": "first summary",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "historical_event_summary": "last summary",
            },
        ]
    )
    labels = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "future_5d_return": 0.01,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "future_5d_return": 0.09,
            },
        ]
    )

    frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["notice_count_3d"] == 7
    assert row["news_attention_level"] == "high"
    assert row["historical_event_summary"] == "last summary"
    assert row["future_5d_return"] == 0.09


def test_build_review_base_frame_derives_coverage_group():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": "宇通客车",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "news_attention_level": "high",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "news_attention_level": "low",
            },
        ]
    )
    enrichment = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    )
    labels = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "future_5d_return": 0.05,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "future_5d_return": -0.01,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "future_5d_return": 0.02,
            },
        ]
    )

    frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )

    assert frame["coverage_group"].tolist() == [
        "historical_summary_present",
        "news_feature_only",
        "no_news_feature",
    ]


def test_build_review_base_frame_derives_source_type_group():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": "宇通客车",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600750",
                "ts_code": "600750.SH",
                "stock_name": "江中药业",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "notice_count_10d": 2,
                "research_report_count_20d": 1,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "notice_count_10d": 3,
                "research_report_count_20d": 0,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "notice_count_10d": 0,
                "research_report_count_20d": 2,
            },
        ]
    )
    enrichment = pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919"}]
    )
    labels = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "future_5d_return": 0.05,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600066",
                "future_5d_return": -0.01,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "future_5d_return": 0.02,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600750",
                "future_5d_return": 0.03,
            },
        ]
    )

    frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )

    assert frame["source_type_group"].tolist() == [
        "notice_and_report",
        "notice_only",
        "report_only",
        "no_historical_event",
    ]


def test_build_coverage_summary_ignores_nan_returns_in_win_rates():
    frame = pd.DataFrame(
        [
            {
                "coverage_group": "historical_summary_present",
                "future_5d_return": 0.10,
                "future_10d_return": 0.15,
            },
            {
                "coverage_group": "historical_summary_present",
                "future_5d_return": float("nan"),
                "future_10d_return": float("nan"),
            },
        ]
    )

    summary = build_group_summary(frame, group_col="coverage_group")

    row = summary.loc[summary["coverage_group"] == "historical_summary_present"].iloc[0]
    assert row["sample_count"] == 2
    assert round(row["win_rate_5d"], 6) == 1.0
    assert round(row["win_rate_10d"], 6) == 1.0


def test_build_group_summary_returns_stable_schema_for_empty_and_thin_input():
    empty_summary = build_group_summary(
        pd.DataFrame(columns=["coverage_group"]),
        group_col="coverage_group",
    )

    expected_columns = [
        "coverage_group",
        "sample_count",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_1d_return",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_20d_return",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "avg_future_20d_max_drawdown",
    ]
    assert empty_summary.columns.tolist() == expected_columns
    assert empty_summary.empty

    thin_summary = build_group_summary(
        pd.DataFrame(
            [
                {
                    "coverage_group": "historical_summary_present",
                    "future_5d_return": 0.10,
                    "future_10d_return": 0.15,
                }
            ]
        ),
        group_col="coverage_group",
    )

    assert thin_summary.columns.tolist() == expected_columns
    row = thin_summary.iloc[0]
    assert row["coverage_group"] == "historical_summary_present"
    assert round(row["avg_future_5d_return"], 6) == 0.10
    assert round(row["avg_future_10d_return"], 6) == 0.15
    assert pd.isna(row["avg_future_1d_return"])
    assert pd.isna(row["avg_future_20d_max_drawdown"])


def test_build_source_type_summary_includes_notice_and_report_group():
    frame = pd.DataFrame(
        [
            {
                "source_type_group": "notice_and_report",
                "future_5d_return": 0.03,
                "future_10d_return": 0.04,
                "future_20d_max_drawdown": -0.04,
            },
            {
                "source_type_group": "notice_only",
                "future_5d_return": -0.01,
                "future_10d_return": 0.00,
                "future_20d_max_drawdown": -0.08,
            },
        ]
    )

    summary = build_group_summary(frame, group_col="source_type_group")

    assert set(summary["source_type_group"]) == {"notice_and_report", "notice_only"}
    row = summary.loc[summary["source_type_group"] == "notice_and_report"].iloc[0]
    assert row["sample_count"] == 1
    assert round(row["win_rate_5d"], 6) == 1.0
    assert round(row["win_rate_10d"], 6) == 1.0
    assert round(row["avg_future_5d_return"], 6) == 0.03
    assert round(row["avg_future_10d_return"], 6) == 0.04
    assert round(row["avg_future_20d_max_drawdown"], 6) == -0.04


def test_build_count_bucket_summary_uses_0_1_2plus_buckets():
    frame = pd.DataFrame(
        [
            {"notice_count_3d": 0, "future_5d_return": -0.01},
            {"notice_count_3d": 1, "future_5d_return": 0.02},
            {"notice_count_3d": 3, "future_5d_return": 0.05},
        ]
    )

    summary = build_count_bucket_summary(frame, feature_name="notice_count_3d")

    assert summary["bucket"].tolist() == ["0", "1", "2+"]


def test_run_review_writes_all_outputs(tmp_path, monkeypatch):
    base = tmp_path / "base"
    out = tmp_path / "out"
    base.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
            }
        ]
    ).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "notice_count_3d": 1,
                "notice_count_10d": 1,
                "research_report_count_20d": 0,
                "news_attention_level": "low",
            }
        ]
    ).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600919",
                "ts_code": "600919.SH",
                "stock_name": "江苏银行",
                "historical_event_summary": "近3日有1条公告",
            }
        ]
    ).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    monkeypatch.setattr(
        "stock_research.top10_historical_news_effectiveness_review.load_daily_bars_for_review",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-02",
                    "close": 10.0,
                    "low": 9.8,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-03",
                    "close": 10.5,
                    "low": 10.1,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-06",
                    "close": 10.8,
                    "low": 10.3,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-07",
                    "close": 11.0,
                    "low": 10.6,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-08",
                    "close": 11.2,
                    "low": 10.8,
                },
                {
                    "asset_id": "CN:SH:600919",
                    "trade_date": "2025-01-09",
                    "close": 11.4,
                    "low": 11.0,
                },
            ]
        ),
    )

    result = run_top10_historical_news_effectiveness_review(
        base_dir=base,
        adjust_type="qfq",
        output_dir=out,
    )

    assert Path(result["paths"]["base"]).exists()
    assert Path(result["paths"]["coverage_summary"]).exists()
    assert Path(result["paths"]["source_type_summary"]).exists()
    assert Path(result["paths"]["feature_bucket_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()
