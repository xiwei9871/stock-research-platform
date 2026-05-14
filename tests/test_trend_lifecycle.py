from pathlib import Path

import pandas as pd
import pytest

from stock_research import trend_lifecycle


def _bars(asset_id: str, closes: list[float], *, start: str = "2026-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "trade_date": [date.date().isoformat() for date in dates],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "amount": [50_000_000.0] * len(closes),
        }
    )


def test_compute_trend_segments_for_asset_identifies_mid_trend_range():
    closes = [100.0] + [100.0 + index for index in range(1, 71)]
    bars = _bars("A", closes)

    segments = trend_lifecycle.compute_trend_segments_for_asset(
        "A",
        bars,
        rules=(trend_lifecycle.TrendRule("mid_trend", 60, 120, 0.40, 0.80),),
    )

    assert len(segments) == 1
    segment = segments.iloc[0]
    assert segment["asset_id"] == "A"
    assert segment["label_set"] == "trend_event"
    assert segment["label_version"] == "v1"
    assert segment["trend_label"] == "mid_trend"
    assert segment["start_date"] == bars.iloc[0]["trade_date"]
    assert segment["peak_date"] == bars.iloc[70]["trade_date"]
    assert segment["gain"] == pytest.approx(0.70)
    assert segment["duration"] == 70
    assert segment["avg_amount"] == pytest.approx(50_000_000.0)
    assert segment["max_drawdown_before_peak"] == pytest.approx(0.0)


def test_compute_trend_segments_deduplicates_overlapping_mid_trends_to_earlier_segment():
    closes = [100.0 + index for index in range(0, 71)]
    bars = _bars("A", closes)

    segments = trend_lifecycle.compute_trend_segments_for_asset(
        "A",
        bars,
        rules=(trend_lifecycle.TrendRule("mid_trend", 60, 120, 0.40, 0.80),),
    )

    assert len(segments) == 1
    assert segments.iloc[0]["start_date"] == bars.iloc[0]["trade_date"]


def test_compute_trend_segments_deduplicates_overlapping_large_trends_to_strongest_gain():
    closes = [100.0, 80.0] + [80.0 + 2.0 * index for index in range(1, 121)]
    bars = _bars("A", closes)

    segments = trend_lifecycle.compute_trend_segments_for_asset(
        "A",
        bars,
        rules=(trend_lifecycle.TrendRule("large_trend", 1, 120, 0.80, None),),
    )

    assert len(segments) == 1
    assert segments.iloc[0]["start_date"] == bars.iloc[1]["trade_date"]
    assert segments.iloc[0]["gain"] > 2.0


def test_default_large_trend_detects_peak_within_120_days():
    closes = [100.0] + [100.0] * 49 + [181.0] + [120.0] * 80
    bars = _bars("A", closes)

    segments = trend_lifecycle.compute_trend_segments_for_asset("A", bars)

    large_segments = segments[segments["trend_label"] == "large_trend"]
    assert len(large_segments) == 1
    assert large_segments.iloc[0]["peak_date"] == bars.iloc[50]["trade_date"]


def test_lifecycle_samples_map_all_stage_boundaries():
    bars = _bars("A", [100.0 + index for index in range(0, 101)])
    segments = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trend_label": "mid_trend",
                "start_date": bars.iloc[0]["trade_date"],
                "peak_date": bars.iloc[100]["trade_date"],
                "start_close": 100.0,
                "peak_close": 200.0,
                "gain": 1.0,
                "duration": 100,
                "avg_amount": 50_000_000.0,
                "max_drawdown_before_peak": 0.0,
            }
        ]
    )

    samples = trend_lifecycle.build_lifecycle_samples(segments, bars)
    stage_by_index = dict(zip(samples["bars_since_start"], samples["stage"], strict=True))

    assert stage_by_index[0] == "early"
    assert stage_by_index[20] == "early"
    assert stage_by_index[21] == "early_mid"
    assert stage_by_index[40] == "early_mid"
    assert stage_by_index[41] == "mid"
    assert stage_by_index[60] == "mid"
    assert stage_by_index[61] == "late_mid"
    assert stage_by_index[80] == "late_mid"
    assert stage_by_index[81] == "late"
    assert stage_by_index[100] == "late"


def test_compute_entry_success_labels_distinguishes_profit_before_stop_from_stop_first():
    success_bars = _bars("A", [100.0, 104.0, 116.0, 90.0])
    failure_bars = _bars("B", [100.0, 91.0, 116.0, 120.0])
    bars = pd.concat([success_bars, failure_bars], ignore_index=True)
    signals = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": success_bars.iloc[0]["trade_date"]},
            {"asset_id": "B", "trade_date": failure_bars.iloc[0]["trade_date"]},
        ]
    )

    labels = trend_lifecycle.compute_entry_success_labels(
        bars,
        signals,
        rules=(trend_lifecycle.EntrySuccessRule("entry_success_20d", 20, 0.15, -0.08),),
    )

    result = labels.set_index("asset_id")["entry_success_20d"].to_dict()
    assert result == {"A": True, "B": False}


