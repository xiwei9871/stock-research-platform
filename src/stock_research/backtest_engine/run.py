"""Run artifacts + manifest for the unified engine.

Every input is passed explicitly; nothing is resolved from "latest" files.
Deterministic outputs (CSV/summary) are separated from run metadata
(timestamps, versions) so reruns can be compared byte-for-byte.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backtest_engine.config import (
    ENGINE_VERSION,
    MODE_REALISTIC,
    RealisticExecutionConfig,
    config_hash,
    config_payload,
)
from stock_research.backtest_engine.ledger import execute_target_weights
from stock_research.backtest_engine.metrics import summarize

DETERMINISTIC_FILES = ("equity_daily.csv", "positions_daily.csv", "trades.csv",
                       "corporate_actions.csv", "summary.json")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_and_write(
    *,
    targets_path: str | Path,
    bars_path: str | Path,
    calendar_path: str | Path,
    output_dir: str | Path,
    config: RealisticExecutionConfig,
    strategy_id: str,
    data_snapshot_id: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    targets = pd.read_csv(targets_path, dtype={"asset_id": str})
    bars = pd.read_csv(bars_path, dtype={"asset_id": str})
    calendar = pd.read_csv(calendar_path)["trade_date"].astype(str).tolist()
    result = execute_target_weights(targets, bars, calendar, config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["equity"].to_csv(out / "equity_daily.csv", index=False, float_format="%.10f")
    result["positions"].to_csv(out / "positions_daily.csv", index=False, float_format="%.10f")
    result["trades"].to_csv(out / "trades.csv", index=False, float_format="%.10f")
    result["corporate_actions"].to_csv(out / "corporate_actions.csv", index=False, float_format="%.10f")
    summary = summarize(result, initial_cash=config.initial_cash)
    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2, default=str))
    manifest = {
        "deterministic": {
            "engine_version": ENGINE_VERSION,
            "execution_mode": MODE_REALISTIC,
            "strategy_id": strategy_id,
            "config": config_payload(config),
            "config_hash": config_hash(config),
            "signal_cutoff": config.signal_cutoff,
            "inputs": {name: {"path": str(path), "sha256": sha256_file(path)}
                       for name, path in (("targets", targets_path), ("bars", bars_path),
                                          ("calendar", calendar_path))},
            "data_snapshot_id": data_snapshot_id,
            "calendar_range": [min(calendar), max(calendar)] if calendar else None,
            "coverage": {"signal_dates": int(targets["signal_date"].nunique()),
                         "assets": int(bars["asset_id"].nunique()),
                         "bar_rows": int(len(bars))},
            "limitations": limitations or [],
            "outputs": {name: sha256_file(out / name) for name in DETERMINISTIC_FILES},
        },
        "runtime": {
            "git_commit": _git_sha(),
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "platform": platform.platform(),
            "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified backtest engine POC V0.1 run")
    parser.add_argument("--targets", required=True)
    parser.add_argument("--bars", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--data-snapshot-id", required=True)
    parser.add_argument("--fill-price", default="next_open", choices=["next_open", "next_close"])
    parser.add_argument("--signal-cutoff", default="15:00")
    args = parser.parse_args(argv)
    config = RealisticExecutionConfig(fill_price=args.fill_price, signal_cutoff=args.signal_cutoff)
    manifest = run_and_write(targets_path=args.targets, bars_path=args.bars,
                             calendar_path=args.calendar, output_dir=args.output_dir,
                             config=config, strategy_id=args.strategy_id,
                             data_snapshot_id=args.data_snapshot_id)
    print(json.dumps(manifest["deterministic"]["outputs"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
