from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd


EXCLUDED_TITLE_PATTERN = re.compile(
    r"晨会|晨报|早报|日报|每日|morning\s+meeting|daily\s+(?:report|summary)",
    re.IGNORECASE,
)


def coverage_target(priority_score: float) -> int:
    score = float(priority_score or 0)
    if score >= 90:
        return 3
    if score >= 80:
        return 2
    return 1


def company_download_cap(row: pd.Series | dict[str, object]) -> int:
    priority = float(row.get("priority_score") or 0)
    theme_count = int(row.get("theme_count") or 0)
    return 5 if priority >= 90 and theme_count > 1 else 4


def build_allocation_slots(
    companies: pd.DataFrame,
    *,
    primary_limit: int = 394,
    multi_theme_limit: int = 28,
    scarcity_limit: int = 28,
    reserve_release_limit: int = 24,
) -> pd.DataFrame:
    frame = companies.copy().fillna(0)
    frame["priority_score"] = pd.to_numeric(frame["priority_score"], errors="coerce").fillna(0.0)
    frame["pdf120"] = pd.to_numeric(frame["pdf120"], errors="coerce").fillna(0).astype(int)
    frame["theme_count"] = pd.to_numeric(frame["theme_count"], errors="coerce").fillna(0).astype(int)
    frame["scarcity_score"] = pd.to_numeric(frame.get("scarcity_score", 0), errors="coerce").fillna(0.0)
    frame["company_cap"] = frame.apply(company_download_cap, axis=1)
    frame["coverage_target"] = frame["priority_score"].map(coverage_target)
    frame["primary_deficit"] = (frame["coverage_target"] - frame["pdf120"]).clip(lower=0)
    frame = frame.sort_values(
        ["priority_score", "primary_deficit", "scarcity_score", "ts_code"],
        ascending=[False, False, False, True],
    )

    slots: list[dict[str, object]] = []
    allocated: dict[str, int] = {}

    def add_slot(row: pd.Series, bucket: str) -> bool:
        code = str(row["ts_code"])
        if allocated.get(code, 0) >= int(row["company_cap"]):
            return False
        slots.append(
            {
                "slot_id": len(slots) + 1,
                "ts_code": code,
                "allocation_bucket": bucket,
                "priority_score": float(row["priority_score"]),
            }
        )
        allocated[code] = allocated.get(code, 0) + 1
        return True

    for _, row in frame.iterrows():
        for _ in range(int(row["primary_deficit"])):
            if len([slot for slot in slots if slot["allocation_bucket"] == "primary_coverage"]) >= primary_limit:
                break
            add_slot(row, "primary_coverage")

    def fill_extra(bucket: str, limit: int, candidates: pd.DataFrame) -> None:
        added = 0
        while added < limit:
            progressed = False
            for _, row in candidates.iterrows():
                if added >= limit:
                    break
                if add_slot(row, bucket):
                    added += 1
                    progressed = True
            if not progressed:
                break

    multi_theme = frame[frame["theme_count"] > 1].sort_values(
        ["priority_score", "scarcity_score", "ts_code"], ascending=[False, False, True]
    )
    fill_extra("multi_theme_depth", multi_theme_limit, multi_theme)
    scarcity = frame.sort_values(
        ["scarcity_score", "priority_score", "pdf120", "ts_code"],
        ascending=[False, False, True, True],
    )
    fill_extra("theme_scarcity", scarcity_limit, scarcity)
    reserve = frame.sort_values(
        ["priority_score", "theme_count", "scarcity_score", "pdf120", "ts_code"],
        ascending=[False, False, False, True, True],
    )
    fill_extra("reserve_release", reserve_release_limit, reserve)
    return pd.DataFrame(slots)


