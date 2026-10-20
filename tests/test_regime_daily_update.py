from __future__ import annotations

import pandas as pd
import pytest

from stock_research.regime_daily_update import (
    RegimeValidationError,
    diff_against_published,
    publish_versioned,
    rollback_to_version,
    validate_regime_frame,
)


def _frame(dates, exposures=None):
    return pd.DataFrame(
        {
            "trade_date": dates,
            "target_exposure": exposures if exposures is not None else [1.0] * len(dates),
        }
    )


def test_validate_rejects_missing_required_date():
    frame = _frame(["2026-10-15", "2026-10-16"])
    with pytest.raises(RegimeValidationError, match="2026-10-19"):
        validate_regime_frame(
            frame,
            required_dates=["2026-10-15", "2026-10-19"],
            expected_last="2026-10-19",
        )


def test_validate_rejects_duplicate_and_nan():
    dup = _frame(["2026-10-15", "2026-10-15"])
    with pytest.raises(RegimeValidationError, match="duplicate"):
        validate_regime_frame(dup, expected_last="2026-10-15")
    nan = _frame(["2026-10-15"], exposures=[None])
    with pytest.raises(RegimeValidationError, match="target_exposure"):
        validate_regime_frame(nan, expected_last="2026-10-15")


def test_validate_rejects_stale_last_date():
    frame = _frame(["2026-10-15", "2026-10-16"])
    with pytest.raises(RegimeValidationError, match="expected last"):
        validate_regime_frame(frame, expected_last="2026-10-19")


def test_validate_passes_clean_frame():
    frame = _frame(["2026-10-15", "2026-10-16"], exposures=[0.7, 1.0])
    validate_regime_frame(frame, expected_last="2026-10-16")


def test_diff_reports_row_level_changes(tmp_path):
    published = _frame(["2026-10-15", "2026-10-16"], exposures=[1.0, 1.0])
    staging = _frame(["2026-10-15", "2026-10-16", "2026-10-19"], exposures=[1.0, 0.5, 0.7])
    pub = tmp_path / "published.csv"
    stg = tmp_path / "staging.csv"
    published.to_csv(pub, index=False)
    staging.to_csv(stg, index=False)
    diff = diff_against_published(stg, pub)
    assert set(diff["change_kind"]) == {"new_date", "value_changed"}
    assert diff.loc[diff.trade_date == "2026-10-19", "change_kind"].iloc[0] == "new_date"
    assert diff.loc[diff.trade_date == "2026-10-16", "change_kind"].iloc[0] == "value_changed"


def test_prefix_stability_detects_shared_date_changes(tmp_path):
    published = _frame(["2026-10-15"], exposures=[1.0])
    staging = _frame(["2026-10-15", "2026-10-16"], exposures=[0.9, 0.7])
    pub = tmp_path / "p.csv"
    stg = tmp_path / "s.csv"
    published.to_csv(pub, index=False)
    staging.to_csv(stg, index=False)
    diff = diff_against_published(stg, pub)
    assert (diff.change_kind == "value_changed").any()


def test_publish_versioned_and_rollback(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "market_regime_confirmation_daily.csv").write_text("trade_date,target_exposure\n2026-10-19,0.7\n")
    root = tmp_path / "versions"

    v1 = publish_versioned(staging, root, version_id="20261019")
    assert (root / "latest").resolve().name == "20261019"
    assert (v1 / "market_regime_confirmation_daily.csv").exists()

    # second publish moves pointer
    (staging / "market_regime_confirmation_daily.csv").write_text("trade_date,target_exposure\n2026-10-20,0.8\n")
    v2 = publish_versioned(staging, root, version_id="20261020")
    assert (root / "latest").resolve().name == "20261020"

    # rollback repoints to the retained version
    rollback_to_version(root, "20261019")
    assert (root / "latest").resolve().name == "20261019"


def test_publish_refuses_invalid_frame(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "market_regime_confirmation_daily.csv").write_text(
        "trade_date,target_exposure\n2026-10-19,\n"
    )
    root = tmp_path / "versions"
    with pytest.raises(RegimeValidationError):
        publish_versioned(staging, root, version_id="20261019", validate=True)
    assert not (root / "latest").exists()
