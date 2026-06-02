from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.factor_config import manual_v1_config
from stock_research.trend_lifecycle import STAGE_ORDER


FACTOR_PROFILE_COLUMNS = [
    "period",
    "trend_label",
    "stage",
    "factor_name",
    "factor_group",
    "n",
    "mean",
    "median",
    "p25",
    "p75",
    "control_median",
    "median_minus_control",
]

FACTOR_STABILITY_COLUMNS = [
    "trend_label",
    "stage",
    "factor_name",
    "factor_group",
    "periods",
    "mean_diff",
    "median_abs_diff",
    "positive_periods",
    "negative_periods",
    "sign_match_rate",
    "stable",
]

CANDIDATE_RANK_COLUMNS = [
    "factor_name",
    "factor_group",
    "direction",
    "focus_stages",
    "focus_oriented_diff",
    "focus_abs_diff",
    "stability",
    "candidate_score",
    "early_median",
    "early_mid_median",
    "mid_median",
    "late_mid_median",
    "late_median",
]

STAGE_SIGNATURE_COLUMNS = [
    "trend_label",
    "stage",
    "factor_name",
    "factor_group",
    "direction",
    "periods",
    "mean_diff",
    "oriented_mean_diff",
    "median_abs_diff",
    "sign_match_rate",
    "stable",
    "signature_type",
]


def build_factor_stage_profile(
    factors: pd.DataFrame,
    lifecycle_samples: pd.DataFrame,
    *,
    trend_label: str = "mid_trend",
    period: str | None = None,
) -> pd.DataFrame:
    factor_frame = _normalize_factors(factors)
    sample_frame = _normalize_lifecycle_samples(lifecycle_samples)
    if factor_frame.empty or sample_frame.empty:
        return pd.DataFrame(columns=FACTOR_PROFILE_COLUMNS)

    sample_frame = sample_frame[sample_frame["trend_label"] == trend_label].copy()
    if sample_frame.empty:
        return pd.DataFrame(columns=FACTOR_PROFILE_COLUMNS)

    factor_frame["period"] = _period_values(factor_frame["trade_date"], period)
    sample_frame["period"] = _period_values(sample_frame["trade_date"], period)

    joined = factor_frame.merge(
        sample_frame[["trade_date", "asset_id", "trend_label", "stage", "period"]],
        on=["trade_date", "asset_id", "period"],
        how="inner",
    ).dropna(subset=["factor_value", "stage"])
    if joined.empty:
        return pd.DataFrame(columns=FACTOR_PROFILE_COLUMNS)

    stage_summary = (
        joined.groupby(
            ["period", "trend_label", "stage", "factor_name", "factor_group"],
            as_index=False,
        )["factor_value"]
        .agg(
            n="count",
            mean="mean",
            median="median",
            p25=lambda series: series.quantile(0.25),
            p75=lambda series: series.quantile(0.75),
        )
    )
    control = (
        factor_frame.dropna(subset=["factor_value"])
        .groupby(["period", "factor_name"], as_index=False)["factor_value"]
        .median()
        .rename(columns={"factor_value": "control_median"})
    )
    result = stage_summary.merge(control, on=["period", "factor_name"], how="left")
    result["median_minus_control"] = result["median"] - result["control_median"]
    result["n"] = result["n"].astype(int)
    return result.reindex(columns=FACTOR_PROFILE_COLUMNS).sort_values(
        ["factor_name", "stage", "period"]
    ).reset_index(drop=True)


