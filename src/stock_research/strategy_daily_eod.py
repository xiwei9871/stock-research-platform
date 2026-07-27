from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from stock_research.atomic_json import atomic_write_json
from stock_research.config import SETTINGS
from stock_research.data_run_manifest import (
    upsert_data_run_manifest,
    upsert_data_run_manifest_with_connection,
)
from stock_research.db import connect, fetch_all
from stock_research.factor_store import load_top_scores
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.strategy_daily_eod_store import (
    apply_strategy_daily_eod_status_schema,
    build_status_payload,
    upsert_strategy_daily_eod_status,
    upsert_strategy_daily_eod_status_with_connection,
)
from stock_research.strategy_eod_publish import publish_strategy_eod
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
    validate_publication_identity,
)
from stock_research.tech_bottleneck_evidence_workflow import (
    build_tech_bottleneck_evidence_workflow,
)


DependencyChecker = Callable[..., dict[str, Any]]
StrategyRunner = Callable[..., dict[str, Any]]
Publisher = Callable[..., dict[str, Any]]
PublicationTransaction = Callable[..., None]


DEFAULT_OUTPUT_ROOT = Path("outputs/research/strategy_daily_eod")

STRATEGY_DEPENDENCIES = {
    "lhb_shortline": ("common", "intraday"),
    "mid_trend": ("common",),
    "midtrend_artifacts": ("common",),
    "tech_bottleneck": ("common",),
}

ARTIFACT_METADATA_FILE_KEYS = {
    "artifact_path",
    "summary_path",
    "review_path",
    "equity_path",
    "positions_path",
    "trades_path",
    "detail_path",
}
ARTIFACT_METADATA_FILE_LIST_KEYS = {"report_files", "report_paths"}
ARTIFACT_METADATA_OPTIONAL_DIR_KEYS = {"reports_dir"}