def normalize_report_title(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def existing_readable_report_keys(
    rows: Iterable[dict[str, object]],
) -> set[tuple[str, str, str, str]]:
    return {
        (
            str(row.get("ts_code") or ""),
            str(row.get("broker") or ""),
            str(row.get("publish_date") or "")[:10],
            normalize_report_title(row.get("report_title")),
        )
        for row in rows
        if bool(row.get("has_pdf"))
    }


def load_downloaded_manifest_uuids(paths: Iterable[str | Path]) -> set[str]:
    uuids: set[str] = set()
    for value in paths:
        path = Path(value)
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            frame = pd.read_csv(path, dtype=object).fillna("")
        except (OSError, pd.errors.ParserError):
            continue
        if "uuid" not in frame.columns:
            continue
        statuses = frame.get("status", pd.Series("", index=frame.index)).astype(str)
        values = frame.loc[statuses.eq("downloaded"), "uuid"].astype(str).str.strip()
        uuids.update(value for value in values if value and value.lower() != "nan")
    return uuids


def select_download_queue(
    candidates: pd.DataFrame,
    slots: pd.DataFrame,
    *,
    target_successes: int = 474,
    candidate_pool_size: int = 550,
    broker_cap: int = 71,
    existing_uuids: Iterable[str] = (),
    existing_report_keys: Iterable[tuple[str, str, str, str]] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = candidates.copy().fillna("")
    if frame.empty:
        return frame, frame
    frame["uuid"] = frame["uuid"].astype(str).str.strip()
    frame = frame[frame["uuid"].ne("") & ~frame["uuid"].isin(set(existing_uuids))].copy()
    frame = frame[~frame["report_title"].astype(str).str.contains(EXCLUDED_TITLE_PATTERN, na=False)].copy()
    frame["normalized_title"] = frame["report_title"].map(normalize_report_title)
    existing_keys = set(existing_report_keys)
    frame = frame[
        ~frame.apply(
            lambda row: (
                str(row["ts_code"]),
                str(row.get("broker") or ""),
                str(row.get("publish_date") or "")[:10],
                str(row["normalized_title"]),
            )
            in existing_keys,
            axis=1,
        )
    ].copy()
    frame = frame.drop_duplicates(subset=["uuid"], keep="first")
    frame = frame.drop_duplicates(
        subset=["ts_code", "broker", "publish_date", "normalized_title"], keep="first"
    )
    frame["candidate_score"] = pd.to_numeric(frame.get("candidate_score", 0), errors="coerce").fillna(0.0)
    frame = frame.sort_values(
        ["candidate_score", "publish_date", "uuid"], ascending=[False, False, True]
    ).reset_index(drop=True)

    selected_rows: list[dict[str, object]] = []
    used: set[str] = set()
    broker_counts: dict[str, int] = {}
    company_counts: dict[str, int] = {}

    def take(row: pd.Series, bucket: str) -> bool:
        uuid = str(row["uuid"])
        code = str(row["ts_code"])
        broker = str(row.get("broker") or "")
        company_cap = int(row.get("company_cap") or 5)
        if uuid in used or company_counts.get(code, 0) >= company_cap:
            return False
        if broker and broker_counts.get(broker, 0) >= broker_cap:
            return False
        record = row.to_dict()
        record["allocation_bucket"] = bucket
        selected_rows.append(record)
        used.add(uuid)
        company_counts[code] = company_counts.get(code, 0) + 1
        if broker:
            broker_counts[broker] = broker_counts.get(broker, 0) + 1
        return True

    for slot in slots.to_dict("records"):
        if len(selected_rows) >= target_successes:
            break
        matching = frame[(frame["ts_code"] == slot["ts_code"]) & ~frame["uuid"].isin(used)]
        for _, row in matching.iterrows():
            if take(row, str(slot["allocation_bucket"])):
                break

    if len(selected_rows) < target_successes:
        for _, row in frame.iterrows():
            if len(selected_rows) >= target_successes:
                break
            take(row, "dynamic_backfill")

    selected = pd.DataFrame(selected_rows)
    replacement_rows: list[dict[str, object]] = []
    for _, row in frame[~frame["uuid"].isin(used)].iterrows():
        if len(selected_rows) + len(replacement_rows) >= candidate_pool_size:
            break
        replacement_rows.append(row.to_dict())
    replacements = pd.DataFrame(replacement_rows, columns=frame.columns)
    return selected.reset_index(drop=True), replacements.reset_index(drop=True)