def build_factor_stability(profile: pd.DataFrame) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=FACTOR_STABILITY_COLUMNS)

    rows: list[dict[str, Any]] = []
    frame = profile.copy()
    frame["median_minus_control"] = pd.to_numeric(
        frame["median_minus_control"],
        errors="coerce",
    )
    frame = frame.dropna(subset=["median_minus_control"])
    for keys, group in frame.groupby(
        ["trend_label", "stage", "factor_name", "factor_group"],
        sort=False,
    ):
        trend_label, stage, factor_name, factor_group = keys
        diffs = group["median_minus_control"].astype(float)
        periods = int(len(diffs))
        mean_diff = float(diffs.mean()) if periods else 0.0
        overall_sign = _sign(mean_diff)
        if overall_sign == 0:
            sign_match_rate = 0.0
        else:
            sign_match_rate = float((_sign_series(diffs) == overall_sign).mean())
        rows.append(
            {
                "trend_label": trend_label,
                "stage": stage,
                "factor_name": factor_name,
                "factor_group": factor_group,
                "periods": periods,
                "mean_diff": mean_diff,
                "median_abs_diff": float(diffs.abs().median()) if periods else 0.0,
                "positive_periods": int((diffs > 0).sum()),
                "negative_periods": int((diffs < 0).sum()),
                "sign_match_rate": sign_match_rate,
                "stable": bool(periods > 0 and sign_match_rate >= 0.67),
            }
        )
    result = pd.DataFrame(rows).reindex(columns=FACTOR_STABILITY_COLUMNS)
    if "stable" in result.columns:
        result["stable"] = result["stable"].map(bool).astype(object)
    return result.sort_values(["factor_name", "stage"]).reset_index(drop=True)


