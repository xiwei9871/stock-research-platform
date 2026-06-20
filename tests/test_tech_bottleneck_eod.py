from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from stock_research.cli import build_parser
from stock_research.cli import main_for_args
from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod, run_tech_bottleneck_eod_from_frames


def test_tech_bottleneck_eod_writes_artifacts_and_manifest_entries(tmp_path: Path) -> None:
    entries: list[dict[str, object]] = []

    result = run_tech_bottleneck_eod_from_frames(
        base_candidates=_base_candidates(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        run_id="strategy-eod-20250108-local",
        output_dir=tmp_path,
        manifest_upsert=entries.append,
        candidate_source_path=tmp_path / "strict_base_candidates.csv",
    )

    expected_paths = {
        "snapshot_path": tmp_path / "tech_bottleneck_daily_candidates.csv",
        "review_path": tmp_path / "strategy_tech_bottleneck_review.csv",
        "equity_path": tmp_path / "strategy_tech_bottleneck_equity.csv",
        "positions_path": tmp_path / "strategy_tech_bottleneck_positions.csv",
        "trades_path": tmp_path / "strategy_tech_bottleneck_trades.csv",
    }
    for key, path in expected_paths.items():
        assert Path(result[key]) == path
        assert path.exists()
    review = pd.read_csv(expected_paths["review_path"])
    assert set(review["trade_date"]) == {"2025-01-08"}

    assert {entry["module"] for entry in entries} == {"tech_bottleneck_candidates", "strategy_tech_bottleneck"}
    candidate_entry = next(entry for entry in entries if entry["module"] == "tech_bottleneck_candidates")
    strategy_entry = next(entry for entry in entries if entry["module"] == "strategy_tech_bottleneck")

    assert candidate_entry["status"] == "success"
    assert candidate_entry["latest_trade_date"] == "2025-01-08"
    assert candidate_entry["row_count"] == result["candidate_rows"]
    assert candidate_entry["asset_count"] == 2
    assert candidate_entry["artifact_path"] == str(expected_paths["snapshot_path"])
    assert candidate_entry["metadata"]["candidate_snapshot_latest_date"] == "2025-01-08"
    assert candidate_entry["metadata"]["candidate_source"] == str(tmp_path / "strict_base_candidates.csv")
    assert candidate_entry["metadata"]["candidate_snapshot_row_count"] == result["candidate_rows"]

    assert strategy_entry["status"] == "success"
    assert strategy_entry["latest_trade_date"] == "2025-01-08"
    assert strategy_entry["artifact_path"] == str(expected_paths["review_path"])
    assert strategy_entry["metadata"]["candidate_snapshot_latest_date"] == "2025-01-08"
    assert strategy_entry["metadata"]["candidate_source"] == str(tmp_path / "strict_base_candidates.csv")
    assert strategy_entry["metadata"]["candidate_snapshot_row_count"] == result["candidate_rows"]
    assert strategy_entry["metadata"]["output_paths"] == {key: str(path) for key, path in expected_paths.items()}
    assert strategy_entry["metadata"]["summary"]["top_n"] == 5
    assert strategy_entry["metadata"]["summary"]["frequency"] == "biweekly"
    assert strategy_entry["metadata"]["summary"]["protection_name"] == "rank_exit_top10_1d"
    assert strategy_entry["metadata"]["summary"]["transaction_cost_bps"] == 10.0
    assert strategy_entry["metadata"]["summary"]["max_position_weight"] == 0.2
    assert strategy_entry["metadata"]["config"]["transaction_cost_bps"] == 10.0
    assert strategy_entry["metadata"]["config"]["max_position_weight"] == 0.2
    assert result["review_rows"] >= 1


def test_tech_bottleneck_eod_equity_file_is_anchored_to_initial_equity(tmp_path: Path) -> None:
    entries: list[dict[str, object]] = []

    run_tech_bottleneck_eod_from_frames(
        base_candidates=_base_candidates(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        run_id="strategy-eod-20250108-local",
        output_dir=tmp_path,
        manifest_upsert=entries.append,
        candidate_source_path=tmp_path / "strict_base_candidates.csv",
    )

    equity = pd.read_csv(tmp_path / "strategy_tech_bottleneck_equity.csv")
    summary = next(entry for entry in entries if entry["module"] == "strategy_tech_bottleneck")["metadata"]["summary"]
    assert equity.iloc[0]["equity"] == pytest.approx(1.0)
    assert equity.iloc[0]["drawdown"] == pytest.approx(0.0)
    assert equity.iloc[-1]["equity"] == pytest.approx(summary["final_equity"])
    assert equity.iloc[-1]["equity"] - 1.0 == pytest.approx(summary["total_return"])


def test_tech_bottleneck_eod_idempotent_rerun_rewrites_same_manifest_ids(tmp_path: Path) -> None:
    first_entries: list[dict[str, object]] = []
    second_entries: list[dict[str, object]] = []

    for entries in (first_entries, second_entries):
        run_tech_bottleneck_eod_from_frames(
            base_candidates=_base_candidates(),
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            run_id="strategy-eod-20250108-local",
            output_dir=tmp_path,
            manifest_upsert=entries.append,
            candidate_source_path=tmp_path / "strict_base_candidates.csv",
        )

    assert [entry["manifest_id"] for entry in first_entries] == [
        entry["manifest_id"] for entry in second_entries
    ]
    assert pd.read_csv(tmp_path / "tech_bottleneck_daily_candidates.csv").shape[0] == first_entries[0]["row_count"]


def test_file_backed_runner_rejects_missing_freshness_before_artifacts(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "strict_base_candidates.csv"
    frame = _base_candidates().drop(columns=["source_latest_trade_date", "data_as_of_date"])
    frame.to_csv(source, index=False)

    monkeypatch.setattr("stock_research.tech_bottleneck_eod._load_prices", _unexpected_loader)

    with pytest.raises(ValueError, match="freshness metadata missing"):
        run_tech_bottleneck_eod(
            start_date="2025-01-01",
            end_date="2025-01-08",
            output_dir=tmp_path / "out",
            base_candidates_path=source,
        )

    assert not (tmp_path / "out").exists()


def test_file_backed_runner_rejects_stale_freshness_before_artifacts(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "strict_base_candidates.csv"
    frame = _base_candidates()
    frame["source_latest_trade_date"] = "2025-01-07"
    frame.to_csv(source, index=False)

    monkeypatch.setattr("stock_research.tech_bottleneck_eod._load_prices", _unexpected_loader)

    with pytest.raises(ValueError, match="base candidate source is stale"):
        run_tech_bottleneck_eod(
            start_date="2025-01-01",
            end_date="2025-01-08",
            output_dir=tmp_path / "out",
            base_candidates_path=source,
        )

    assert not (tmp_path / "out").exists()


def test_cli_parser_requires_base_candidates_path() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "run-tech-bottleneck-eod",
            "--end-date",
            "2025-01-08",
            "--output-dir",
            "outputs/eod",
            "--base-candidates-path",
            "outputs/strict_candidates.csv",
        ]
    )
    assert args.start_date == "2025-01-01"
    assert args.base_candidates_path == "outputs/strict_candidates.csv"

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "run-tech-bottleneck-eod",
                "--end-date",
                "2025-01-08",
                "--output-dir",
                "outputs/eod",
            ]
        )


