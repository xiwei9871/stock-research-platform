from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import signal
import stat
import subprocess
import time
from typing import Any

from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
from stock_research.eod_auto_repair_models import RepairStatus


REPORT_SCHEMA_VERSION = "playwright-eod-browser-acceptance/v1"
CANDIDATE_SCHEMA_VERSION = "playwright-eod-candidate-snapshot/v1"
PREVIOUS_SCHEMA_VERSION = "playwright-eod-previous-publications/v1"
OFFICIAL_STRATEGY_IDS = ("lhb_shortline", "mid_trend", "tech_bottleneck")
REQUIRED_GATE_IDS = (
    "candidate-consistency",
    "publication-consistency",
    "runtime-deep-links",
)
REPAIRABLE_FAILURE_CLASSES = frozenset(
    {"presentation_runtime", "critical_request_transport", "stale_cache"}
)
NONREPAIRABLE_FAILURE_CLASSES = frozenset(
    {
        "api_ui_mismatch",
        "publication_identity",
        "date_regression",
        "return_unit",
        "contract_mismatch",
        "publish_rollback",
        "unknown",
        "infrastructure",
    }
)
DEFAULT_DASHBOARD_PORT = 5176
DEFAULT_API_PORT = 8768
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_BROWSER_PROJECT = "chromium-desktop"
_VERIFIED_RESULT_PROVENANCE = object()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DASHBOARD_ROOT = _REPO_ROOT / "dashboard"
_REPORT_KEYS = frozenset(
    {
        "schemaVersion",
        "runId",
        "tradeDate",
        "revision",
        "startedAt",
        "endedAt",
        "durationSeconds",
        "contractOnly",
        "status",
        "tests",
        "failures",
        "attachments",
        "candidateSnapshot",
        "candidateSnapshotSha256",
    }
)
_CANDIDATE_KEYS = frozenset({"schemaVersion", "tradeDate", "publications"})
_PUBLICATION_KEYS = frozenset(
    {
        "strategyId",
        "tradeDate",
        "totalReturnPct",
        "contractId",
        "publishId",
        "publishStartedAt",
        "artifactVersion",
    }
)
_PREVIOUS_KEYS = frozenset({"schemaVersion", "publications"})
_CANDIDATE_IDENTITY_REQUIRED_KEYS = frozenset(
    {"strategyId", "tradeDate", "publishId", "publishStartedAt"}
)
_CANDIDATE_IDENTITY_ALLOWED_KEYS = _PUBLICATION_KEYS | {"runId"}
_GATE_PATTERN = re.compile(r"(?:^|\s)@eod-gate-([a-z0-9_-]+)(?=\s|$)")
_REPORTED_TEST_KEYS = frozenset(
    {
        "testId",
        "title",
        "projectName",
        "retry",
        "status",
        "durationMs",
        "failures",
        "attachments",
        "severity",
        "attemptHistory",
    }
)
_ATTEMPT_KEYS = frozenset(
    {"retry", "status", "durationMs", "failures", "attachments"}
)
_TEST_ATTACHMENT_REQUIRED_KEYS = frozenset({"name", "contentType"})
_TOP_ATTACHMENT_REQUIRED_KEYS = frozenset(
    {"test", "retry", "name", "contentType"}
)
_ATTACHMENT_OPTIONAL_KEYS = frozenset({"path"})
_PLAYWRIGHT_TEST_STATUSES = frozenset(
    {"passed", "failed", "timedOut", "interrupted", "skipped"}
)


class BrowserAcceptanceError(RuntimeError):
    """Fail-closed browser acceptance contract or infrastructure error."""