def rank_candidate_factors(
    profile: pd.DataFrame,
    stability: pd.DataFrame,
    *,
    focus_stages: tuple[str, ...] = ("early", "early_mid"),
    factor_directions: dict[str, str] | None = None,
) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=CANDIDATE_RANK_COLUMNS)
    directions = factor_directions or manual_v1_config()["factor_directions"]

    stage_medians = (
        profile.groupby(["factor_name", "factor_group", "stage"], as_index=False)["median"]
        .mean()
        .pivot_table(
            index=["factor_name", "factor_group"],
            columns="stage",
            values="median",
            aggfunc="first",
        )
        .reset_index()
    )
    focus = profile[profile["stage"].isin(focus_stages)].copy()
    if focus.empty:
        return pd.DataFrame(columns=CANDIDATE_RANK_COLUMNS)
    focus["median_minus_control"] = pd.to_numeric(
        focus["median_minus_control"],
        errors="coerce",
    )
    focus_summary = (
        focus.dropna(subset=["median_minus_control"])
        .groupby(["factor_name", "factor_group"], as_index=False)["median_minus_control"]
        .mean()
        .rename(columns={"median_minus_control": "focus_diff"})
    )
    stability_focus = stability[stability["stage"].isin(focus_stages)].copy()
    stability_summary = (
        stability_focus.groupby(["factor_name", "factor_group"], as_index=False)["sign_match_rate"]
        .mean()
        .rename(columns={"sign_match_rate": "stability"})
    )
    result = focus_summary.merge(
        stability_summary,
        on=["factor_name", "factor_group"],
        how="left",
    ).merge(stage_medians, on=["factor_name", "factor_group"], how="left")
    result["stability"] = result["stability"].fillna(0.0)
    result["direction"] = result["factor_name"].map(directions).fillna("higher")
    result["focus_oriented_diff"] = result.apply(
        lambda row: _oriented_diff(row["focus_diff"], row["direction"]),
        axis=1,
    )
    result["focus_abs_diff"] = result["focus_diff"].abs()
    result["candidate_score"] = (
        result["focus_oriented_diff"].clip(lower=0.0)
        * result["stability"]
    )
    result["focus_stages"] = ",".join(focus_stages)
    for stage in STAGE_ORDER:
        if stage not in result.columns:
            result[stage] = pd.NA
    result = result.rename(
        columns={
            "early": "early_median",
            "early_mid": "early_mid_median",
            "mid": "mid_median",
            "late_mid": "late_mid_median",
            "late": "late_median",
        }
    )
    return result.reindex(columns=CANDIDATE_RANK_COLUMNS).sort_values(
        ["candidate_score", "focus_abs_diff", "factor_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def build_stage_signatures(
    profile: pd.DataFrame,
    stability: pd.DataFrame,
    *,
    factor_directions: dict[str, str] | None = None,
    stable_only: bool = True,
) -> pd.DataFrame:
    if profile.empty or stability.empty:
        return pd.DataFrame(columns=STAGE_SIGNATURE_COLUMNS)
    directions = factor_directions or manual_v1_config()["factor_directions"]
    frame = stability.copy()
    frame["mean_diff"] = pd.to_numeric(frame["mean_diff"], errors="coerce")
    frame["median_abs_diff"] = pd.to_numeric(frame["median_abs_diff"], errors="coerce")
    frame["sign_match_rate"] = pd.to_numeric(frame["sign_match_rate"], errors="coerce")
    frame = frame.dropna(subset=["mean_diff"])
    if stable_only and "stable" in frame.columns:
        frame = frame[frame["stable"].map(bool)]
    if frame.empty:
        return pd.DataFrame(columns=STAGE_SIGNATURE_COLUMNS)

    frame["direction"] = frame["factor_name"].map(directions).fillna("higher")
    frame["oriented_mean_diff"] = frame.apply(
        lambda row: _oriented_diff(row["mean_diff"], row["direction"]),
        axis=1,
    )
    frame["signature_type"] = frame["oriented_mean_diff"].map(
        lambda value: "positive" if value > 0 else "negative" if value < 0 else "neutral"
    )
    frame["stage_order"] = frame["stage"].map({stage: idx for idx, stage in enumerate(STAGE_ORDER)})
    result = frame.reindex(columns=STAGE_SIGNATURE_COLUMNS + ["stage_order"])
    result["stable"] = result["stable"].map(bool).astype(object)
    return result.sort_values(
        ["stage_order", "signature_type", "median_abs_diff", "factor_name"],
        ascending=[True, False, False, True],
    ).drop(columns=["stage_order"]).reset_index(drop=True)


def write_factor_profile_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    profile: pd.DataFrame,
    stability: pd.DataFrame,
    candidate_rank: pd.DataFrame,
    stage_signatures: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "factor_profile": str(path / "mid_trend_factor_profile.csv"),
        "stage_stability": str(path / "mid_trend_stage_stability.csv"),
        "candidate_rank": str(path / "mid_trend_candidate_rank.csv"),
        "stage_signatures": str(path / "mid_trend_stage_signatures.csv"),
        "markdown_report": str(path / "mid_trend_factor_report.md"),
    }
    profile.reindex(columns=FACTOR_PROFILE_COLUMNS).to_csv(paths["factor_profile"], index=False)
    stability.reindex(columns=FACTOR_STABILITY_COLUMNS).to_csv(paths["stage_stability"], index=False)
    candidate_rank.reindex(columns=CANDIDATE_RANK_COLUMNS).to_csv(
        paths["candidate_rank"],
        index=False,
    )
    stage_signatures.reindex(columns=STAGE_SIGNATURE_COLUMNS).to_csv(
        paths["stage_signatures"],
        index=False,
    )
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=str(start_date),
            end_date=str(end_date),
            profile=profile,
            stability=stability,
            candidate_rank=candidate_rank,
            stage_signatures=stage_signatures,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def run_mid_trend_factor_profile_report(
    *,
    start_date: object,
    end_date: object,
    lifecycle_samples_path: str | Path,
    factor_names: list[str] | None = None,
    period: str = "Q",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    lifecycle_path = Path(lifecycle_samples_path)
    if not lifecycle_path.exists():
        raise FileNotFoundError(f"lifecycle_samples CSV not found: {lifecycle_path}")

    lifecycle_samples = pd.read_csv(lifecycle_path)
    selected_factors = factor_names or sorted(manual_v1_config()["factor_groups"].keys())
    profile = load_factor_stage_profile_from_db(
        lifecycle_samples,
        start_date=start,
        end_date=end,
        factor_names=selected_factors,
        period=period,
        service=service,
    )
    stability = build_factor_stability(profile)
    candidate_rank = rank_candidate_factors(
        profile,
        stability,
        factor_directions=manual_v1_config()["factor_directions"],
    )
    stage_signatures = build_stage_signatures(
        profile,
        stability,
        factor_directions=manual_v1_config()["factor_directions"],
    )
    diagnostics = _diagnostics(
        lifecycle_samples=lifecycle_samples,
        profile=profile,
        candidate_rank=candidate_rank,
        factor_names=selected_factors,
    )
    output_dir = (
        Path(reports_dir)
        / f"mid_trend_factor_profile_{start.replace('-', '')}_{end.replace('-', '')}"
    )
    paths = write_factor_profile_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        profile=profile,
        stability=stability,
        candidate_rank=candidate_rank,
        stage_signatures=stage_signatures,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "profile": profile,
        "stability": stability,
        "candidate_rank": candidate_rank,
        "stage_signatures": stage_signatures,
        "diagnostics": diagnostics,
    }


