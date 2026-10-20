"""Regime daily-update machinery (M0.7 release candidate).

Staged rebuild → validation → **versioned publish**. Deliberately avoids the
"daily overwrite of all historical DB rows" design: new versions live in a
versioned directory with a movable `latest` pointer; history is only changed by
explicit, classified diff approval — never silently.

Rollback is a pointer repoint, not a data restore.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

REGIME_FILENAME = "market_regime_confirmation_daily.csv"


class RegimeValidationError(ValueError):
    """Raised when a rebuilt regime frame fails a publish-time check."""


def validate_regime_frame(
    frame: pd.DataFrame,
    *,
    required_dates: list[str] | None = None,
    expected_last: str | None = None,
) -> None:
    """Fail-closed checks before any publish. Raises RegimeValidationError."""
    if frame.empty:
        raise RegimeValidationError("regime frame is empty")
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    if dates.isna().any():
        raise RegimeValidationError("unparseable trade_date values present")
    if dates.duplicated().any():
        dupes = sorted(dates[dates.duplicated()].dt.strftime("%Y-%m-%d").unique())
        raise RegimeValidationError(f"duplicate trade_date(s): {', '.join(dupes)}")
    if not dates.is_monotonic_increasing:
        raise RegimeValidationError("trade_date values are not strictly increasing")
    if "target_exposure" not in frame.columns:
        raise RegimeValidationError("missing target_exposure column")
    exposure = pd.to_numeric(frame["target_exposure"], errors="coerce")
    if exposure.isna().any():
        bad = frame.loc[exposure.isna(), "trade_date"].astype(str).tolist()
        raise RegimeValidationError(
            f"missing/invalid target_exposure on dates: {', '.join(map(str, bad[:10]))}"
        )
    if expected_last is not None and str(dates.iloc[-1].date()) != str(expected_last):
        raise RegimeValidationError(
            f"expected last trade_date {expected_last}, got {dates.iloc[-1].date()}"
        )
    if required_dates:
        present = set(dates.dt.strftime("%Y-%m-%d"))
        missing = [d for d in required_dates if d not in present]
        if missing:
            raise RegimeValidationError(
                f"missing required regime dates: {', '.join(missing[:20])}"
            )


def diff_against_published(
    staging_path: str | Path,
    published_path: str | Path,
) -> pd.DataFrame:
    """Row-level diff of a staged rebuild vs the currently published file.

    change_kind: new_date (only in staging) | removed_date (only in published) |
    value_changed (shared date, differing non-key cells).
    """
    staging = pd.read_csv(staging_path)
    published = pd.read_csv(published_path)
    for frame in (staging, published):
        frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    merged = staging.merge(
        published,
        on="trade_date",
        how="outer",
        suffixes=("_new", "_old"),
        indicator=True,
    )
    rows: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        key = row["trade_date"]
        if row["_merge"] == "left_only":
            rows.append({"trade_date": key, "change_kind": "new_date"})
        elif row["_merge"] == "right_only":
            rows.append({"trade_date": key, "change_kind": "removed_date"})
        else:
            changed = []
            for col in staging.columns:
                if col == "trade_date":
                    continue
                new_v = row.get(f"{col}_new")
                old_v = row.get(f"{col}_old")
                if pd.isna(new_v) and pd.isna(old_v):
                    continue
                try:
                    # tolerance, not exact equality — different write vintages carry
                    # different float precision (e.g. ...480 vs ...4799999999) which
                    # is formatting noise, not a content change.
                    if abs(float(new_v) - float(old_v)) > 1e-9:
                        changed.append(col)
                except (TypeError, ValueError):
                    if str(new_v) != str(old_v):
                        changed.append(col)
            if changed:
                rows.append(
                    {"trade_date": key, "change_kind": "value_changed", "columns": ",".join(changed)}
                )
    return pd.DataFrame(rows, columns=["trade_date", "change_kind", "columns"])


def _version_dir(root: Path, version_id: str) -> Path:
    return root / version_id


def publish_versioned(
    staging_dir: str | Path,
    version_root: str | Path,
    *,
    version_id: str,
    validate: bool = True,
    required_dates: list[str] | None = None,
    expected_last: str | None = None,
) -> Path:
    """Copy staging into ``version_root/version_id`` and repoint ``latest``.

    With ``validate=True`` the regime CSV is checked first — an invalid frame
    refuses the publish and the previous ``latest`` stays untouched (fail-closed).
    """
    staging = Path(staging_dir)
    root = Path(version_root)
    regime_csv = staging / REGIME_FILENAME
    if validate:
        frame = pd.read_csv(regime_csv)
        validate_regime_frame(
            frame, required_dates=required_dates, expected_last=expected_last
        )
    version_dir = _version_dir(root, version_id)
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True)
    shutil.copy2(regime_csv, version_dir / REGIME_FILENAME)
    for extra in staging.iterdir():
        if extra.name != REGIME_FILENAME and extra.is_file():
            shutil.copy2(extra, version_dir / extra.name)
    latest = root / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(version_dir.name)
    return version_dir


def rollback_to_version(version_root: str | Path, version_id: str) -> Path:
    """Repoint ``latest`` back to a retained version — pure pointer rollback."""
    root = Path(version_root)
    target = _version_dir(root, version_id)
    if not target.exists():
        raise FileNotFoundError(f"version not retained: {version_id}")
    latest = root / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(target.name)
    return target