def test_cli_main_dispatches_tech_bottleneck_eod(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(**kwargs):
        calls.append({key: str(value) for key, value in kwargs.items()})
        return {"ok": True}

    monkeypatch.setattr("stock_research.tech_bottleneck_eod.run_tech_bottleneck_eod", fake_run)

    main_for_args(
        [
            "run-tech-bottleneck-eod",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-08",
            "--output-dir",
            str(tmp_path / "out"),
            "--base-candidates-path",
            str(tmp_path / "strict_candidates.csv"),
        ]
    )

    assert calls == [
        {
            "start_date": "2025-01-01",
            "end_date": "2025-01-08",
            "output_dir": str(tmp_path / "out"),
            "base_candidates_path": str(tmp_path / "strict_candidates.csv"),
        }
    ]


def _unexpected_loader(*args, **kwargs) -> pd.DataFrame:
    raise AssertionError("price loader must not run before base candidate freshness validation")


def _base_candidates() -> pd.DataFrame:
    rows = [
        {
            "asset_id": "A",
            "stock_name": "Alpha",
            "first_hit_date": "2025-01-01",
            "candidate_trade_date": "2025-01-01",
            "hit_count_as_of_date": 8,
            "primary_chain_id": "chain-a",
            "primary_chain_name": "Compute",
            "matched_bottleneck_dimensions": "capacity",
            "financial_as_of_date": "2025-01-01",
            "technical_as_of_date": "2025-01-01",
            "source_latest_trade_date": "2025-01-08",
            "data_as_of_date": "2025-01-08",
            "filter_decision": "pass",
        },
        {
            "asset_id": "B",
            "stock_name": "Beta",
            "first_hit_date": "2025-01-01",
            "candidate_trade_date": "2025-01-01",
            "hit_count_as_of_date": 7,
            "primary_chain_id": "chain-b",
            "primary_chain_name": "Chips",
            "matched_bottleneck_dimensions": "supply",
            "financial_as_of_date": "2025-01-01",
            "technical_as_of_date": "2025-01-01",
            "source_latest_trade_date": "2025-01-08",
            "data_as_of_date": "2025-01-08",
            "filter_decision": "pass",
        },
    ]
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for offset, trade_date in enumerate(pd.date_range("2025-01-01", periods=8, freq="D")):
        for asset_id, base in {"A": 10.0, "B": 20.0}.items():
            close = base + offset
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def _market_exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": trade_date.strftime("%Y-%m-%d"), "target_exposure": 1.0}
            for trade_date in pd.date_range("2025-01-01", periods=8, freq="D")
        ]
    )
