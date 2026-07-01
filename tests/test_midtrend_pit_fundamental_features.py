from pathlib import Path

import pandas as pd
from stock_research import cli


def test_build_pit_feature_row_respects_announcement_cutoff() -> None:
    from stock_research.midtrend_pit_fundamental_features import build_pit_feature_row

    row = build_pit_feature_row(
        trade_date="2025-01-10",
        asset_id="A",
        indicator={"report_period": "2024-12-31", "announcement_date": "2025-01-09", "roe": 0.15, "revenue_yoy": 0.2, "np_yoy": 0.3, "ocf_to_np": 1.1, "gross_margin": 0.4, "net_margin": 0.1, "debt_ratio": 0.3},
        income={"report_period": "2024-12-31", "announcement_date": "2025-01-09", "revenue": 100.0, "net_profit": 20.0},
        balance={"report_period": "2024-12-31", "announcement_date": "2025-01-09", "total_equity": 80.0},
        cash_flow=None,
        share_capital={"announcement_date": "2025-01-09", "total_share": 10.0},
        close_price=12.0,
    )
    assert row["lookahead_violation_flag"] is False
    assert row["pit_valid_flag"] is True
    assert row["report_disclosure_date"] == "2025-01-09"


def test_missing_fundamental_data_stays_unknown() -> None:
    from stock_research.midtrend_pit_fundamental_features import assign_fundamental_buckets_from_pit

    out = assign_fundamental_buckets_from_pit(pd.Series({"revenue_growth_yoy": None, "profit_growth_yoy": None, "roe": None}))
    assert out["fundamental_quality_bucket"] == "quality_unknown"


def test_run_pit_feature_builder_writes_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_pit_fundamental_features import (
        run_midtrend_build_pit_fundamental_features_from_frames,
    )

    universe = pd.DataFrame(
        [
            {"trade_date": "2025-01-10", "asset_id": "A", "industry_name": "Tech"},
            {"trade_date": "2025-01-10", "asset_id": "B", "industry_name": "Tech"},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-10", "asset_id": "A", "close": 12.0},
            {"trade_date": "2025-01-10", "asset_id": "B", "close": 8.0},
        ]
    )
    indicators = {
        ("2025-01-10", "A"): {"report_period": "2024-12-31", "announcement_date": "2025-01-09", "roe": 0.15, "revenue_yoy": 0.2, "np_yoy": 0.3, "ocf_to_np": 1.2, "gross_margin": 0.4, "net_margin": 0.1, "debt_ratio": 0.3},
    }
    shares = {
        ("2025-01-10", "A"): {"announcement_date": "2025-01-09", "total_share": 10.0, "float_share": 8.0},
    }
    result = run_midtrend_build_pit_fundamental_features_from_frames(
        universe=universe,
        prices=prices,
        indicator_rows=indicators,
        income_rows={},
        balance_rows={},
        cash_flow_rows={},
        share_capital_rows=shares,
        output_dir=tmp_path,
    )
    assert (tmp_path / "midtrend_pit_fundamental_features.csv").exists()
    assert (tmp_path / "fundamental_data_coverage_audit.csv").exists()
    assert result["pit_features"].shape[0] == 2


def test_cli_parser_and_dispatch_pit_builder(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-build-pit-fundamental-features",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-12",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-build-pit-fundamental-features"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_pit_fundamental_features.run_midtrend_build_pit_fundamental_features_cli",
        _fake_runner,
    )

    rc = cli.main(
        [
            "midtrend-build-pit-fundamental-features",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-12",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