def run_strategy_daily_eod(
    *,
    trade_date: str,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    dependency_checker: DependencyChecker | None = None,
    publisher: Publisher = publish_strategy_eod,
    release_root: str | Path | None = None,
    publication_transaction: PublicationTransaction | None = None,
    lhb_runner: StrategyRunner | None = None,
    mid_runner: StrategyRunner | None = None,
    tech_runner: StrategyRunner | None = None,
    midtrend_artifact_builder: StrategyRunner | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    if any(
        runner is not None
        for runner in (lhb_runner, mid_runner, tech_runner, midtrend_artifact_builder)
    ):
        raise ValueError("legacy strategy runner injection is unsupported")
    apply_strategy_daily_eod_status_schema(service=service)
    dependency_checker = dependency_checker or check_strategy_daily_eod_dependencies
    root = Path(output_root).resolve()
    allowed_release_root = (
        Path(release_root).resolve()
        if release_root is not None
        else _default_release_boundary(root)
    )
    if not _path_is_within(root, allowed_release_root):
        raise ValueError("strategy output root must be contained within release root")
    publication_transaction = publication_transaction or commit_strategy_publication
    canonical_output_dir = root / trade_date
    versions_dir = root / ".versions" / trade_date
    versions_dir.mkdir(parents=True, exist_ok=True)
    staging_name = f"strategy-eod-{trade_date}-{uuid.uuid4().hex}"
    publisher_root = versions_dir / f".{staging_name}-publisher-root"
    output_dir = versions_dir / staging_name

    dependency_check = _normalize_dependency_check(
        dependency_checker(trade_date=trade_date, service=service)
    )

    dependency_reason = _dependency_failure_reason(dependency_check)
    expected_counts = {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    manifest_entries: list[dict[str, Any]] = []
    publisher_summary: dict[str, Any] = {}
    publication_error: str | None = None
    required_manifest_errors: dict[str, str] = {}

    dependency_blocked = _dependency_check_status(dependency_check) != "success"
    if dependency_blocked:
        strategy_status, strategy_errors = _blocked_publication_status(dependency_check)
        strategy_counts = {name: 0 for name in expected_counts}
    else:
        try:
            publisher_summary = publisher(
                trade_date=trade_date,
                output_root=publisher_root,
                manifest_upsert=manifest_entries.append,
            )
            generated = publisher_root / "research" / "strategy_daily_eod" / trade_date
            if not generated.is_dir():
                raise RuntimeError(f"mature publisher did not create staged release: {generated}")
            _validate_official_publication_identities(manifest_entries)
            manifest_entries = [
                _relocate_manifest_entry(
                    entry,
                    staging=generated,
                    canonical=output_dir,
                    allowed_roots=(allowed_release_root,),
                )
                for entry in manifest_entries
            ]
            _relocate_review_manifest_paths(
                generated / "review_queue_strategy_manifest.csv",
                staging=generated,
                canonical=output_dir,
                allowed_roots=(allowed_release_root,),
            )
            os.replace(generated, output_dir)
            if not _manifest_entries_reference_root(manifest_entries, publisher_root):
                shutil.rmtree(publisher_root, ignore_errors=True)
            strategy_counts = {
                name: int((publisher_summary.get("strategy_counts") or {}).get(name, 0))
                for name in expected_counts
            }
            strategy_status = {
                name: "success" if strategy_counts[name] == expected else "failed"
                for name, expected in expected_counts.items()
            }
            strategy_status["midtrend_artifacts"] = (
                "success"
                if _midtrend_artifacts_valid(manifest_entries, staging=output_dir)
                else "failed"
            )
            strategy_errors = {
                name: f"expected 5 review rows, got {strategy_counts[name]}"
                for name in expected_counts
                if strategy_status[name] != "success"
            }
            if strategy_status["midtrend_artifacts"] != "success":
                strategy_errors["midtrend_artifacts"] = "midtrend artifact contract invalid"
            required_manifest_errors = _required_success_manifest_errors(
                manifest_entries,
                trade_date=trade_date,
                strategy_date_root=output_dir,
            )
            strategy_errors.update(required_manifest_errors)
            for module, strategy_name in {
                "strategy_lhb_shortline": "lhb_shortline",
                "strategy_mid_trend": "mid_trend",
                "strategy_tech_bottleneck": "tech_bottleneck",
            }.items():
                if module in required_manifest_errors:
                    strategy_status[strategy_name] = "failed"
        except Exception as exc:  # noqa: BLE001
            publication_error = f"{type(exc).__name__}: {exc}"
            strategy_counts = {name: 0 for name in expected_counts}
            strategy_status = {
                "lhb_shortline": "failed",
                "mid_trend": "failed",
                "midtrend_artifacts": "failed",
                "tech_bottleneck": "failed",
            }
            strategy_errors = {name: publication_error for name in strategy_status}

    review_rows = sum(strategy_counts.values())
    contract_valid = (
        not dependency_blocked
        and publication_error is None
        and strategy_counts == expected_counts
        and strategy_status.get("midtrend_artifacts") == "success"
        and publisher_summary.get("publishable") is True
        and int(publisher_summary.get("review_rows") or 0) == 15
        and (publisher_summary.get("score_audit") or {}).get("status") == "success"
        and not required_manifest_errors
        and _staged_release_valid(output_dir, trade_date=trade_date)
    )
    success_count = sum(status == "success" for status in strategy_status.values())
    final_status = "success" if contract_valid else "partial" if success_count else "failed"
    failure_output_dir = root / ".failures" / trade_date / staging_name
    persistent_output_dir = canonical_output_dir if contract_valid else failure_output_dir
    manifest_modules = list(dict.fromkeys(
        str(entry.get("module") or "") for entry in manifest_entries if entry.get("module")
    ))
    summary = {
        "trade_date": trade_date,
        "run_id": str(publisher_summary.get("run_id") or staging_name),
        "output_dir": str(persistent_output_dir),
        "dependency_check": dependency_check,
        "dependency_reason": dependency_reason,
        "strategy_status": strategy_status,
        "strategy_errors": strategy_errors,
        "midtrend_artifacts": _canonical_midtrend_artifacts(
            manifest_entries, staging=output_dir, canonical=canonical_output_dir
        ) if contract_valid else {},
        "midtrend_artifact_warnings": [],
        "review_rows": review_rows,
        "status": final_status,
        "publishable": contract_valid,
        "manifest_modules": manifest_modules,
        "score_audit": {
            "status": "success" if contract_valid else "failed",
            "strategy_counts": strategy_counts,
        },
        "error_summary": _join_errors([publication_error, *strategy_errors.values()]),
    }
    staging_summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary_path = persistent_output_dir / "strategy_eod_publish_summary.json"
    summary["summary_path"] = str(summary_path)

    status_payload = build_status_payload(
        trade_date=trade_date,
        status=summary["status"],
        dependency_check_status=_dependency_check_status(dependency_check),
        lhb_shortline_status=strategy_status["lhb_shortline"],
        mid_trend_status=strategy_status["mid_trend"],
        midtrend_artifacts_status=strategy_status["midtrend_artifacts"],
        tech_bottleneck_status=strategy_status["tech_bottleneck"],
        review_rows=review_rows,
        output_dir=str(summary["output_dir"]),
        summary_path=str(summary["summary_path"]),
        error_summary=summary["error_summary"],
    )

    if contract_valid:
        handle: AtomicPublishHandle | None = None
        try:
            canonical_entries = [
                _relocate_manifest_entry(
                    entry,
                    staging=output_dir,
                    canonical=canonical_output_dir,
                    allowed_roots=(allowed_release_root,),
                )
                for entry in manifest_entries
            ]
            _relocate_review_manifest_paths(
                output_dir / "review_queue_strategy_manifest.csv",
                staging=output_dir,
                canonical=canonical_output_dir,
                allowed_roots=(allowed_release_root,),
            )
            staging_summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            handle = begin_atomic_publish(output_dir, canonical_output_dir)
            publication_transaction(
                manifest_entries=canonical_entries,
                status_payload=status_payload,
                service=service,
            )
            handle.commit()
        except Exception as exc:  # noqa: BLE001
            rollback_failed = False
            if handle is not None:
                try:
                    handle.rollback()
                except Exception:  # noqa: BLE001
                    rollback_failed = True
                    exc = RuntimeError(f"{exc}; rollback_failure: filesystem rollback did not complete")
            summary = _failed_commit_summary(
                summary,
                error=exc,
                failure_output_dir=failure_output_dir,
            )
            _persist_failure_summary(
                summary_path=Path(summary["summary_path"]),
                summary=summary,
                output_root=root,
                trade_date=trade_date,
            )
            _best_effort_failed_status(summary, dependency_check=dependency_check, service=service)
            if rollback_failed:
                raise RuntimeError(
                    "strategy publication rollback failed; manual recovery required"
                ) from exc
            shutil.rmtree(output_dir, ignore_errors=True)
            shutil.rmtree(publisher_root, ignore_errors=True)
            return summary
    else:
        _persist_failure_summary(
            summary_path=summary_path,
            summary=summary,
            output_root=Path(output_root),
            trade_date=trade_date,
        )
        shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(publisher_root, ignore_errors=True)
        upsert_strategy_daily_eod_status(status_payload, service=service)
    return summary


def commit_strategy_publication(
    *,
    manifest_entries: list[dict[str, Any]],
    status_payload: dict[str, Any],
    service: str,
) -> None:
    with connect(service) as conn:
        for entry in manifest_entries:
            upsert_data_run_manifest_with_connection(entry, conn=conn)
        upsert_strategy_daily_eod_status_with_connection(status_payload, conn=conn)


def _validate_official_publication_identities(entries: list[dict[str, Any]]) -> None:
    modules = {
        "strategy_lhb_shortline": "lhb_shortline",
        "strategy_mid_trend": "mid_trend",
        "strategy_tech_bottleneck": "tech_bottleneck",
    }
    by_module = {
        str(entry.get("module") or ""): entry
        for entry in entries
        if str(entry.get("module") or "") in modules
        and str(entry.get("status") or "") == "success"
    }
    for module, strategy_id in modules.items():
        entry = by_module.get(module)
        if entry is None:
            raise RuntimeError(
                f"missing required success manifest: {module}; publication identity unavailable"
            )
        metadata = entry.get("metadata")
        actual = metadata.get("publication_identity") if isinstance(metadata, dict) else None
        if not isinstance(actual, Mapping):
            raise RuntimeError(f"publication identity missing: {module}")
        expected = build_publication_identity(get_publication_contract(strategy_id))
        mismatches = validate_publication_identity(actual, expected)
        if mismatches:
            raise RuntimeError(f"publication identity mismatch: {module}: {mismatches}")


def _failed_commit_summary(
    summary: dict[str, Any],
    *,
    error: Exception,
    failure_output_dir: Path,
) -> dict[str, Any]:
    failed = dict(summary)
    message = f"{type(error).__name__}: {error}"
    failed.update(
        {
            "status": "failed",
            "publishable": False,
            "output_dir": str(failure_output_dir),
            "summary_path": str(failure_output_dir / "strategy_eod_publish_summary.json"),
            "error_summary": _join_errors([summary.get("error_summary"), message]),
        }
    )
    failed["strategy_status"] = {
        name: "failed" for name in STRATEGY_DEPENDENCIES
    }
    failed["strategy_errors"] = {
        name: message for name in STRATEGY_DEPENDENCIES
    }
    return failed


def _best_effort_failed_status(
    summary: dict[str, Any],
    *,
    dependency_check: dict[str, dict[str, Any]],
    service: str,
) -> None:
    statuses = dict(summary.get("strategy_status") or {})
    payload = build_status_payload(
        trade_date=str(summary["trade_date"]),
        status="failed",
        dependency_check_status=_dependency_check_status(dependency_check),
        lhb_shortline_status=str(statuses.get("lhb_shortline") or "failed"),
        mid_trend_status=str(statuses.get("mid_trend") or "failed"),
        midtrend_artifacts_status=str(statuses.get("midtrend_artifacts") or "failed"),
        tech_bottleneck_status=str(statuses.get("tech_bottleneck") or "failed"),
        review_rows=int(summary.get("review_rows") or 0),
        output_dir=str(summary.get("output_dir") or ""),
        summary_path=str(summary.get("summary_path") or ""),
        error_summary=str(summary.get("error_summary") or ""),
    )
    try:
        upsert_strategy_daily_eod_status(payload, service=service)
    except Exception:  # noqa: BLE001
        return


class AtomicPublishHandle:
    def __init__(self, *, staging: Path, canonical: Path, mode: str, old_link: str | None = None):
        self.staging = staging
        self.canonical = canonical
        self.mode = mode
        self.old_link = old_link
        self.finished = False

    def commit(self) -> None:
        if self.finished:
            return
        self.finished = True
        try:
            if self.mode == "exchange":
                history = self.staging.parent / f"history-{uuid.uuid4().hex}"
                os.replace(self.staging, history)
                _prune_version_history(history.parent, current_target=None)
            elif self.mode == "symlink":
                _prune_version_history(self.staging.parent, current_target=self.staging)
            _fsync_directory(self.canonical.parent)
        except OSError:
            # The canonical switch and DB transaction are already committed.
            # Retaining an extra old version is safer than reporting a false rollback.
            return

    def rollback(self) -> None:
        if self.finished:
            return
        if self.mode == "first":
            os.replace(self.canonical, self.staging)
        elif self.mode == "exchange":
            _atomic_exchange_directories(self.staging, self.canonical)
        elif self.mode == "symlink":
            if self.old_link is None:
                raise RuntimeError("missing previous canonical symlink target")
            temporary = self.canonical.with_name(f".{self.canonical.name}.rollback-{uuid.uuid4().hex}")
            temporary.symlink_to(self.old_link, target_is_directory=True)
            os.replace(temporary, self.canonical)
        self.finished = True
        _fsync_directory(self.canonical.parent)


def begin_atomic_publish(staging: Path, canonical: Path) -> AtomicPublishHandle:
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if canonical.is_symlink():
        old_link = os.readlink(canonical)
        _atomic_symlink_publish(staging, canonical)
        return AtomicPublishHandle(
            staging=staging,
            canonical=canonical,
            mode="symlink",
            old_link=old_link,
        )
    if not canonical.exists():
        os.replace(staging, canonical)
        _fsync_directory(canonical.parent)
        return AtomicPublishHandle(staging=staging, canonical=canonical, mode="first")
    try:
        _atomic_exchange_directories(staging, canonical)
    except OSError as exc:
        if exc.errno not in {errno.ENOSYS, errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL)}:
            raise
        _atomic_symlink_publish(staging, canonical)
        return AtomicPublishHandle(staging=staging, canonical=canonical, mode="symlink")
    _fsync_directory(canonical.parent)
    return AtomicPublishHandle(staging=staging, canonical=canonical, mode="exchange")


def _atomic_publish_directory(staging: Path, canonical: Path) -> None:
    handle = begin_atomic_publish(staging, canonical)
    handle.commit()


def _persist_failure_summary(
    *,
    summary_path: Path,
    summary: dict[str, Any],
    output_root: Path,
    trade_date: str,
) -> None:
    failure_date_root = output_root / ".failures" / trade_date
    resolved_root = output_root.resolve()
    try:
        summary_path.parent.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError("failure summary path escapes strategy output root") from exc
    atomic_write_json(summary_path, summary)
    _prune_version_history(
        failure_date_root,
        current_target=summary_path.parent,
        retain=10,
    )


def _relocate_result_paths(
    paths: dict[str, Any],
    *,
    staging: Path,
    canonical: Path,
) -> dict[str, Any]:
    relocated: dict[str, Any] = {}
    for key, value in paths.items():
        candidate = Path(str(value))
        try:
            relative = candidate.relative_to(staging)
        except ValueError:
            relocated[key] = value
        else:
            relocated[key] = str(canonical / relative)
    return relocated


def _blocked_publication_status(
    dependency_check: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    statuses: dict[str, str] = {}
    errors: dict[str, str] = {}
    for strategy_name in STRATEGY_DEPENDENCIES:
        reason = strategy_blocked_reason(strategy_name, dependency_check)
        if reason:
            statuses[strategy_name] = "blocked"
            errors[strategy_name] = reason
        else:
            statuses[strategy_name] = "skipped"
            errors[strategy_name] = "publication skipped because another required dependency failed"
    return statuses, errors


def _staged_release_valid(staging: Path, *, trade_date: str) -> bool:
    expected_files = {
        "lhb_shortline": "strategy_lhb_shortline_review.csv",
        "mid_trend": "strategy_mid_trend_review.csv",
        "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
    }
    try:
        manifest = pd.read_csv(staging / "review_queue_strategy_manifest.csv", low_memory=False)
        if len(manifest) != 15:
            return False
        for strategy_id, filename in expected_files.items():
            frame = pd.read_csv(staging / filename, low_memory=False)
            selected = manifest.loc[manifest["strategy_id"].astype(str).eq(strategy_id)]
            if not _review_frame_valid(frame, strategy_id=strategy_id, trade_date=trade_date):
                return False
            if not _review_frame_valid(selected, strategy_id=strategy_id, trade_date=trade_date):
                return False
            file_keys = set(zip(frame["rank"].astype(int), frame["asset_id"].astype(str)))
            manifest_keys = set(zip(selected["rank"].astype(int), selected["asset_id"].astype(str)))
            if file_keys != manifest_keys:
                return False
    except (FileNotFoundError, KeyError, TypeError, ValueError, pd.errors.EmptyDataError):
        return False
    return True


def _review_frame_valid(frame: pd.DataFrame, *, strategy_id: str, trade_date: str) -> bool:
    required = {"trade_date", "strategy_id", "asset_id", "rank", "review_tier"}
    if len(frame) != 5 or not required.issubset(frame.columns):
        return False
    return (
        set(frame["trade_date"].astype(str)) == {trade_date}
        and set(frame["strategy_id"].astype(str)) == {strategy_id}
        and sorted(frame["rank"].astype(int).tolist()) == [1, 2, 3, 4, 5]
        and frame["review_tier"].astype(str).eq("top5_focus").all()
        and frame["asset_id"].astype(str).str.strip().ne("").all()
        and frame["asset_id"].astype(str).nunique() == 5
    )


def _midtrend_artifacts_valid(
    entries: list[dict[str, Any]],
    *,
    staging: Path,
) -> bool:
    entry = next(
        (
            item
            for item in entries
            if item.get("module") == "strategy_mid_trend" and item.get("status") == "success"
        ),
        None,
    )
    if entry is None:
        return False
    metadata = dict(entry.get("metadata") or {})
    paths = [
        metadata.get("review_path"),
        metadata.get("equity_path"),
        metadata.get("positions_path"),
        metadata.get("trades_path"),
    ]
    if not all(paths):
        return False
    try:
        return all(_contained_existing_path(value, root=staging).is_file() for value in paths)
    except RuntimeError:
        return False


def _canonical_midtrend_artifacts(
    entries: list[dict[str, Any]],
    *,
    staging: Path,
    canonical: Path,
) -> dict[str, str]:
    entry = next(
        (item for item in entries if item.get("module") == "strategy_mid_trend"),
        {},
    )
    metadata = dict(entry.get("metadata") or {})
    return {
        key: str(canonical / _contained_existing_path(value, root=staging).relative_to(staging.resolve()))
        for key, value in metadata.items()
        if key in {"review_path", "equity_path", "positions_path", "trades_path"} and value
    }


def _contained_existing_path(value: Any, *, root: Path) -> Path:
    candidate = Path(str(value))
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"manifest path escapes staged release: {value}") from exc
    return resolved


def _relocate_manifest_entry(
    entry: dict[str, Any],
    *,
    staging: Path,
    canonical: Path,
    allowed_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    relocated = dict(entry)
    if relocated.get("artifact_path"):
        relocated["artifact_path"] = _relocate_path_value(
            relocated["artifact_path"],
            staging=staging,
            canonical=canonical,
            allowed_roots=allowed_roots,
        )
    relocated["metadata"] = _relocate_metadata_paths(
        dict(relocated.get("metadata") or {}),
        staging=staging,
        canonical=canonical,
        allowed_roots=allowed_roots,
    )
    return relocated


def _relocate_metadata_paths(
    value: Any,
    *,
    staging: Path,
    canonical: Path,
    allowed_roots: tuple[Path, ...] = (),
    path_kind: str | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            key: _relocate_metadata_paths(
                item,
                staging=staging,
                canonical=canonical,
                allowed_roots=allowed_roots,
                path_kind=(
                    "directory"
                    if key in ARTIFACT_METADATA_OPTIONAL_DIR_KEYS
                    else "file"
                    if key in ARTIFACT_METADATA_FILE_KEYS
                    or key in ARTIFACT_METADATA_FILE_LIST_KEYS
                    else None
                ),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _relocate_metadata_paths(
                item,
                staging=staging,
                canonical=canonical,
                allowed_roots=allowed_roots,
                path_kind=path_kind,
            )
            for item in value
        ]
    if path_kind and value:
        return _relocate_path_value(
            value,
            staging=staging,
            canonical=canonical,
            allowed_roots=allowed_roots,
            require_exists=path_kind == "file",
        )
    return value


def _relocate_path_value(
    value: Any,
    *,
    staging: Path,
    canonical: Path,
    allowed_roots: tuple[Path, ...] = (),
    require_exists: bool = True,
) -> str:
    candidate = Path(str(value))
    resolved = candidate.resolve() if candidate.is_absolute() else (staging / candidate).resolve()
    if require_exists and not resolved.exists():
        raise RuntimeError(f"manifest path does not exist: {value}")
    try:
        relative = resolved.relative_to(staging.resolve())
    except ValueError:
        if not any(_path_is_within(resolved, root) for root in allowed_roots):
            raise RuntimeError(f"manifest path escapes controlled publication roots: {value}")
        return str(resolved)
    return str(canonical / relative)


def _relocate_review_manifest_paths(
    manifest_path: Path,
    *,
    staging: Path,
    canonical: Path,
    allowed_roots: tuple[Path, ...] = (),
) -> None:
    frame = pd.read_csv(manifest_path, low_memory=False)
    if "artifact_path" not in frame.columns:
        return
    frame["artifact_path"] = [
        _relocate_path_value(
            value,
            staging=staging,
            canonical=canonical,
            allowed_roots=allowed_roots,
        )
        if str(value or "").strip() and str(value).lower() != "nan"
        else ""
        for value in frame["artifact_path"].tolist()
    ]
    frame.to_csv(manifest_path, index=False)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _default_release_boundary(output_root: Path) -> Path:
    if output_root.parts[-3:] == ("outputs", "research", "strategy_daily_eod"):
        return output_root.parents[2]
    return output_root


def _manifest_entries_reference_root(entries: list[dict[str, Any]], root: Path) -> bool:
    root_text = str(root.resolve())
    return any(root_text in json.dumps(entry, ensure_ascii=False) for entry in entries)


def _required_success_manifest_errors(
    entries: list[dict[str, Any]],
    *,
    trade_date: str,
    strategy_date_root: Path,
) -> dict[str, str]:
    required = {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    }
    errors: dict[str, str] = {}
    for module in required:
        candidates = [entry for entry in entries if entry.get("module") == module]
        valid = False
        for entry in candidates:
            artifact = str(entry.get("artifact_path") or "").strip()
            if (
                entry.get("status") == "success"
                and str(entry.get("trade_date") or "") == trade_date
                and str(entry.get("latest_trade_date") or "") == trade_date
                and artifact
            ):
                path = Path(artifact).resolve()
                if path.exists() and _path_is_within(path, strategy_date_root):
                    valid = True
                    break
        if not valid:
            errors[module] = f"missing required success manifest for {module} on {trade_date}"
    return errors


def _atomic_symlink_publish(staging: Path, canonical: Path) -> None:
    if canonical.exists() and not canonical.is_symlink():
        raise RuntimeError(
            "atomic symlink fallback requires canonical path migration; existing real directory preserved"
        )
    try:
        staging.resolve(strict=True).relative_to(staging.parent.parent.parent.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError("staging directory escapes version root") from exc
    temporary = canonical.with_name(f".{canonical.name}.link-{uuid.uuid4().hex}")
    relative_target = os.path.relpath(staging, canonical.parent)
    temporary.symlink_to(relative_target, target_is_directory=True)
    try:
        os.replace(temporary, canonical)
        _fsync_directory(canonical.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _prune_version_history(
    versions_root: Path,
    *,
    current_target: Path | None,
    retain: int = 3,
) -> None:
    root = versions_root.resolve(strict=True)
    current = current_target.resolve(strict=True) if current_target is not None else None
    candidates = []
    for candidate in versions_root.iterdir():
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if current is not None and resolved == current:
            continue
        if candidate.is_dir() and not candidate.is_symlink():
            candidates.append(candidate)
    candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    retained_history = max(retain - (1 if current is not None else 0), 0)
    for stale in candidates[retained_history:]:
        try:
            shutil.rmtree(stale)
        except OSError:
            continue


def _atomic_exchange_directories(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    left_b = os.fsencode(left)
    right_b = os.fsencode(right)
    if sys.platform == "darwin":
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(left_b, right_b, 0x00000002)  # RENAME_SWAP
    elif sys.platform.startswith("linux"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, left_b, -100, right_b, 0x2)  # AT_FDCWD, RENAME_EXCHANGE
    else:
        raise RuntimeError("atomic directory exchange is unsupported on this platform")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_strategy_daily_eod_dependencies(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = _fetch_one(
        service,
        """
        SELECT daily_status, minute5_status, deps_status, failed_jobs
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [trade_date],
    )
    if not rows:
        failure = {"status": "failed", "reason": "missing daily_pipeline_status"}
        return {"common": failure, "intraday": failure}
    row = rows[0]
    common_failures = []
    if str(row.get("daily_status") or "") not in {"success", "partial_success"}:
        failure = f"daily_status={row.get('daily_status')}"
        detail = _failed_job_reason(row.get("failed_jobs"), stage="daily")
        common_failures.append(f"{failure}: {detail}" if detail else failure)
    if str(row.get("deps_status") or "") != "success":
        failure = f"deps_status={row.get('deps_status')}"
        detail = _failed_job_reason(row.get("failed_jobs"), stage="deps")
        common_failures.append(f"{failure}: {detail}" if detail else failure)
    common = (
        {"status": "failed", "reason": "; ".join(common_failures)}
        if common_failures
        else {"status": "success"}
    )
    if str(row.get("minute5_status") or "") in {"success", "partial_success"}:
        intraday = {"status": "success"}
    else:
        reason = _failed_job_reason(row.get("failed_jobs"), stage="minute5")
        intraday = {
            "status": "failed",
            "reason": reason or f"minute5_status={row.get('minute5_status')}",
        }
    return {"common": common, "intraday": intraday}


def _normalize_dependency_check(check: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if "common" in check or "intraday" in check:
        return {
            "common": dict(
                check.get("common")
                or {"status": "failed", "reason": "missing common dependency status"}
            ),
            "intraday": dict(
                check.get("intraday")
                or {"status": "failed", "reason": "missing intraday dependency status"}
            ),
        }
    status = str(check.get("status") or "failed")
    normalized = {"status": status}
    if check.get("reason"):
        normalized["reason"] = str(check["reason"])
    return {"common": dict(normalized), "intraday": dict(normalized)}


def strategy_blocked_reason(
    strategy_name: str,
    dependency_check: dict[str, dict[str, Any]],
) -> str | None:
    failures = []
    for dependency_name in STRATEGY_DEPENDENCIES[strategy_name]:
        dependency = dependency_check[dependency_name]
        if dependency.get("status") != "success":
            reason = str(dependency.get("reason") or "dependency check failed")
            failures.append(f"{dependency_name}: {reason}")
    return "; ".join(failures) if failures else None


def _dependency_check_status(dependency_check: dict[str, dict[str, Any]]) -> str:
    return (
        "success"
        if all(item.get("status") == "success" for item in dependency_check.values())
        else "failed"
    )


def _dependency_failure_reason(dependency_check: dict[str, dict[str, Any]]) -> str | None:
    failures = []
    for name, item in dependency_check.items():
        if item.get("status") != "success":
            failures.append(f"{name}: {item.get('reason') or 'dependency check failed'}")
    return "; ".join(failures) if failures else None


def _failed_job_reason(value: Any, *, stage: str) -> str | None:
    jobs = value
    if isinstance(jobs, str):
        try:
            jobs = json.loads(jobs)
        except json.JSONDecodeError:
            return None
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if not isinstance(job, dict) or str(job.get("stage") or "") != stage:
            continue
        provider = str(job.get("source") or job.get("provider") or "").strip()
        error = str(job.get("error_summary") or job.get("error") or "").strip()
        reason = " ".join(part for part in (provider, error) if part)
        if reason:
            return reason
    return None


def _run_strategy(
    runner: StrategyRunner,
    *,
    trade_date: str,
    output_dir: Path,
    service: str,
) -> dict[str, Any]:
    try:
        return runner(trade_date=trade_date, output_dir=output_dir, service=service)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "review_rows": 0,
            "paths": {},
            "error_summary": f"{type(exc).__name__}: {exc}",
        }


def build_lhb_shortline_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    watchlist_path = Path(f"outputs/research/daily_lhb_shortline_watchlist_{trade_date.replace('-', '')}.csv")
    if watchlist_path.exists():
        source = pd.read_csv(watchlist_path, low_memory=False).head(5).copy()
        review = _normalize_lhb_review(source, trade_date=trade_date)
    else:
        top_scores = load_top_scores(trade_date=trade_date, score_version="manual_v1", top_n=5, service=service)
        review = _build_lhb_review_rows(top_scores, trade_date=trade_date)
    final_review_path = Path(output_dir) / "strategy_lhb_shortline_review.csv"
    review.to_csv(final_review_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(final_review_path),
            "daily_watchlist": str(watchlist_path) if watchlist_path.exists() else "",
        },
    }


def build_mid_trend_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/mid_trend_watch_funnel_detail.csv"),
            Path("outputs/research/mid_trend_watch_funnel_detail.csv"),
        ]
    )
    top_scores = load_top_scores(trade_date=trade_date, score_version="manual_v1", top_n=5, service=service)
    names = _load_asset_names([str(row.get("asset_id") or "") for row in top_scores], service=service)
    review = _build_mid_trend_review_rows(top_scores, names, trade_date=trade_date)
    if funnel_detail_path.exists():
        funnel = pd.read_csv(funnel_detail_path, low_memory=False)
        if not funnel.empty:
            shadow = build_mid_trend_shadow_top10_from_frame(
                funnel,
                top_n=5,
                trade_date=trade_date,
                output_dir=None,
            )["top10"]
            review = review.iloc[:0].copy() if review.empty else review
            if not shadow.empty:
                review = _normalize_mid_trend_review(shadow, review, trade_date=trade_date)
    review_path = Path(output_dir) / "strategy_mid_trend_review.csv"
    review.to_csv(review_path, index=False)
    positions_path = Path(output_dir) / "strategy_mid_trend_positions.csv"
    trades_path = Path(output_dir) / "strategy_mid_trend_trades.csv"
    equity_path = Path(output_dir) / "strategy_mid_trend_equity.csv"
    review.assign(position_weight=1.0 / max(len(review), 1)).to_csv(positions_path, index=False)
    review.assign(trade_action="hold").to_csv(trades_path, index=False)
    review.assign(equity=1.0).to_csv(equity_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(review_path),
            "positions": str(positions_path),
            "trades": str(trades_path),
            "equity": str(equity_path),
        },
    }


def build_midtrend_daily_review_artifacts_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    output = Path(output_dir)
    paths: dict[str, str] = {}
    warnings: list[str] = []

    v1_review = output / "strategy_mid_trend_review.csv"
    _copy_if_exists(
        v1_review,
        output / "midtrend_v1_top5_reference.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_v1_top5_reference.csv",
    )

    top10_dir = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")
    top10_holdings = top10_dir / "current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv"
    top10_trades = top10_dir / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"
    _write_trade_date_slice(
        top10_holdings,
        output / "midtrend_v2_top10_candidate.csv",
        trade_date=trade_date,
        paths=paths,
        warnings=warnings,
        key="midtrend_v2_top10_candidate.csv",
    )
    _write_trade_date_slice(
        top10_trades,
        output / "midtrend_v2_top10_trade_changes.csv",
        trade_date=trade_date,
        paths=paths,
        warnings=warnings,
        key="midtrend_v2_top10_trade_changes.csv",
    )

    canonical_dir = Path("outputs/research/midtrend_pit_attribution_canonical_and_daily_review_lite_v1_20260628")
    _copy_if_exists(
        canonical_dir / "bad_buy_fundamental_attribution_pit_canonical.csv",
        output / "midtrend_canonical_pit_review_labels.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_canonical_pit_review_labels.csv",
    )
    _copy_if_exists(
        canonical_dir / "midtrend_post_exit_watch_daily_review_lite.json",
        output / "midtrend_post_exit_watch_daily_review_lite.json",
        paths=paths,
        warnings=warnings,
        key="midtrend_post_exit_watch_daily_review_lite.json",
    )
    _copy_if_exists(
        canonical_dir / "midtrend_post_exit_watch_daily_review_lite.csv",
        output / "midtrend_post_exit_watch_daily_review_lite.csv",
        paths=paths,
        warnings=warnings,
        key="midtrend_post_exit_watch_daily_review_lite.csv",
    )

    manifest = pd.DataFrame(
        [{"artifact_name": key, "path": value} for key, value in sorted(paths.items())]
    )
    manifest_path = output / "midtrend_daily_review_artifacts_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    paths["midtrend_daily_review_artifacts_manifest.csv"] = str(manifest_path)
    return {"status": "success", "review_rows": 0, "paths": paths, "warnings": warnings}


def build_tech_bottleneck_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    asset_queue_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/tech_bottleneck_daily_candidates.csv"),
            Path("outputs/research/strategy_lab_tech_bottleneck/2026-06-18/tech_bottleneck_daily_candidates.csv"),
        ]
    )
    evidence_detail_path = _default_or_existing_path(
        [
            Path(f"outputs/research/strategy_daily_eod/{trade_date}/tech_bottleneck_candidate_source/strict_153_st_only_financial_state_candidates.csv"),
            Path("outputs/research/tech_bottleneck_evidence_workflow_20260619_mainbiz_final/tech_bottleneck_evidence_adjusted_candidates.csv"),
        ]
    )
    candidates = pd.read_csv(asset_queue_path, low_memory=False) if asset_queue_path.exists() else pd.DataFrame()
    evidence = pd.read_csv(evidence_detail_path, low_memory=False) if evidence_detail_path.exists() else pd.DataFrame()
    result = build_tech_bottleneck_evidence_workflow(
        asset_queue=candidates,
        evidence_detail=evidence,
        trade_date=trade_date,
        top_n=5,
        output_dir=output_dir,
    )
    review = result["adjusted_candidates"].head(5).copy()
    if review.empty:
        review = pd.DataFrame(columns=["trade_date", "asset_id", "rank", "bottleneck_score", "score_total"])
    review_path = Path(output_dir) / "strategy_tech_bottleneck_review.csv"
    if "rank" not in review.columns:
        review["rank"] = range(1, len(review) + 1)
    review["trade_date"] = trade_date
    review.to_csv(review_path, index=False)
    return {
        "status": "success",
        "review_rows": int(len(review)),
        "paths": {
            "review": str(review_path),
            "positions": result["paths"].get("adjusted_candidates", ""),
        },
    }


def _join_errors(values: list[Any]) -> str | None:
    messages = [str(value).strip() for value in values if str(value or "").strip()]
    return "; ".join(messages) if messages else None


def _fetch_one(service: str, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _default_or_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _copy_if_exists(
    source: Path,
    target: Path,
    *,
    paths: dict[str, str],
    warnings: list[str],
    key: str,
) -> None:
    if not source.exists():
        warnings.append(f"missing:{source}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    paths[key] = str(target)


def _write_trade_date_slice(
    source: Path,
    target: Path,
    *,
    trade_date: str,
    paths: dict[str, str],
    warnings: list[str],
    key: str,
) -> None:
    if not source.exists():
        warnings.append(f"missing:{source}")
        return
    frame = pd.read_csv(source, low_memory=False)
    if "trade_date" in frame.columns:
        frame = frame[frame["trade_date"].astype(str).eq(trade_date)].copy()
    if frame.empty:
        warnings.append(f"empty_for_trade_date:{source}:{trade_date}")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    paths[key] = str(target)


def _load_asset_names(asset_ids: list[str], *, service: str) -> dict[str, str]:
    cleaned = [asset_id for asset_id in asset_ids if asset_id]
    if not cleaned:
        return {}
    rows = _fetch_one(
        service,
        """
        SELECT asset_id, name
        FROM core.asset_master
        WHERE asset_id = ANY(%s)
        """,
        [cleaned],
    )
    return {str(row.get("asset_id") or ""): str(row.get("name") or "") for row in rows}


def _build_mid_trend_review_rows(
    top_scores: list[dict[str, Any]],
    names_by_asset: dict[str, str],
    *,
    trade_date: str,
) -> pd.DataFrame:
    rows = []
    for idx, row in enumerate(top_scores[:5], start=1):
        asset_id = str(row.get("asset_id") or "")
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "rank": idx,
                "score_total": row.get("score_total"),
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "daily EOD review from stock_score_daily",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_mid_trend",
                "source_rank": idx,
                "review_tier": "top5_focus",
                "stock_name": names_by_asset.get(asset_id, ""),
            }
        )
    return pd.DataFrame(rows)


def _build_lhb_review_rows(
    top_scores: list[dict[str, Any]],
    *,
    trade_date: str,
) -> pd.DataFrame:
    rows = []
    for idx, row in enumerate(top_scores[:5], start=1):
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": str(row.get("asset_id") or ""),
                "rank": idx,
                "score_total": row.get("score_total"),
                "score_source": "stock_score_daily",
                "score_explanation": "daily EOD fallback from stock_score_daily",
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_lhb_shortline",
                "source_rank": idx,
                "review_tier": "top5_focus",
            }
        )
    return pd.DataFrame(rows)


def _normalize_lhb_review(frame: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    result = frame.copy()
    asset_id = (
        result["asset_id"].astype(str)
        if "asset_id" in result.columns
        else result.get("ts_code", pd.Series(dtype=object)).astype(str)
    )
    review = pd.DataFrame(
        {
            "trade_date": trade_date,
            "asset_id": asset_id,
            "rank": range(1, len(result) + 1),
            "score_total": 20.0,
            "score_source": "lhb_shortline_watchlist",
            "score_explanation": "daily LHB shortline watchlist rank",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "strategy_run_id": f"strategy-eod-{trade_date}-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_lhb_shortline",
            "source_rank": range(1, len(result) + 1),
            "review_tier": "top5_focus",
        }
    )
    return review


def _normalize_mid_trend_review(
    shadow: pd.DataFrame,
    review: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    if shadow.empty:
        return review
    source = shadow.head(5).copy()
    if review.empty:
        normalized = pd.DataFrame(
            {
                "trade_date": trade_date,
                "asset_id": source["asset_id"].astype(str).tolist(),
                "rank": range(1, len(source) + 1),
                "score_total": pd.to_numeric(source.get("mid_trend_funnel_score"), errors="coerce"),
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "mid trend shadow top list",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_mid_trend",
                "source_rank": range(1, len(source) + 1),
                "review_tier": "top5_focus",
            }
        )
        return normalized
    normalized = review.head(len(source)).copy()
    normalized["asset_id"] = source["asset_id"].astype(str).tolist()
    normalized["rank"] = range(1, len(normalized) + 1)
    normalized["source_rank"] = normalized["rank"]
    return normalized


def _write_review_manifest(output_dir: Path) -> dict[str, int]:
    frames: list[pd.DataFrame] = []
    strategy_files = {
        "lhb_shortline": "strategy_lhb_shortline_review.csv",
        "mid_trend": "strategy_mid_trend_review.csv",
        "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
    }
    counts: dict[str, int] = {}
    for strategy_id, filename in strategy_files.items():
        path = output_dir / filename
        if path.exists() and path.stat().st_size > 0:
            frame = pd.read_csv(path, low_memory=False)
            frame["strategy_id"] = strategy_id
            frame["artifact_path"] = filename
            frames.append(frame)
            counts[strategy_id] = int(len(frame))
        else:
            counts[strategy_id] = 0
    legacy_manifest_path = output_dir / "strategy_daily_eod_review_manifest.csv"
    manifest_path = output_dir / "review_queue_strategy_manifest.csv"
    if not frames:
        empty = pd.DataFrame()
        empty.to_csv(legacy_manifest_path, index=False)
        empty.to_csv(manifest_path, index=False)
        return counts
    manifest = pd.concat(frames, ignore_index=True, sort=False)
    manifest.to_csv(legacy_manifest_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    return counts