class FrozenJsonDict(dict[str, object]):
    """A JSON-serializable mapping that rejects mutation at every exposed layer."""

    def _immutable(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("browser acceptance snapshot is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, _memo: dict[int, object]) -> FrozenJsonDict:
        return self


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenJsonDict(
            {str(key): _freeze_json(nested) for key, nested in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _empty_snapshot() -> FrozenJsonDict:
    return FrozenJsonDict()


@dataclass(frozen=True)
class BrowserAcceptanceAttempt:
    attempt_number: int
    status: RepairStatus
    duration_seconds: float
    exit_code: int | None = None
    failure_classes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    artifact_paths: tuple[str, ...] = ()
    snapshot: Mapping[str, object] = field(default_factory=_empty_snapshot)
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, Mapping):
            raise TypeError("browser acceptance snapshot must be a mapping")
        object.__setattr__(self, "snapshot", _freeze_json(self.snapshot))


@dataclass(frozen=True)
class BrowserAcceptanceResult:
    status: RepairStatus
    trade_date: str
    run_id: str
    duration_seconds: float
    application_revision: str = ""
    browser_project: str = DEFAULT_BROWSER_PROJECT
    report_schema_version: str = REPORT_SCHEMA_VERSION
    failure_classes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    artifact_paths: tuple[str, ...] = ()
    snapshot: Mapping[str, object] = field(default_factory=_empty_snapshot)
    started_at: str = ""
    ended_at: str = ""
    message: str = ""
    attempts: tuple[BrowserAcceptanceAttempt, ...] = ()
    _verified_provenance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, Mapping):
            raise TypeError("browser acceptance snapshot must be a mapping")
        object.__setattr__(self, "snapshot", _freeze_json(self.snapshot))


def _mark_result_verified(
    result: BrowserAcceptanceResult,
) -> BrowserAcceptanceResult:
    object.__setattr__(
        result,
        "_verified_provenance",
        _VERIFIED_RESULT_PROVENANCE,
    )
    return result


def write_browser_acceptance_manifest(
    result: BrowserAcceptanceResult,
    *,
    manifest_upsert: Callable[[dict[str, Any]], Any] = upsert_data_run_manifest,
) -> dict[str, Any]:
    status = result.status.value
    if status not in {"success", "degraded", "failed"}:
        raise ValueError(
            "browser acceptance manifest status must be success, degraded, or failed"
        )
    if (
        result.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}
        and result._verified_provenance is not _VERIFIED_RESULT_PROVENANCE
    ):
        raise _error("browser_acceptance_result_unverified")
    trade_date = _required_date(
        _required_string(result.trade_date, "browser_acceptance_trade_date_invalid"),
        "browser_acceptance_trade_date_invalid",
    )
    run_id = _required_string(result.run_id, "browser_acceptance_run_id_invalid")
    revision = _required_string(
        result.application_revision, "browser_acceptance_revision_invalid"
    )
    project = _required_string(
        result.browser_project, "browser_acceptance_browser_project_invalid"
    )
    if result.report_schema_version != REPORT_SCHEMA_VERSION:
        raise _error("browser_acceptance_report_schema_version")
    snapshot_for_metadata: Mapping[str, object] = result.snapshot
    if result.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        snapshot_for_metadata = _validate_candidate_snapshot(
            json.loads(_stable_json(result.snapshot)),
            trade_date,
        )
    artifacts = list(result.artifact_paths)
    entry = build_manifest_entry(
        run_id=run_id,
        run_date=trade_date,
        trade_date=trade_date,
        module="dashboard_browser_acceptance",
        source="eod_browser_acceptance",
        tier="tier1",
        status=status,
        started_at=result.started_at or None,
        ended_at=result.ended_at or None,
        duration_seconds=result.duration_seconds,
        warnings=list(result.warnings),
        error_message=result.message if result.status == RepairStatus.FAILED else "",
        artifact_path=artifacts[0] if artifacts else None,
        code_version=revision,
        metadata={
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "application_revision": revision,
            "browser_project": project,
            "duration_seconds": result.duration_seconds,
            "failure_classes": list(result.failure_classes),
            "warnings": list(result.warnings),
            "candidate_snapshot": snapshot_for_metadata,
            "artifact_paths": artifacts,
        },
    )
    if result.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        validate_browser_acceptance_manifest_entry(
            entry,
            expected_trade_date=trade_date,
        )
    manifest_upsert(entry)
    return entry


def _error(code: str, detail: object | None = None) -> BrowserAcceptanceError:
    return BrowserAcceptanceError(f"{code}:{detail}" if detail is not None else code)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _required_object(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(code)
    return value


def _required_list(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(code)
    return value


def _required_string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _error(code)
    return value


def _required_date(value: object, code: str) -> str:
    if isinstance(value, datetime):
        raise _error(code)
    text = value.isoformat() if isinstance(value, date) else _required_string(value, code)
    try:
        if date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except ValueError as exc:
        raise _error(code) from exc
    return text


def _required_timestamp(value: object, code: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _required_string(value, code)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _error(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(code)
    return parsed.astimezone(timezone.utc).isoformat()


def _required_number(value: object, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(code)
    number = float(value)
    if not math.isfinite(number):
        raise _error(code)
    return number


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], code: str) -> None:
    if frozenset(value) != expected:
        raise _error(code)


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _validate_candidate_snapshot(value: object, expected_trade_date: str) -> dict[str, object]:
    snapshot = _required_object(value, "browser_acceptance_candidate_snapshot_invalid")
    _exact_keys(snapshot, _CANDIDATE_KEYS, "browser_acceptance_candidate_snapshot_schema")
    if snapshot.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        raise _error("browser_acceptance_candidate_snapshot_schema_version")
    trade_date = _required_date(
        snapshot.get("tradeDate"), "browser_acceptance_candidate_snapshot_trade_date"
    )
    if trade_date != expected_trade_date:
        raise _error(
            "browser_acceptance_candidate_snapshot_trade_date_mismatch",
            f"{trade_date}:{expected_trade_date}",
        )
    publications = _required_list(
        snapshot.get("publications"), "browser_acceptance_candidate_snapshot_publications"
    )
    if len(publications) != len(OFFICIAL_STRATEGY_IDS):
        raise _error("browser_acceptance_candidate_snapshot_publication_count")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(publications):
        publication = _required_object(
            raw, f"browser_acceptance_candidate_snapshot_publication:{index}"
        )
        _exact_keys(
            publication,
            _PUBLICATION_KEYS,
            f"browser_acceptance_candidate_snapshot_publication_schema:{index}",
        )
        strategy_id = _required_string(
            publication.get("strategyId"),
            f"browser_acceptance_candidate_snapshot_strategy_id:{index}",
        )
        if strategy_id not in OFFICIAL_STRATEGY_IDS or strategy_id in seen:
            raise _error("browser_acceptance_candidate_snapshot_strategy_inventory", strategy_id)
        seen.add(strategy_id)
        publication_date = _required_date(
            publication.get("tradeDate"),
            f"browser_acceptance_candidate_snapshot_publication_trade_date:{strategy_id}",
        )
        if publication_date != expected_trade_date:
            raise _error(
                "browser_acceptance_candidate_snapshot_publication_trade_date_mismatch",
                strategy_id,
            )
        normalized.append(
            {
                "strategyId": strategy_id,
                "tradeDate": publication_date,
                "totalReturnPct": _required_number(
                    publication.get("totalReturnPct"),
                    f"browser_acceptance_candidate_snapshot_total_return:{strategy_id}",
                ),
                "contractId": _required_string(
                    publication.get("contractId"),
                    f"browser_acceptance_candidate_snapshot_contract_id:{strategy_id}",
                ),
                "publishId": _required_string(
                    publication.get("publishId"),
                    f"browser_acceptance_candidate_snapshot_publish_id:{strategy_id}",
                ),
                "publishStartedAt": _required_timestamp(
                    publication.get("publishStartedAt"),
                    f"browser_acceptance_candidate_snapshot_publish_started_at:{strategy_id}",
                ),
                "artifactVersion": _required_string(
                    publication.get("artifactVersion"),
                    f"browser_acceptance_candidate_snapshot_artifact_version:{strategy_id}",
                ),
            }
        )
    if seen != set(OFFICIAL_STRATEGY_IDS):
        raise _error("browser_acceptance_candidate_snapshot_strategy_inventory")
    return {
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "tradeDate": trade_date,
        "publications": normalized,
    }


def _manifest_number(value: object, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise _error(code)
    number = float(value)
    if not math.isfinite(number):
        raise _error(code)
    return number


def _manifest_string_list(value: object, code: str) -> list[str]:
    return [
        _required_string(item, f"{code}:{index}")
        for index, item in enumerate(_required_list(value, code))
    ]


def _manifest_artifact_paths(value: object) -> list[str]:
    paths = _manifest_string_list(value, "browser_acceptance_manifest_artifact_paths")
    if not paths:
        raise _error("browser_acceptance_manifest_artifact_paths_empty")
    for path in paths:
        windows_path = PureWindowsPath(path)
        if not (PurePosixPath(path).is_absolute() or windows_path.is_absolute()):
            _safe_report_artifact_path(path)
    if len(set(paths)) != len(paths):
        raise _error("browser_acceptance_manifest_artifact_paths_duplicate")
    return paths


def validate_browser_acceptance_manifest_entry(
    value: Mapping[str, object],
    *,
    expected_trade_date: str,
) -> dict[str, object]:
    row = dict(value)
    if row.get("module") != "dashboard_browser_acceptance":
        raise _error("browser_acceptance_manifest_module")
    if row.get("source") != "eod_browser_acceptance":
        raise _error("browser_acceptance_manifest_source")
    status = _required_string(row.get("status"), "browser_acceptance_manifest_status")
    if status not in {"success", "degraded"}:
        raise _error("browser_acceptance_manifest_status", status)
    trade_date = _required_date(
        row.get("trade_date"), "browser_acceptance_manifest_trade_date"
    )
    if trade_date != expected_trade_date:
        raise _error(
            "browser_acceptance_manifest_trade_date_mismatch",
            f"{trade_date}:{expected_trade_date}",
        )
    run_id = _required_string(row.get("run_id"), "browser_acceptance_manifest_run_id")
    metadata = _required_object(
        row.get("metadata"), "browser_acceptance_manifest_metadata"
    )
    if metadata.get("report_schema_version") != REPORT_SCHEMA_VERSION:
        raise _error("browser_acceptance_manifest_report_schema_version")
    if _required_string(
        metadata.get("run_id"), "browser_acceptance_manifest_metadata_run_id"
    ) != run_id:
        raise _error("browser_acceptance_manifest_run_id_mismatch")
    revision = _required_string(
        metadata.get("application_revision"),
        "browser_acceptance_manifest_application_revision",
    )
    if _required_string(
        row.get("code_version"), "browser_acceptance_manifest_code_version"
    ) != revision:
        raise _error("browser_acceptance_manifest_revision_mismatch")
    project = _required_string(
        metadata.get("browser_project"), "browser_acceptance_manifest_browser_project"
    )
    if project != DEFAULT_BROWSER_PROJECT:
        raise _error("browser_acceptance_manifest_browser_project", project)
    duration = _manifest_number(
        metadata.get("duration_seconds"), "browser_acceptance_manifest_duration"
    )
    row_duration = _manifest_number(
        row.get("duration_seconds"), "browser_acceptance_manifest_row_duration"
    )
    if duration < 0 or row_duration < 0 or duration != row_duration:
        raise _error("browser_acceptance_manifest_duration_mismatch")
    failure_classes = _manifest_string_list(
        metadata.get("failure_classes"),
        "browser_acceptance_manifest_failure_classes",
    )
    warnings = _manifest_string_list(
        metadata.get("warnings"), "browser_acceptance_manifest_warnings"
    )
    row_warnings = _manifest_string_list(
        row.get("warnings"), "browser_acceptance_manifest_row_warnings"
    )
    if warnings != row_warnings:
        raise _error("browser_acceptance_manifest_warnings_mismatch")
    warning_count = row.get("warning_count")
    if (
        isinstance(warning_count, bool)
        or not isinstance(warning_count, int)
        or warning_count != len(warnings)
    ):
        raise _error("browser_acceptance_manifest_warning_count")
    if failure_classes:
        raise _error("browser_acceptance_manifest_publishable_failure_classes")
    if status == "success" and warnings:
        raise _error("browser_acceptance_manifest_success_warnings")
    if status == "degraded" and not warnings:
        raise _error("browser_acceptance_manifest_degraded_warnings_missing")
    error_message = row.get("error_message")
    if error_message is not None and error_message != "":
        raise _error("browser_acceptance_manifest_publishable_error_message")
    snapshot = _validate_candidate_snapshot(
        metadata.get("candidate_snapshot"),
        expected_trade_date,
    )
    artifact_paths = _manifest_artifact_paths(metadata.get("artifact_paths"))
    if row.get("artifact_path") != artifact_paths[0]:
        raise _error("browser_acceptance_manifest_artifact_path_mismatch")
    return {
        "status": status,
        "trade_date": trade_date,
        "run_id": run_id,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "application_revision": revision,
        "browser_project": project,
        "duration_seconds": duration,
        "failure_classes": failure_classes,
        "warnings": warnings,
        "candidate_snapshot": snapshot,
        "artifact_paths": artifact_paths,
    }


def _validate_previous_publications_payload(value: object) -> dict[str, object]:
    root = _required_object(value, "previous_publication_schema")
    _exact_keys(root, _PREVIOUS_KEYS, "previous_publication_schema")
    if root.get("schemaVersion") != PREVIOUS_SCHEMA_VERSION:
        raise _error("previous_publication_schema_version")
    publications = _required_list(root.get("publications"), "previous_publication_publications")
    if len(publications) != len(OFFICIAL_STRATEGY_IDS):
        raise _error("previous_publication_count")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(publications):
        publication = _required_object(raw, f"previous_publication_invalid:{index}")
        _exact_keys(publication, _PUBLICATION_KEYS, f"previous_publication_schema:{index}")
        strategy_id = _required_string(
            publication.get("strategyId"), f"previous_publication_strategy_id:{index}"
        )
        if strategy_id not in OFFICIAL_STRATEGY_IDS or strategy_id in seen:
            raise _error("previous_publication_strategy_inventory", strategy_id)
        seen.add(strategy_id)
        normalized.append(
            {
                "strategyId": strategy_id,
                "tradeDate": _required_date(
                    publication.get("tradeDate"),
                    f"previous_publication_trade_date:{strategy_id}",
                ),
                "totalReturnPct": _required_number(
                    publication.get("totalReturnPct"),
                    f"previous_publication_total_return_pct:{strategy_id}",
                ),
                "contractId": _required_string(
                    publication.get("contractId"),
                    f"previous_publication_contract_id:{strategy_id}",
                ),
                "publishId": _required_string(
                    publication.get("publishId"),
                    f"previous_publication_publish_id:{strategy_id}",
                ),
                "publishStartedAt": _required_timestamp(
                    publication.get("publishStartedAt"),
                    f"previous_publication_publish_started_at:{strategy_id}",
                ),
                "artifactVersion": _required_string(
                    publication.get("artifactVersion"),
                    f"previous_publication_artifact_version:{strategy_id}",
                ),
            }
        )
    if seen != set(OFFICIAL_STRATEGY_IDS):
        raise _error("previous_publication_strategy_inventory")
    return {"schemaVersion": PREVIOUS_SCHEMA_VERSION, "publications": normalized}


def _validate_candidate_publication_identities(
    value: object,
    *,
    expected_trade_date: str | None = None,
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        raise _error("previous_publication_candidate_identity_schema")
    if len(value) != len(OFFICIAL_STRATEGY_IDS):
        raise _error("previous_publication_candidate_identity_count")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        candidate = _required_object(
            raw, f"previous_publication_candidate_identity:{index}"
        )
        keys = frozenset(candidate)
        if (
            not _CANDIDATE_IDENTITY_REQUIRED_KEYS.issubset(keys)
            or not keys.issubset(_CANDIDATE_IDENTITY_ALLOWED_KEYS)
        ):
            raise _error("previous_publication_candidate_identity_schema", index)
        strategy_id = _required_string(
            candidate.get("strategyId"),
            f"previous_publication_candidate_strategy_id:{index}",
        )
        if strategy_id not in OFFICIAL_STRATEGY_IDS or strategy_id in seen:
            raise _error("previous_publication_candidate_strategy_inventory", strategy_id)
        seen.add(strategy_id)
        trade_date = _required_date(
            candidate.get("tradeDate"),
            f"previous_publication_candidate_trade_date:{strategy_id}",
        )
        if expected_trade_date is not None and trade_date != expected_trade_date:
            raise _error(
                "previous_publication_candidate_trade_date_mismatch", strategy_id
            )
        item = {
            "strategyId": strategy_id,
            "tradeDate": trade_date,
            "publishId": _required_string(
                candidate.get("publishId"),
                f"previous_publication_candidate_publish_id:{strategy_id}",
            ),
            "publishStartedAt": _required_timestamp(
                candidate.get("publishStartedAt"),
                f"previous_publication_candidate_publish_started_at:{strategy_id}",
            ),
        }
        if "runId" in candidate:
            item["runId"] = _required_string(
                candidate.get("runId"),
                f"previous_publication_candidate_run_id:{strategy_id}",
            )
        if "totalReturnPct" in candidate:
            item["totalReturnPct"] = _required_number(
                candidate.get("totalReturnPct"),
                f"previous_publication_candidate_total_return_pct:{strategy_id}",
            )
        for optional_key in ("contractId", "artifactVersion"):
            if optional_key in candidate:
                item[optional_key] = _required_string(
                    candidate.get(optional_key),
                    f"previous_publication_candidate_{optional_key}:{strategy_id}",
                )
        normalized.append(item)
    if seen != set(OFFICIAL_STRATEGY_IDS):
        raise _error("previous_publication_candidate_strategy_inventory")
    return tuple(
        next(item for item in normalized if item["strategyId"] == strategy_id)
        for strategy_id in OFFICIAL_STRATEGY_IDS
    )


def _safe_report_artifact_path(value: object) -> str:
    text = _required_string(value, "browser_acceptance_artifact_path_invalid")
    windows_path = PureWindowsPath(text)
    if (
        PurePosixPath(text).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    ):
        raise _error("browser_acceptance_artifact_path_absolute")
    normalized = text.replace("\\", "/")
    posix_parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in posix_parts):
        raise _error("browser_acceptance_artifact_path_traversal")
    return str(PurePosixPath(*posix_parts))


def _required_nonnegative_int(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(code)
    return value


def _validate_attachment(
    value: object,
    *,
    required_keys: frozenset[str],
    code: str,
) -> dict[str, object]:
    attachment = _required_object(value, code)
    keys = frozenset(attachment)
    if not required_keys.issubset(keys) or not keys.issubset(
        required_keys | _ATTACHMENT_OPTIONAL_KEYS
    ):
        raise _error(f"{code}_schema")
    normalized: dict[str, object] = {}
    for key in sorted(required_keys):
        if key == "retry":
            normalized[key] = _required_nonnegative_int(
                attachment.get(key), f"{code}_{key}"
            )
        else:
            normalized[key] = _required_string(
                attachment.get(key), f"{code}_{key}"
            )
    if "path" in attachment:
        normalized["path"] = _safe_report_artifact_path(attachment["path"])
    return normalized


def _validate_failures(value: object, code: str) -> list[str]:
    return [
        _required_string(item, code)
        for item in _required_list(value, f"{code}_list")
    ]


def _validate_report_tests(tests: Sequence[object]) -> None:
    seen_test_ids: set[str] = set()
    for index, raw in enumerate(tests):
        test = _required_object(raw, f"browser_acceptance_test_invalid:{index}")
        _exact_keys(test, _REPORTED_TEST_KEYS, f"browser_acceptance_test_schema:{index}")
        test_id = _required_string(test.get("testId"), f"browser_acceptance_test_id:{index}")
        if test_id in seen_test_ids:
            raise _error("browser_acceptance_test_id_duplicate", test_id)
        seen_test_ids.add(test_id)
        _required_string(test.get("title"), f"browser_acceptance_test_title:{index}")
        _required_string(
            test.get("projectName"), f"browser_acceptance_test_project_name:{index}"
        )
        retry = _required_nonnegative_int(
            test.get("retry"), f"browser_acceptance_test_retry:{index}"
        )
        status = _required_string(
            test.get("status"), f"browser_acceptance_test_status:{index}"
        )
        if status not in _PLAYWRIGHT_TEST_STATUSES:
            raise _error("browser_acceptance_test_status_invalid", status)
        duration = _required_number(
            test.get("durationMs"), f"browser_acceptance_test_duration:{index}"
        )
        if duration < 0:
            raise _error("browser_acceptance_test_duration_negative", index)
        failures = _validate_failures(
            test.get("failures"), f"browser_acceptance_test_failure:{index}"
        )
        if status in {"passed", "skipped"} and failures:
            raise _error("browser_acceptance_test_passed_with_failures", test_id)
        if status in {"failed", "timedOut", "interrupted"} and not failures:
            raise _error("browser_acceptance_test_failed_without_failures", test_id)
        attachments = [
            _validate_attachment(
                attachment,
                required_keys=_TEST_ATTACHMENT_REQUIRED_KEYS,
                code=f"browser_acceptance_test_attachment:{index}:{attachment_index}",
            )
            for attachment_index, attachment in enumerate(
                _required_list(
                    test.get("attachments"),
                    f"browser_acceptance_test_attachments:{index}",
                )
            )
        ]
        _required_string(test.get("severity"), f"browser_acceptance_test_severity:{index}")
        history = _required_list(
            test.get("attemptHistory"),
            f"browser_acceptance_test_attempt_history:{index}",
        )
        if not history:
            raise _error("browser_acceptance_attempt_history_missing", test_id)
        normalized_history: list[dict[str, object]] = []
        seen_retries: set[int] = set()
        for attempt_index, raw_attempt in enumerate(history):
            attempt = _required_object(
                raw_attempt,
                f"browser_acceptance_attempt_history_invalid:{index}:{attempt_index}",
            )
            _exact_keys(
                attempt,
                _ATTEMPT_KEYS,
                f"browser_acceptance_attempt_history_schema:{index}:{attempt_index}",
            )
            attempt_retry = _required_nonnegative_int(
                attempt.get("retry"),
                f"browser_acceptance_attempt_history_retry:{index}:{attempt_index}",
            )
            if attempt_retry in seen_retries:
                raise _error("browser_acceptance_attempt_history_retry_duplicate", test_id)
            seen_retries.add(attempt_retry)
            attempt_status = _required_string(
                attempt.get("status"),
                f"browser_acceptance_attempt_history_status:{index}:{attempt_index}",
            )
            if attempt_status not in _PLAYWRIGHT_TEST_STATUSES:
                raise _error("browser_acceptance_attempt_history_status_invalid", attempt_status)
            attempt_duration = _required_number(
                attempt.get("durationMs"),
                f"browser_acceptance_attempt_history_duration:{index}:{attempt_index}",
            )
            if attempt_duration < 0:
                raise _error("browser_acceptance_attempt_history_duration_negative", test_id)
            attempt_failures = _validate_failures(
                attempt.get("failures"),
                f"browser_acceptance_attempt_history_failure:{index}:{attempt_index}",
            )
            if attempt_status in {"passed", "skipped"} and attempt_failures:
                raise _error("browser_acceptance_attempt_history_passed_with_failures", test_id)
            if attempt_status in {"failed", "timedOut", "interrupted"} and not attempt_failures:
                raise _error("browser_acceptance_attempt_history_failed_without_failures", test_id)
            attempt_attachments = [
                _validate_attachment(
                    attachment,
                    required_keys=_TEST_ATTACHMENT_REQUIRED_KEYS,
                    code=(
                        f"browser_acceptance_attempt_history_attachment:"
                        f"{index}:{attempt_index}:{attachment_index}"
                    ),
                )
                for attachment_index, attachment in enumerate(
                    _required_list(
                        attempt.get("attachments"),
                        f"browser_acceptance_attempt_history_attachments:{index}:{attempt_index}",
                    )
                )
            ]
            normalized_history.append(
                {
                    "retry": attempt_retry,
                    "status": attempt_status,
                    "durationMs": attempt_duration,
                    "failures": attempt_failures,
                    "attachments": attempt_attachments,
                }
            )
        if [item["retry"] for item in normalized_history] != sorted(seen_retries):
            raise _error("browser_acceptance_attempt_history_order", test_id)
        final_attempt = normalized_history[-1]
        if final_attempt != {
            "retry": retry,
            "status": status,
            "durationMs": duration,
            "failures": failures,
            "attachments": attachments,
        }:
            raise _error("browser_acceptance_attempt_history_final_mismatch", test_id)


def _test_failure_messages(tests: Sequence[object]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    for index, raw in enumerate(tests):
        test = _required_object(raw, f"browser_acceptance_test_invalid:{index}")
        title = _required_string(test.get("title"), f"browser_acceptance_test_title:{index}")
        status = _required_string(test.get("status"), f"browser_acceptance_test_status:{index}")
        severity = _required_string(
            test.get("severity"), f"browser_acceptance_test_severity:{index}"
        )
        failures = [
            _required_string(item, f"browser_acceptance_test_failure:{index}")
            for item in _required_list(
                test.get("failures"), f"browser_acceptance_test_failures:{index}"
            )
        ]
        if status not in {"passed", "failed", "timedOut", "interrupted", "skipped"}:
            raise _error("browser_acceptance_test_status_invalid", status)
        if status not in {"failed", "timedOut", "interrupted"}:
            continue
        messages = failures or [f"{title}: {status}"]
        if severity == "warning":
            warnings.extend(messages)
        else:
            blocking.extend(f"{title}: {message}" for message in messages)
    return blocking, warnings


def _validate_gate_inventory(tests: Sequence[object]) -> dict[str, str]:
    claims: dict[str, list[str]] = {gate_id: [] for gate_id in REQUIRED_GATE_IDS}
    test_claim_counts: dict[str, int] = {}
    status_by_test_id: dict[str, str] = {}
    for index, raw in enumerate(tests):
        test = _required_object(raw, f"browser_acceptance_test_invalid:{index}")
        test_id = _required_string(test.get("testId"), f"browser_acceptance_test_id:{index}")
        title = _required_string(test.get("title"), f"browser_acceptance_test_title:{index}")
        status_by_test_id[test_id] = _required_string(
            test.get("status"), f"browser_acceptance_test_status:{index}"
        )
        gate_ids = _GATE_PATTERN.findall(title)
        test_claim_counts[test_id] = len(gate_ids)
        for gate_id in gate_ids:
            if gate_id not in claims:
                raise _error("browser_acceptance_gate_unknown", gate_id)
            claims[gate_id].append(test_id)
    if any(count > 1 for count in test_claim_counts.values()):
        raise _error("browser_acceptance_gate_test_claims_multiple")
    if any(len(test_ids) != 1 for test_ids in claims.values()):
        raise _error("browser_acceptance_gate_inventory")
    if len({test_ids[0] for test_ids in claims.values()}) != len(REQUIRED_GATE_IDS):
        raise _error("browser_acceptance_gate_ids_not_distinct")
    return {
        gate_id: status_by_test_id[test_ids[0]]
        for gate_id, test_ids in claims.items()
    }


def classify_browser_failures(failures: Iterable[str] | Mapping[str, object]) -> tuple[str, ...]:
    if isinstance(failures, Mapping):
        raw_failures = failures.get("failures", [])
        values = raw_failures if isinstance(raw_failures, list) else [raw_failures]
    else:
        values = list(failures)
    classes: set[str] = set()
    for value in values:
        text = str(value).lower()
        matches: set[str] = set()
        candidate_gate = "eod-gate-candidate-consistency" in text
        publication_gate = "eod-gate-publication-consistency" in text
        runtime_gate = "eod-gate-runtime-deep-links" in text
        if candidate_gate:
            matches.add("api_ui_mismatch")
        if publication_gate:
            matches.add("publication_identity")
        if "publish_rollback" in text or "publication rollback" in text or "not_newer" in text:
            matches.add("publish_rollback")
        if "contract_mismatch" in text or "contract mismatch" in text:
            matches.add("contract_mismatch")
        if "api_ui_mismatch" in text or "api/ui mismatch" in text or "api ui mismatch" in text:
            matches.add("api_ui_mismatch")
        if (
            "175.29" in text
            or "return_unit" in text
            or "return unit" in text
            or ("total return" in text and "unit" in text)
        ):
            matches.add("return_unit")
        if "date_regression" in text or "date regression" in text:
            matches.add("date_regression")
        if any(
            token in text
            for token in (
                "performance_date_mismatch",
                "performance date mismatch",
                "latest_date_mismatch",
                "trade_date_mismatch",
            )
        ):
            matches.add("date_regression")
        if any(
            token in text
            for token in (
                "publish_id",
                "publish id",
                "contract_id",
                "contract id",
                "artifact_version",
                "artifact version",
                "publication_identity",
                "publication identity",
            )
        ):
            matches.add("publication_identity")
        consistency_gate = candidate_gate or publication_gate
        if not consistency_gate:
            if "stale_cache" in text or "stale cache" in text or "cached selector" in text:
                matches.add("stale_cache")
            if any(
                token in text
                for token in (
                    "critical_request",
                    "requestfailed",
                    "request failed",
                    "transport error",
                    "network error",
                )
            ):
                matches.add("critical_request_transport")
            if any(
                token in text
                for token in (
                    "pageerror",
                    "page error",
                    "console error",
                    "white screen",
                    "wrong route context",
                    "route context",
                    "presentation_runtime",
                )
            ):
                matches.add("presentation_runtime")
            if runtime_gate and not matches:
                matches.add("presentation_runtime")
        if not matches:
            matches.add("unknown")
        classes.update(matches)
    classification_order = (
        "api_ui_mismatch",
        "publication_identity",
        "date_regression",
        "return_unit",
        "contract_mismatch",
        "publish_rollback",
        "unknown",
        "stale_cache",
        "critical_request_transport",
        "presentation_runtime",
    )
    return tuple(item for item in classification_order if item in classes)


def _failure_corresponds_to_warning(failure: str, warning: str) -> bool:
    return failure == warning or failure.endswith(f": {warning}")


def _assert_candidate_snapshot_matches_expected(
    snapshot: Mapping[str, object],
    expected_candidate_publications: Sequence[Mapping[str, object]],
    expected_trade_date: str,
) -> None:
    expected = _validate_candidate_publication_identities(
        expected_candidate_publications,
        expected_trade_date=expected_trade_date,
    )
    actual_publications = _required_list(
        snapshot.get("publications"),
        "browser_acceptance_candidate_snapshot_publications",
    )
    actual_by_strategy = {
        str(publication["strategyId"]): publication
        for publication in actual_publications
        if isinstance(publication, Mapping)
    }
    raw_expected_by_strategy = {
        str(publication.get("strategyId")): publication
        for publication in expected_candidate_publications
    }
    for expected_identity in expected:
        strategy_id = expected_identity["strategyId"]
        actual = actual_by_strategy.get(strategy_id)
        if actual is None:
            raise _error("browser_acceptance_candidate_snapshot_expected_mismatch", strategy_id)
        for field in ("tradeDate", "publishId", "publishStartedAt"):
            if actual.get(field) != expected_identity[field]:
                raise _error(
                    "browser_acceptance_candidate_snapshot_expected_mismatch",
                    f"{strategy_id}:{field}",
                )
        raw_expected = raw_expected_by_strategy[strategy_id]
        for field in ("contractId", "artifactVersion"):
            if field in raw_expected and actual.get(field) != _required_string(
                raw_expected.get(field),
                f"browser_acceptance_expected_candidate_{field}:{strategy_id}",
            ):
                raise _error(
                    "browser_acceptance_candidate_snapshot_expected_mismatch",
                    f"{strategy_id}:{field}",
                )
        if "totalReturnPct" in raw_expected:
            expected_return = _required_number(
                raw_expected.get("totalReturnPct"),
                f"browser_acceptance_expected_candidate_total_return_pct:{strategy_id}",
            )
            actual_return = _required_number(
                actual.get("totalReturnPct"),
                f"browser_acceptance_candidate_total_return_pct:{strategy_id}",
            )
            if round(actual_return, 2) != round(expected_return, 2):
                raise _error(
                    "browser_acceptance_candidate_snapshot_expected_mismatch",
                    f"{strategy_id}:totalReturnPct",
                )


def parse_browser_acceptance_report(
    report_path: str | Path,
    *,
    expected_run_id: str,
    expected_trade_date: str,
    expected_revision: str,
    expected_candidate_publications: Sequence[Mapping[str, object]],
    exit_code: int,
) -> BrowserAcceptanceResult:
    path = Path(report_path)
    if not path.is_file():
        raise _error("browser_acceptance_report_missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error("browser_acceptance_report_malformed") from exc
    report = _required_object(raw, "browser_acceptance_report_schema")
    _exact_keys(report, _REPORT_KEYS, "browser_acceptance_report_schema")
    if report.get("schemaVersion") != REPORT_SCHEMA_VERSION:
        raise _error("browser_acceptance_report_schema_version")
    run_id = _required_string(report.get("runId"), "browser_acceptance_report_run_id")
    if run_id != expected_run_id:
        raise _error("browser_acceptance_report_run_id_mismatch", f"{run_id}:{expected_run_id}")
    trade_date = _required_date(
        report.get("tradeDate"), "browser_acceptance_report_trade_date"
    )
    if trade_date != expected_trade_date:
        raise _error(
            "browser_acceptance_report_trade_date_mismatch",
            f"{trade_date}:{expected_trade_date}",
        )
    revision = _required_string(report.get("revision"), "browser_acceptance_report_revision")
    if revision != expected_revision:
        raise _error(
            "browser_acceptance_report_revision_mismatch",
            f"{revision}:{expected_revision}",
        )
    started_at = _required_timestamp(
        report.get("startedAt"), "browser_acceptance_report_started_at"
    )
    ended_at = _required_timestamp(report.get("endedAt"), "browser_acceptance_report_ended_at")
    duration = _required_number(
        report.get("durationSeconds"), "browser_acceptance_report_duration"
    )
    if duration < 0:
        raise _error("browser_acceptance_report_duration_negative")
    if report.get("contractOnly") is not False:
        raise _error("browser_acceptance_report_contract_only")
    status_text = _required_string(report.get("status"), "browser_acceptance_report_status")
    if status_text not in {"success", "degraded", "failed"}:
        raise _error("browser_acceptance_report_status_invalid", status_text)
    if (status_text in {"success", "degraded"} and exit_code != 0) or (
        status_text == "failed" and exit_code == 0
    ):
        raise _error("browser_acceptance_exit_status_mismatch", f"{status_text}:{exit_code}")

    tests = _required_list(report.get("tests"), "browser_acceptance_report_tests")
    _validate_report_tests(tests)
    browser_projects = {
        _required_string(
            test.get("projectName"),
            "browser_acceptance_browser_project_invalid",
        )
        for test in tests
        if isinstance(test, dict)
    }
    if browser_projects != {DEFAULT_BROWSER_PROJECT}:
        raise _error("browser_acceptance_browser_project_mismatch")
    gate_statuses = _validate_gate_inventory(tests)
    blocking_failures, warning_failures = _test_failure_messages(tests)
    top_level_failures = [
        _required_string(item, "browser_acceptance_report_failure")
        for item in _required_list(report.get("failures"), "browser_acceptance_report_failures")
    ]
    if status_text == "success" and (blocking_failures or warning_failures or top_level_failures):
        raise _error("browser_acceptance_report_success_has_failures")
    if status_text in {"success", "degraded"} and any(
        status != "passed" for status in gate_statuses.values()
    ):
        raise _error("browser_acceptance_gate_status")
    if status_text == "degraded":
        top_level_classes = classify_browser_failures(top_level_failures)
        degraded_forbidden = NONREPAIRABLE_FAILURE_CLASSES - {"unknown", "infrastructure"}
        nonrepairable_top_level = set(top_level_classes) & degraded_forbidden
        top_matches_warnings = all(
            any(_failure_corresponds_to_warning(failure, warning) for warning in warning_failures)
            for failure in top_level_failures
        )
        warnings_have_top_match = all(
            any(_failure_corresponds_to_warning(failure, warning) for failure in top_level_failures)
            for warning in warning_failures
        )
        if (
            blocking_failures
            or not warning_failures
            or not top_level_failures
            or nonrepairable_top_level
            or not top_matches_warnings
            or not warnings_have_top_match
        ):
            raise _error("browser_acceptance_report_degraded_failure_shape")
    if status_text == "failed" and not (blocking_failures or top_level_failures):
        raise _error("browser_acceptance_report_failed_without_failure")

    raw_snapshot = report.get("candidateSnapshot")
    snapshot = _validate_candidate_snapshot(raw_snapshot, trade_date)
    _assert_candidate_snapshot_matches_expected(
        snapshot,
        expected_candidate_publications,
        expected_trade_date,
    )
    digest = _required_string(
        report.get("candidateSnapshotSha256"), "browser_acceptance_candidate_snapshot_sha256"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise _error("browser_acceptance_candidate_snapshot_sha256_invalid")
    expected_digest = hashlib.sha256(_stable_json(raw_snapshot).encode("utf-8")).hexdigest()
    if digest != expected_digest:
        raise _error("browser_acceptance_candidate_snapshot_sha256_mismatch")

    artifact_paths = [str(path)]
    for index, raw_attachment in enumerate(
        _required_list(report.get("attachments"), "browser_acceptance_report_attachments")
    ):
        attachment = _validate_attachment(
            raw_attachment,
            required_keys=_TOP_ATTACHMENT_REQUIRED_KEYS,
            code=f"browser_acceptance_report_attachment:{index}",
        )
        if "path" in attachment:
            artifact_paths.append(_safe_report_artifact_path(attachment["path"]))

    blocking_text = _dedupe([*top_level_failures, *blocking_failures])
    warning_text = _dedupe(warning_failures if status_text == "degraded" else [])
    failure_classes = classify_browser_failures(blocking_text) if status_text == "failed" else ()
    status = {
        "success": RepairStatus.SUCCESS,
        "degraded": RepairStatus.DEGRADED,
        "failed": RepairStatus.FAILED,
    }[status_text]
    message_parts = blocking_text if status == RepairStatus.FAILED else warning_text
    result = BrowserAcceptanceResult(
        status=status,
        trade_date=trade_date,
        run_id=run_id,
        duration_seconds=duration,
        application_revision=revision,
        browser_project=DEFAULT_BROWSER_PROJECT,
        report_schema_version=REPORT_SCHEMA_VERSION,
        failure_classes=failure_classes,
        warnings=warning_text,
        artifact_paths=_dedupe(artifact_paths),
        snapshot=_freeze_json(snapshot),
        started_at=started_at,
        ended_at=ended_at,
        message="; ".join(message_parts) or f"browser acceptance {status.value}",
    )
    if result.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        return _mark_result_verified(result)
    return result


def _redact_text(value: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    text = re.sub(
        r"(?i)\b(cookie|set-cookie|authorization)\s*:\s*[^\r\n]+",
        lambda match: f"{match.group(1)}: <redacted>",
        text,
    )
    text = re.sub(
        (
            r"(?i)(?<![A-Za-z0-9_])"
            r"((?:PGPASSWORD|AWS_SECRET_ACCESS_KEY|GH_TOKEN|DATABASE_URL|"
            r"[A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API[_-]?KEY|ACCESS[_-]?KEY)"
            r"[A-Za-z0-9_]*))\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        lambda match: f"{match.group(1)}=<redacted>",
        text,
    )
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer <redacted>", text)
    text = re.sub(
        r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]*:[^\s/@]+@",
        lambda match: f"{match.group(1)}<redacted>@",
        text,
    )
    text = re.sub(r"(?<![:/\w])/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+", "<path>", text)
    text = re.sub(r"(?<!\w)[A-Za-z]:[\\/][^\s,;]+", "<path>", text)
    return text


def _redacted_tail(path: Path, *, max_bytes: int = 16_384, max_chars: int = 4_000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            raw = handle.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="replace")
    return _redact_text(text)[-max_chars:].strip()


def _private_binary_writer(path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "wb")


def _prepare_private_directory(path: Path, *, must_create: bool) -> None:
    if path.is_symlink():
        raise _error("browser_acceptance_output_directory_symlink")
    try:
        path.mkdir(parents=True, exist_ok=not must_create, mode=0o700)
    except FileExistsError as exc:
        raise _error("browser_acceptance_attempt_output_exists") from exc
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise _error("browser_acceptance_output_directory_invalid")
    path.chmod(0o700)
    if path.stat().st_mode & 0o777 != 0o700:
        raise _error("browser_acceptance_output_directory_permissions")


def _secure_attempt_artifacts(
    attempt_dir: Path,
    artifacts: Iterable[str | Path],
) -> tuple[str, ...]:
    root = attempt_dir.resolve(strict=True)
    secured: list[str] = []
    for raw in artifacts:
        path = Path(raw)
        candidate = path if path.is_absolute() else attempt_dir / path
        try:
            relative_candidate = candidate.relative_to(attempt_dir)
        except ValueError:
            raise _error("browser_acceptance_artifact_outside_attempt", str(path))
        cursor = attempt_dir
        for part in relative_candidate.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise _error("browser_acceptance_artifact_symlink", str(path))
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise _error("browser_acceptance_artifact_missing", str(path)) from exc
        if not resolved.is_relative_to(root):
            raise _error("browser_acceptance_artifact_outside_attempt", str(path))
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise _error("browser_acceptance_artifact_symlink", str(path))
        if not stat.S_ISREG(metadata.st_mode):
            raise _error("browser_acceptance_artifact_not_regular", str(path))
        candidate.chmod(0o600)
        if candidate.stat().st_mode & 0o777 != 0o600:
            raise _error("browser_acceptance_artifact_permissions", str(path))
        secured.append(str(resolved))
    return _dedupe(secured)


def _terminate_process_group(process: Any, grace_seconds: float) -> None:
    try:
        os.killpg(int(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(int(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        return


def _default_runtime_checker(dashboard_root: Path) -> None:
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise _error("browser_acceptance_pnpm_missing")
    node = shutil.which("node")
    if not node:
        raise _error("browser_acceptance_node_missing")
    check = subprocess.run(
        [
            node,
            "-e",
            (
                "const fs=require('node:fs');"
                "const {chromium}=require('@playwright/test');"
                "if(!fs.existsSync(chromium.executablePath()))process.exit(3)"
            ),
        ],
        cwd=dashboard_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
        check=False,
    )
    if check.returncode != 0:
        raise _error("browser_acceptance_chromium_runtime_missing")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attempt_from_result(
    result: BrowserAcceptanceResult,
    *,
    attempt_number: int,
    exit_code: int | None,
    artifacts: Iterable[str],
    message: str | None = None,
) -> BrowserAcceptanceAttempt:
    return BrowserAcceptanceAttempt(
        attempt_number=attempt_number,
        status=result.status,
        duration_seconds=result.duration_seconds,
        exit_code=exit_code,
        failure_classes=result.failure_classes,
        warnings=result.warnings,
        artifact_paths=_dedupe([*artifacts, *result.artifact_paths]),
        snapshot=result.snapshot,
        message=message or result.message,
    )


def _infrastructure_attempt(
    *,
    attempt_number: int,
    duration_seconds: float,
    exit_code: int | None,
    artifacts: Iterable[str],
    message: str,
) -> BrowserAcceptanceAttempt:
    return BrowserAcceptanceAttempt(
        attempt_number=attempt_number,
        status=RepairStatus.FAILED,
        duration_seconds=duration_seconds,
        exit_code=exit_code,
        failure_classes=("infrastructure",),
        artifact_paths=_dedupe(artifacts),
        message=message,
    )


def _run_attempt(
    *,
    attempt_number: int,
    trade_date: str,
    run_id: str,
    revision: str,
    candidate_publications: Sequence[Mapping[str, object]],
    output_root: Path,
    previous_publications_json: str,
    dashboard_root: Path,
    dashboard_port: int,
    api_port: int,
    timeout_seconds: float,
    termination_grace_seconds: float,
    popen: Callable[..., Any],
    base_env: Mapping[str, str],
) -> BrowserAcceptanceAttempt:
    attempt_started = time.monotonic()
    attempt_dir = output_root / f"attempt-{attempt_number}"
    try:
        _prepare_private_directory(attempt_dir, must_create=True)
    except (BrowserAcceptanceError, OSError) as exc:
        return _infrastructure_attempt(
            attempt_number=attempt_number,
            duration_seconds=max(0.0, time.monotonic() - attempt_started),
            exit_code=None,
            artifacts=(),
            message=_redact_text(str(exc)),
        )
    stdout_path = attempt_dir / "stdout.log"
    stderr_path = attempt_dir / "stderr.log"
    report_path = attempt_dir / "eod-browser-acceptance.json"
    artifacts = [str(stdout_path), str(stderr_path)]
    env = dict(base_env)
    env.pop("PLAYWRIGHT_EOD_CONTRACT_ONLY", None)
    env.update(
        {
            "PLAYWRIGHT_PROFILE": "eod",
            "PLAYWRIGHT_EOD_TRADE_DATE": trade_date,
            "PLAYWRIGHT_EOD_RUN_ID": run_id,
            "PLAYWRIGHT_EOD_REVISION": revision,
            "PLAYWRIGHT_EOD_PREVIOUS_PUBLICATIONS_JSON": previous_publications_json,
            "PLAYWRIGHT_EOD_OUTPUT_DIR": str(attempt_dir),
            "PLAYWRIGHT_JSON_OUTPUT_NAME": str(attempt_dir / "playwright-results.json"),
            "PLAYWRIGHT_DASHBOARD_PORT": str(dashboard_port),
            "PLAYWRIGHT_API_PORT": str(api_port),
            "PLAYWRIGHT_REUSE_EXISTING": "false",
        }
    )
    process = None
    exit_code: int | None = None
    error: BrowserAcceptanceError | None = None
    with _private_binary_writer(stdout_path) as stdout, _private_binary_writer(stderr_path) as stderr:
        try:
            process = popen(
                ["pnpm", "test:e2e:eod"],
                cwd=dashboard_root,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                umask=0o077,
            )
            exit_code = int(process.wait(timeout=timeout_seconds))
        except subprocess.TimeoutExpired:
            if process is not None:
                _terminate_process_group(process, termination_grace_seconds)
                exit_code = process.returncode
            error = _error("browser_acceptance_timeout", timeout_seconds)
        except (AttributeError, OSError, ValueError) as exc:
            error = _error("browser_acceptance_process_start_failed", type(exc).__name__)
    duration = max(0.0, time.monotonic() - attempt_started)
    stderr_tail = _redacted_tail(stderr_path)
    try:
        _prepare_private_directory(attempt_dir, must_create=False)
        _prepare_private_directory(output_root, must_create=False)
    except (BrowserAcceptanceError, OSError) as exc:
        error = _error("browser_acceptance_output_directory_security", _redact_text(str(exc)))
    base_artifacts = [str(stdout_path), str(stderr_path)]
    if report_path.exists() or report_path.is_symlink():
        base_artifacts.append(str(report_path))
    try:
        secured_base_artifacts = _secure_attempt_artifacts(attempt_dir, base_artifacts)
    except (BrowserAcceptanceError, OSError) as exc:
        error = _error("browser_acceptance_artifact_security", _redact_text(str(exc)))
        secured_base_artifacts = _secure_attempt_artifacts(
            attempt_dir,
            [str(stdout_path), str(stderr_path)],
        )
    if error is None:
        try:
            parsed = parse_browser_acceptance_report(
                report_path,
                expected_run_id=run_id,
                expected_trade_date=trade_date,
                expected_revision=revision,
                expected_candidate_publications=candidate_publications,
                exit_code=int(exit_code or 0),
            )
        except BrowserAcceptanceError as exc:
            error = exc
        else:
            message = _redact_text(parsed.message)
            if stderr_tail:
                message = f"{message}; stderr_tail={stderr_tail}"
            try:
                secured_artifacts = _secure_attempt_artifacts(
                    attempt_dir,
                    [*secured_base_artifacts, *parsed.artifact_paths],
                )
            except (BrowserAcceptanceError, OSError) as exc:
                error = _error("browser_acceptance_artifact_security", _redact_text(str(exc)))
            else:
                return _attempt_from_result(
                    replace(parsed, duration_seconds=duration, artifact_paths=()),
                    attempt_number=attempt_number,
                    exit_code=exit_code,
                    artifacts=secured_artifacts,
                    message=message,
                )
    message = _redact_text(
        str(error or _error("browser_acceptance_unknown_infrastructure_failure"))
    )
    if stderr_tail:
        message = f"{message}; stderr_tail={stderr_tail}"
    return _infrastructure_attempt(
        attempt_number=attempt_number,
        duration_seconds=duration,
        exit_code=exit_code,
        artifacts=secured_base_artifacts,
        message=message,
    )


def _result_from_attempts(
    *,
    trade_date: str,
    run_id: str,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    application_revision: str,
    attempts: Sequence[BrowserAcceptanceAttempt],
    override_status: RepairStatus | None = None,
    override_failure_classes: tuple[str, ...] | None = None,
    override_message: str | None = None,
) -> BrowserAcceptanceResult:
    final = attempts[-1] if attempts else None
    result = BrowserAcceptanceResult(
        status=override_status or (final.status if final else RepairStatus.FAILED),
        trade_date=trade_date,
        run_id=run_id,
        duration_seconds=max(0.0, duration_seconds),
        application_revision=application_revision,
        browser_project=DEFAULT_BROWSER_PROJECT,
        report_schema_version=REPORT_SCHEMA_VERSION,
        failure_classes=(
            override_failure_classes
            if override_failure_classes is not None
            else (final.failure_classes if final else ("infrastructure",))
        ),
        warnings=final.warnings if final else (),
        artifact_paths=_dedupe(
            path for attempt in attempts for path in attempt.artifact_paths
        ),
        snapshot=final.snapshot if final else _empty_snapshot(),
        started_at=started_at,
        ended_at=ended_at,
        message=override_message or (final.message if final else "browser acceptance failed"),
        attempts=tuple(attempts),
    )
    if result.status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        return _mark_result_verified(result)
    return result


def run_browser_acceptance(
    *,
    trade_date: str,
    run_id: str,
    revision: str,
    output_dir: str | Path,
    candidate_publications: Sequence[Mapping[str, object]],
    previous_publications: Mapping[str, object] | None = None,
    cache_clearer: Callable[[], object] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    api_port: int = DEFAULT_API_PORT,
    termination_grace_seconds: float = 5.0,
    dashboard_root: str | Path = _DASHBOARD_ROOT,
    popen: Callable[..., Any] = subprocess.Popen,
    runtime_checker: Callable[[Path], None] = _default_runtime_checker,
    base_env: Mapping[str, str] | None = None,
    previous_publication_loader: Callable[[], Mapping[str, object]] | None = None,
) -> BrowserAcceptanceResult:
    validated_trade_date = _required_date(trade_date, "browser_acceptance_trade_date_invalid")
    validated_run_id = _required_string(run_id, "browser_acceptance_run_id_invalid")
    validated_revision = _required_string(revision, "browser_acceptance_revision_invalid")
    if timeout_seconds <= 0:
        raise _error("browser_acceptance_timeout_invalid")
    if not 1 <= int(dashboard_port) <= 65535 or not 1 <= int(api_port) <= 65535:
        raise _error("browser_acceptance_port_invalid")
    output_root = Path(output_dir).absolute()
    try:
        _prepare_private_directory(output_root, must_create=False)
    except (BrowserAcceptanceError, OSError) as exc:
        return BrowserAcceptanceResult(
            status=RepairStatus.FAILED,
            trade_date=validated_trade_date,
            run_id=validated_run_id,
            duration_seconds=0.0,
            application_revision=validated_revision,
            failure_classes=("infrastructure",),
            message=_redact_text(str(exc)),
        )
    output_root = output_root.resolve(strict=True)
    started_at = _utc_now()
    overall_started = time.monotonic()
    try:
        validated_candidates = _validate_candidate_publication_identities(
            candidate_publications,
            expected_trade_date=validated_trade_date,
        )
        runtime_checker(Path(dashboard_root))
        if previous_publications is not None:
            previous = previous_publications
        elif previous_publication_loader is not None:
            previous = previous_publication_loader()
        else:
            previous = load_previous_official_publications(
                candidate_publications=list(validated_candidates)
            )
        previous = _validate_previous_publications_payload(previous)
        previous_json = _stable_json(previous)
    except Exception as exc:
        ended_at = _utc_now()
        message = _redact_text(str(exc))
        return BrowserAcceptanceResult(
            status=RepairStatus.FAILED,
            trade_date=validated_trade_date,
            run_id=validated_run_id,
            duration_seconds=max(0.0, time.monotonic() - overall_started),
            application_revision=validated_revision,
            failure_classes=("infrastructure",),
            started_at=started_at,
            ended_at=ended_at,
            message=message,
        )

    environment = dict(os.environ if base_env is None else base_env)
    attempts = [
        _run_attempt(
            attempt_number=1,
            trade_date=validated_trade_date,
            run_id=validated_run_id,
            revision=validated_revision,
            candidate_publications=validated_candidates,
            output_root=output_root,
            previous_publications_json=previous_json,
            dashboard_root=Path(dashboard_root),
            dashboard_port=int(dashboard_port),
            api_port=int(api_port),
            timeout_seconds=float(timeout_seconds),
            termination_grace_seconds=float(termination_grace_seconds),
            popen=popen,
            base_env=environment,
        )
    ]
    first = attempts[0]
    repairable = bool(first.failure_classes) and set(first.failure_classes).issubset(
        REPAIRABLE_FAILURE_CLASSES
    )
    if first.status == RepairStatus.FAILED and repairable and cache_clearer is not None:
        try:
            cache_clearer()
        except Exception as exc:
            ended_at = _utc_now()
            return _result_from_attempts(
                trade_date=validated_trade_date,
                run_id=validated_run_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=time.monotonic() - overall_started,
                application_revision=validated_revision,
                attempts=attempts,
                override_status=RepairStatus.FAILED,
                override_failure_classes=("infrastructure",),
                override_message=f"browser_acceptance_cache_clear_failed:{_redact_text(str(exc))}",
            )
        attempts.append(
            _run_attempt(
                attempt_number=2,
                trade_date=validated_trade_date,
                run_id=validated_run_id,
                revision=validated_revision,
                candidate_publications=validated_candidates,
                output_root=output_root,
                previous_publications_json=previous_json,
                dashboard_root=Path(dashboard_root),
                dashboard_port=int(dashboard_port),
                api_port=int(api_port),
                timeout_seconds=float(timeout_seconds),
                termination_grace_seconds=float(termination_grace_seconds),
                popen=popen,
                base_env=environment,
            )
        )
    ended_at = _utc_now()
    return _result_from_attempts(
        trade_date=validated_trade_date,
        run_id=validated_run_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=time.monotonic() - overall_started,
        application_revision=validated_revision,
        attempts=attempts,
    )


_PREVIOUS_PUBLICATIONS_SQL = """
SELECT *
FROM ops.data_run_manifest
WHERE module IN (
    'strategy_lhb_shortline',
    'strategy_mid_trend',
    'strategy_tech_bottleneck'
)
  AND source = 'strategy_daily_eod'
  AND status = 'success'
ORDER BY trade_date DESC, started_at DESC, run_id DESC
"""


def _row_trade_date(row: Mapping[str, object], strategy_id: str) -> str:
    trade_date = _required_date(
        row.get("trade_date"), f"previous_publication_trade_date:{strategy_id}"
    )
    latest = row.get("latest_trade_date")
    if latest not in {None, ""}:
        latest_date = _required_date(
            latest, f"previous_publication_latest_trade_date:{strategy_id}"
        )
        if latest_date != trade_date:
            raise _error("previous_publication_trade_date_conflict", strategy_id)
    return trade_date


def _timestamp_value(value: object, code: str) -> datetime:
    return datetime.fromisoformat(_required_timestamp(value, code))


def _same_explicit_value(
    containers: Sequence[Mapping[str, object]], key: str, code: str
) -> str:
    values = [container[key] for container in containers if key in container]
    if not values:
        raise _error(code)
    normalized = [_required_string(value, code) for value in values]
    if len(set(normalized)) != 1:
        raise _error(f"{code}_conflict")
    return normalized[0]


def _previous_publication_from_row(
    row: Mapping[str, object], strategy_id: str
) -> dict[str, object]:
    if row.get("status") != "success":
        raise _error("previous_publication_status", strategy_id)
    if row.get("source") not in {None, "", "strategy_daily_eod"}:
        raise _error("previous_publication_source", strategy_id)
    trade_date = _row_trade_date(row, strategy_id)
    publish_started_at = _required_timestamp(
        row.get("started_at"), f"previous_publication_publish_started_at:{strategy_id}"
    )
    metadata = _required_object(
        row.get("metadata"), f"previous_publication_metadata:{strategy_id}"
    )
    summary = _required_object(
        metadata.get("summary"), f"previous_publication_summary:{strategy_id}"
    )
    metadata_identity = _required_object(
        metadata.get("publication_identity"),
        f"previous_publication_identity:{strategy_id}",
    )
    summary_identity = _required_object(
        summary.get("publication_identity"),
        f"previous_publication_summary_identity:{strategy_id}",
    )
    for identity in (metadata_identity, summary_identity):
        if identity.get("strategy_id") != strategy_id:
            raise _error("previous_publication_strategy_identity", strategy_id)
    contract_id = _same_explicit_value(
        (metadata_identity, summary_identity),
        "contract_id",
        f"previous_publication_contract_id:{strategy_id}",
    )
    publish_id = _required_string(
        metadata.get("publish_id"), f"previous_publication_publish_id:{strategy_id}"
    )
    if "publish_id" in summary and _required_string(
        summary["publish_id"], f"previous_publication_publish_id:{strategy_id}"
    ) != publish_id:
        raise _error(f"previous_publication_publish_id:{strategy_id}_conflict")
    artifact_version = _same_explicit_value(
        (metadata, summary),
        "artifact_version",
        f"previous_publication_artifact_version:{strategy_id}",
    )
    if "total_return_pct" in summary:
        total_return_pct = _required_number(
            summary["total_return_pct"],
            f"previous_publication_total_return_pct:{strategy_id}",
        )
    elif "total_return" in summary:
        total_return_pct = 100.0 * _required_number(
            summary["total_return"], f"previous_publication_total_return:{strategy_id}"
        )
    elif "final_equity" in summary:
        total_return_pct = 100.0 * (
            _required_number(
                summary["final_equity"], f"previous_publication_final_equity:{strategy_id}"
            )
            - 1.0
        )
    else:
        raise _error("previous_publication_total_return_missing", strategy_id)
    return {
        "strategyId": strategy_id,
        "tradeDate": trade_date,
        "totalReturnPct": total_return_pct,
        "contractId": contract_id,
        "publishId": publish_id,
        "publishStartedAt": publish_started_at,
        "artifactVersion": artifact_version,
    }


def _validated_publication_row(
    row: Mapping[str, object], strategy_id: str
) -> tuple[dict[str, object], datetime, str]:
    publication = _previous_publication_from_row(row, strategy_id)
    started_at = _timestamp_value(
        row.get("started_at"), f"previous_publication_publish_started_at:{strategy_id}"
    )
    run_id = _required_string(
        row.get("run_id"), f"previous_publication_run_id:{strategy_id}"
    )
    return publication, started_at, run_id


def _has_publication_contract_markers(row: Mapping[str, object]) -> bool:
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    summary = metadata.get("summary")
    return any(
        key in metadata
        for key in ("publish_id", "publication_identity", "artifact_version")
    ) or (
        isinstance(summary, Mapping)
        and any(
            key in summary
            for key in ("publish_id", "publication_identity", "artifact_version")
        )
    )


def _strategy_manifest_business_time(row: Mapping[str, object]) -> datetime:
    value = (
        row.get("ended_at")
        or row.get("updated_at")
        or row.get("created_at")
        or row.get("started_at")
    )
    return _timestamp_value(value, "browser_candidate_manifest_business_time")


def select_latest_strategy_candidate_publications(
    rows: Iterable[Mapping[str, object]],
    *,
    trade_date: str,
) -> tuple[str, list[dict[str, object]]]:
    expected_trade_date = _required_date(
        trade_date, "browser_candidate_manifest_trade_date"
    )
    required_modules = {
        f"strategy_{strategy_id}" for strategy_id in OFFICIAL_STRATEGY_IDS
    }
    cohorts: dict[str, list[tuple[Mapping[str, object], datetime]]] = {}
    for raw in rows:
        row = dict(raw)
        if row.get("module") not in required_modules:
            continue
        run_id = _required_string(
            row.get("run_id"), "browser_candidate_manifest_run_id"
        )
        cohorts.setdefault(run_id, []).append(
            (row, _strategy_manifest_business_time(row))
        )
    if not cohorts:
        raise _error("browser_candidate_manifest_missing")
    cohort_times = {
        run_id: max(timestamp for _row, timestamp in cohort_rows)
        for run_id, cohort_rows in cohorts.items()
    }
    latest_time = max(cohort_times.values())
    latest_run_ids = [
        run_id for run_id, timestamp in cohort_times.items() if timestamp == latest_time
    ]
    if len(latest_run_ids) != 1:
        raise _error("browser_candidate_manifest_latest_run_ambiguous")
    run_id = latest_run_ids[0]
    latest_rows = [row for row, _timestamp in cohorts[run_id]]
    by_module: dict[str, list[Mapping[str, object]]] = {}
    for row in latest_rows:
        by_module.setdefault(str(row.get("module") or ""), []).append(row)
    if set(by_module) != required_modules or any(
        len(module_rows) != 1 for module_rows in by_module.values()
    ):
        raise _error("browser_candidate_manifest_latest_run_incomplete")
    candidates: list[dict[str, object]] = []
    for strategy_id in OFFICIAL_STRATEGY_IDS:
        row = by_module[f"strategy_{strategy_id}"][0]
        if row.get("source") != "strategy_daily_eod":
            raise _error("browser_candidate_manifest_source", strategy_id)
        publication, _started_at, row_run_id = _validated_publication_row(
            row, strategy_id
        )
        if row_run_id != run_id:
            raise _error("browser_candidate_manifest_run_id_mismatch", strategy_id)
        if publication["tradeDate"] != expected_trade_date:
            raise _error("browser_candidate_manifest_trade_date_mismatch", strategy_id)
        candidates.append({**publication, "runId": run_id})
    return run_id, candidates


def _select_unique_latest_prior(
    rows: Sequence[tuple[Mapping[str, object], dict[str, object], datetime, str]],
    strategy_id: str,
) -> Mapping[str, object]:
    if not rows:
        raise _error("previous_publication_missing_before_candidate", strategy_id)
    latest_trade_date = max(str(publication["tradeDate"]) for _, publication, _, _ in rows)
    latest_date_rows = [
        item for item in rows if str(item[1]["tradeDate"]) == latest_trade_date
    ]
    latest_started_at = max(started_at for _, _, started_at, _ in latest_date_rows)
    latest = [
        item for item in latest_date_rows if item[2] == latest_started_at
    ]
    if len(latest) != 1:
        raise _error("previous_publication_prior_ambiguous", strategy_id)
    return latest[0][0]


def load_previous_official_publications(
    *,
    reader: Callable[[], Iterable[Mapping[str, object]]] | None = None,
    connection: object | None = None,
    connection_reader: Callable[[object, str], Iterable[Mapping[str, object]]] | None = None,
    candidate_publications: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if reader is not None and connection is not None:
        raise _error("previous_publication_loader_ambiguous")
    if connection is not None:
        if connection_reader is None:
            from stock_research.db import fetch_all

            rows = list(fetch_all(connection, _PREVIOUS_PUBLICATIONS_SQL))
        else:
            rows = list(connection_reader(connection, _PREVIOUS_PUBLICATIONS_SQL))
    elif reader is not None:
        rows = list(reader())
    else:
        from stock_research.data_run_manifest import load_recent_data_run_manifest

        rows = list(load_recent_data_run_manifest())
    validated_candidates = (
        _validate_candidate_publication_identities(candidate_publications)
        if candidate_publications is not None
        else None
    )
    selected: list[dict[str, object]] = []
    for strategy_id in OFFICIAL_STRATEGY_IDS:
        module = f"strategy_{strategy_id}"
        candidates = [
            row
            for row in rows
            if isinstance(row, Mapping)
            and row.get("module") == module
            and row.get("status") == "success"
            and row.get("source") in {None, "", "strategy_daily_eod"}
            and _has_publication_contract_markers(row)
        ]
        if not candidates:
            raise _error("previous_publication_missing", strategy_id)
        validated_rows = [
            (row, *_validated_publication_row(row, strategy_id))
            for row in candidates
        ]
        if validated_candidates is None:
            latest = _select_unique_latest_prior(validated_rows, strategy_id)
            selected.append(_previous_publication_from_row(latest, strategy_id))
            continue
        candidate = next(
            item for item in validated_candidates if item["strategyId"] == strategy_id
        )
        candidate_started_at = _timestamp_value(
            candidate["publishStartedAt"],
            f"previous_publication_candidate_publish_started_at:{strategy_id}",
        )
        matches = [
            item
            for item in validated_rows
            if item[1]["tradeDate"] == candidate["tradeDate"]
            and item[1]["publishId"] == candidate["publishId"]
            and item[2] == candidate_started_at
            and ("runId" not in candidate or item[3] == candidate["runId"])
        ]
        if len(matches) != 1:
            raise _error("previous_publication_candidate_match_not_unique", strategy_id)
        matched = matches[0]
        later_or_tied = [
            item
            for item in validated_rows
            if item is not matched
            and (
                str(item[1]["tradeDate"]) > str(candidate["tradeDate"])
                or (
                    item[1]["tradeDate"] == candidate["tradeDate"]
                    and item[2] >= candidate_started_at
                )
            )
        ]
        if later_or_tied:
            raise _error("previous_publication_candidate_not_latest", strategy_id)
        same_day_priors = [
            item
            for item in validated_rows
            if item is not matched
            and item[1]["tradeDate"] == candidate["tradeDate"]
            and item[2] < candidate_started_at
        ]
        if same_day_priors:
            prior_rows = same_day_priors
        else:
            prior_rows = [
                item
                for item in validated_rows
                if item is not matched
                and str(item[1]["tradeDate"]) < str(candidate["tradeDate"])
            ]
        latest = _select_unique_latest_prior(prior_rows, strategy_id)
        selected.append(_previous_publication_from_row(latest, strategy_id))
    return {
        "schemaVersion": PREVIOUS_SCHEMA_VERSION,
        "publications": selected,
    }
