from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECTOR_PRIORITY_PATH = PROJECT_ROOT / "config" / "yanbaoke_sector_priority.csv"


def load_sector_priority_config(path: str | Path | None = None) -> pd.DataFrame:
    config_path = Path(path) if path is not None else DEFAULT_SECTOR_PRIORITY_PATH
    frame = pd.read_csv(config_path, dtype="string").fillna("")
    required = {"sector_name", "match_keywords", "sector_priority", "sector_quota_bucket", "pilot_quota"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"sector priority config missing columns: {sorted(missing)}")
    frame["pilot_quota"] = pd.to_numeric(frame["pilot_quota"], errors="coerce").fillna(0).astype(int)
    return frame