def test_compute_entry_success_labels_marks_uncovered_future_window():
    bars = _bars("A", [100.0, 101.0, 102.0])
    signals = pd.DataFrame([{"asset_id": "A", "trade_date": bars.iloc[0]["trade_date"]}])

    labels = trend_lifecycle.compute_entry_success_labels(
        bars,
        signals,
        rules=(trend_lifecycle.EntrySuccessRule("entry_success_20d", 20, 0.15, -0.08),),
    )

    row = labels.iloc[0]
    assert row["entry_success_20d"] is False
    assert row["entry_success_20d_covered"] is False


def test_top20_stage_hit_report_counts_stage_hits_without_replacing_scores():
    lifecycle_samples = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2026-01-01",
                "trend_label": "mid_trend",
                "stage": "early",
            },
            {
                "asset_id": "B",
                "trade_date": "2026-01-01",
                "trend_label": "large_trend",
                "stage": "late",
            },
        ]
    )
    scores = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-01", "rank": 1, "score_total": 9.0},
            {"asset_id": "B", "trade_date": "2026-01-01", "rank": 2, "score_total": 8.0},
            {"asset_id": "C", "trade_date": "2026-01-01", "rank": 3, "score_total": 7.0},
        ]
    )

    report = trend_lifecycle.build_top20_stage_hit_report(
        scores,
        lifecycle_samples,
        top_n=2,
    )

    records = report.sort_values(["trend_label", "stage"]).to_dict("records")
    assert records == [
        {
            "trend_label": "large_trend",
            "stage": "late",
            "top20_rows": 2,
            "hits": 1,
            "hit_rate": 0.5,
        },
        {
            "trend_label": "mid_trend",
            "stage": "early",
            "top20_rows": 2,
            "hits": 1,
            "hit_rate": 0.5,
        },
    ]


def test_top20_stage_hit_report_errors_when_score_input_missing():
    with pytest.raises(ValueError, match="factor.stock_score_daily"):
        trend_lifecycle.build_top20_stage_hit_report(
            pd.DataFrame(),
            pd.DataFrame(
                [
                    {
                        "asset_id": "A",
                        "trade_date": "2026-01-01",
                        "trend_label": "mid_trend",
                        "stage": "early",
                    }
                ]
            ),
        )


def test_lifecycle_samples_are_diagnostic_labels_not_scoring_features():
    bars = _bars("A", [100.0 + index for index in range(0, 61)])
    segments = trend_lifecycle.compute_trend_segments_for_asset(
        "A",
        bars,
        rules=(trend_lifecycle.TrendRule("mid_trend", 60, 120, 0.40, 0.80),),
    )

    samples = trend_lifecycle.build_lifecycle_samples(segments, bars)

    assert "close" not in samples.columns
    assert "gain" not in samples.columns
    assert {"trend_label", "stage", "progress"}.issubset(samples.columns)


def test_write_trend_lifecycle_report_outputs_required_files(tmp_path: Path):
    segments = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trend_label": "mid_trend",
                "start_date": "2026-01-01",
                "peak_date": "2026-03-01",
                "start_close": 100.0,
                "peak_close": 150.0,
                "gain": 0.5,
                "duration": 40,
                "avg_amount": 50_000_000.0,
                "max_drawdown_before_peak": -0.05,
            }
        ]
    )
    lifecycle_samples = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-10", "trend_label": "mid_trend", "stage": "early"},
            {"asset_id": "A", "trade_date": "2026-01-20", "trend_label": "mid_trend", "stage": "early_mid"},
        ]
    )
    entry_success = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2026-01-10",
                "entry_success_20d": True,
                "entry_success_20d_covered": True,
                "entry_success_40d": False,
                "entry_success_40d_covered": False,
                "entry_success_60d": False,
                "entry_success_60d_covered": False,
            }
        ]
    )
    top20_report = pd.DataFrame(
        [
            {
                "trend_label": "mid_trend",
                "stage": "early",
                "top20_rows": 1,
                "hits": 1,
                "hit_rate": 1.0,
            }
        ]
    )

    paths = trend_lifecycle.write_trend_lifecycle_outputs(
        output_dir=tmp_path,
        start_date="2026-01-01",
        end_date="2026-03-31",
        segments=segments,
        lifecycle_samples=lifecycle_samples,
        entry_success=entry_success,
        top20_stage_hits=top20_report,
        diagnostics=["fundamental point-in-time coverage not implemented in phase 1"],
    )

    assert Path(paths["trend_segments"]).exists()
    assert Path(paths["lifecycle_samples"]).exists()
    assert Path(paths["entry_success_labels"]).exists()
    assert Path(paths["top20_stage_hit_report"]).exists()
    report_text = Path(paths["markdown_report"]).read_text(encoding="utf-8")
    assert "mid_trend early / early_mid samples" in report_text
    assert "entry_success_20d" in report_text
    assert "fundamental point-in-time coverage not implemented in phase 1" in report_text