def load_factor_stage_profile_from_db(
    lifecycle_samples: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    factor_names: list[str],
    period: str = "Q",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    samples = _normalize_lifecycle_samples(lifecycle_samples)
    samples = samples[
        (samples["trend_label"] == "mid_trend")
        & (samples["trade_date"] >= start_date)
        & (samples["trade_date"] <= end_date)
    ].copy()
    if samples.empty or not factor_names:
        return pd.DataFrame(columns=FACTOR_PROFILE_COLUMNS)

    samples["period"] = _period_values(samples["trade_date"], period)
    samples = samples[["trade_date", "asset_id", "trend_label", "stage", "period"]].drop_duplicates()

    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TEMP TABLE tmp_mid_trend_lifecycle_samples (
                    trade_date date NOT NULL,
                    asset_id text NOT NULL,
                    trend_label text NOT NULL,
                    stage text NOT NULL,
                    period text NOT NULL
                ) ON COMMIT DROP
                """
            )
            with cur.copy(
                """
                COPY tmp_mid_trend_lifecycle_samples (
                    trade_date, asset_id, trend_label, stage, period
                ) FROM STDIN
                """
            ) as copy:
                for row in samples.itertuples(index=False):
                    copy.write_row(row)

            cur.execute(
                f"""
                SELECT
                    s.period,
                    s.trend_label,
                    s.stage,
                    f.factor_name,
                    max(f.factor_group) AS factor_group,
                    count(*)::int AS n,
                    avg(f.factor_value::double precision) AS mean,
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY f.factor_value::double precision
                    ) AS median,
                    percentile_cont(0.25) WITHIN GROUP (
                        ORDER BY f.factor_value::double precision
                    ) AS p25,
                    percentile_cont(0.75) WITHIN GROUP (
                        ORDER BY f.factor_value::double precision
                    ) AS p75
                FROM tmp_mid_trend_lifecycle_samples s
                JOIN factor.factor_daily f
                  ON f.trade_date = s.trade_date
                 AND f.asset_id = s.asset_id
                WHERE f.factor_name = ANY(%s)
                  AND f.factor_value IS NOT NULL
                GROUP BY s.period, s.trend_label, s.stage, f.factor_name
                ORDER BY f.factor_name, s.stage, s.period
                """,
                [factor_names],
            )
            profile_rows = cur.fetchall()

            cur.execute(
                f"""
                SELECT
                    {_period_sql(period)} AS period,
                    factor_name,
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY factor_value::double precision
                    ) AS control_median
                FROM factor.factor_daily
                WHERE trade_date BETWEEN %s AND %s
                  AND factor_name = ANY(%s)
                  AND factor_value IS NOT NULL
                GROUP BY period, factor_name
                ORDER BY factor_name, period
                """,
                [start_date, end_date, factor_names],
            )
            control_rows = cur.fetchall()

    profile = pd.DataFrame(profile_rows)
    if profile.empty:
        return pd.DataFrame(columns=FACTOR_PROFILE_COLUMNS)
    control = pd.DataFrame(control_rows)
    result = profile.merge(control, on=["period", "factor_name"], how="left")
    result["median_minus_control"] = result["median"] - result["control_median"]
    result["n"] = result["n"].astype(int)
    return result.reindex(columns=FACTOR_PROFILE_COLUMNS)


def _normalize_factors(factors: pd.DataFrame) -> pd.DataFrame:
    if factors.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "factor_name", "factor_group", "factor_value"])
    frame = factors.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["factor_name"] = frame["factor_name"].astype(str)
    if "factor_group" not in frame.columns:
        frame["factor_group"] = "unknown"
    frame["factor_group"] = frame["factor_group"].fillna("unknown").astype(str)
    frame["factor_value"] = pd.to_numeric(frame["factor_value"], errors="coerce")
    return frame


def _normalize_lifecycle_samples(samples: pd.DataFrame) -> pd.DataFrame:
    if samples.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "trend_label", "stage"])
    frame = samples.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trend_label"] = frame["trend_label"].astype(str)
    frame["stage"] = frame["stage"].astype(str)
    return frame.drop_duplicates(["trade_date", "asset_id", "trend_label", "stage"])


def _period_values(trade_dates: pd.Series, period: str | None) -> pd.Series:
    if period is None:
        return pd.Series(["all"] * len(trade_dates), index=trade_dates.index)
    return pd.to_datetime(trade_dates).dt.to_period(period).astype(str)


def _period_sql(period: str | None) -> str:
    normalized = (period or "").upper()
    if not normalized:
        return "'all'"
    if normalized == "Q":
        return "to_char(trade_date, 'YYYY\"Q\"Q')"
    if normalized == "M":
        return "to_char(trade_date, 'YYYY-MM')"
    if normalized in {"A", "Y"}:
        return "to_char(trade_date, 'YYYY')"
    raise ValueError("period must be one of: Q, M, A, Y")


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _sign_series(values: pd.Series) -> pd.Series:
    return values.map(_sign)


def _oriented_diff(diff: float, direction: str) -> float:
    if str(direction).lower() == "lower":
        return -float(diff)
    return float(diff)


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    profile: pd.DataFrame,
    stability: pd.DataFrame,
    candidate_rank: pd.DataFrame,
    stage_signatures: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Mid Trend Factor Profile V1",
        "",
        f"- Period: {start_date} to {end_date}",
        "- Target: `mid_trend` lifecycle stages, with emphasis on `early` and `early_mid`.",
        "- Purpose: factor profile, candidate evaluation, and stability diagnostics only.",
        "",
        "## mid_trend early / early_mid factor candidates",
        "",
        _markdown_table(candidate_rank.head(20)),
        "",
        "## Stage Stability",
        "",
        _markdown_table(
            stability[stability["stage"].isin(["early", "early_mid"])]
            .sort_values(["sign_match_rate", "median_abs_diff"], ascending=[False, False])
            .head(20)
        ),
        "",
        "## Lifecycle Stage Signatures",
        "",
        _stage_signature_markdown(stage_signatures),
        "",
        "## Stage Profile Sample",
        "",
        _markdown_table(profile.head(30)),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by factor profile diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- Convert stable early/early_mid factors into transparent candidate score blocks.",
            "- Validate candidate enrichment with entry_success labels before portfolio backtesting.",
            "- Add point-in-time fundamental coverage once announcement-date joins are audited.",
            "",
        ]
    )
    return "\n".join(lines)


def _diagnostics(
    *,
    lifecycle_samples: pd.DataFrame,
    profile: pd.DataFrame,
    candidate_rank: pd.DataFrame,
    factor_names: list[str],
) -> list[str]:
    diagnostics = []
    mid_samples = lifecycle_samples[lifecycle_samples.get("trend_label") == "mid_trend"]
    if mid_samples.empty:
        diagnostics.append("No mid_trend lifecycle samples were available.")
    missing_factors = sorted(set(factor_names) - set(profile["factor_name"].dropna().astype(str)))
    if missing_factors:
        diagnostics.append("Missing factor profile rows: " + ",".join(missing_factors))
    if candidate_rank.empty:
        diagnostics.append("No candidate factor ranking was produced.")
    diagnostics.append(
        "Candidate ranking uses lifecycle labels and same-date factor values only; "
        "it is not a portfolio backtest."
    )
    return diagnostics


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _stage_signature_markdown(stage_signatures: pd.DataFrame) -> str:
    if stage_signatures.empty:
        return "_No rows._"
    rows = []
    for stage in STAGE_ORDER:
        stage_rows = stage_signatures[stage_signatures["stage"] == stage]
        positive = stage_rows[stage_rows["signature_type"] == "positive"].head(5)
        negative = stage_rows[stage_rows["signature_type"] == "negative"].head(5)
        rows.append(pd.concat([positive, negative], ignore_index=True))
    return _markdown_table(
        pd.concat(rows, ignore_index=True)
        .reindex(columns=STAGE_SIGNATURE_COLUMNS)
        .dropna(how="all")
    )
