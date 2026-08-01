from __future__ import annotations

import copy
import hashlib
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.theme_research_report_manifest import (
    ThemeResearchReportManifest,
    metadata_to_jsonable,
)


_PENDING_REVIEW = "pending_review"
_PUBLISHED = "published"
_REJECTED = "rejected"
_ARCHIVED = "archived"
_ADMIN_LIST_STATUSES = {_PENDING_REVIEW, _REJECTED}
_COMMENT_MAX_LENGTH = 2_000
_REASON_MAX_LENGTH = 4_000
_REQUEST_IDENTITY_MAX_LENGTH = 200
_DATABASE_REVIEW_ERROR_CODES = {
    "THEME_REPORT_ACTOR_NOT_FOUND",
    "THEME_REPORT_IDEMPOTENCY_CONFLICT",
    "THEME_REPORT_NOT_FOUND",
    "THEME_REPORT_REVIEW_REQUEST_INVALID",
    "THEME_REPORT_STATE_CONFLICT",
    "THEME_REPORT_VERSION_CONFLICT",
}


class ThemeResearchReportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = copy.deepcopy(details) if details is not None else {}


def report_version_id(theme_id: str, version: str) -> str:
    normalized_theme_id = _required_identity(theme_id, "theme_id")
    normalized_version = _required_identity(version, "version")
    return _stable_digest(
        "theme-research-report-version",
        normalized_theme_id,
        normalized_version,
    )


def register_report_manifest(
    manifest: ThemeResearchReportManifest,
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, str]:
    version_id = report_version_id(manifest.theme_id, manifest.version)
    metadata = metadata_to_jsonable(manifest.metadata)
    desired = {
        "report_version_id": version_id,
        **_immutable_values(manifest, metadata),
    }
    lock_key_1, lock_key_2 = _advisory_lock_keys(manifest.theme_id, manifest.version)

    try:
        with connect(service) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (lock_key_1, lock_key_2),
                )
                cur.execute(
                    """
                    SELECT 1
                    FROM research.theme_research_theme
                    WHERE theme_id = %s
                    """,
                    (manifest.theme_id,),
                )
                if cur.fetchone() is None:
                    raise ThemeResearchReportError(
                        "THEME_REPORT_THEME_NOT_FOUND",
                        "theme research report theme was not found",
                    )

                cur.execute(
                    """
                    SELECT report_version_id, title, summary,
                           markdown_relative_path, markdown_sha256,
                           pdf_relative_path, pdf_sha256,
                           manifest_relative_path, manifest_sha256,
                           generator_name, generator_version, generator_metadata,
                           generated_at, metadata, status
                    FROM research.theme_research_report_version
                    WHERE theme_id = %s AND version = %s
                    """,
                    (manifest.theme_id, manifest.version),
                )
                existing = cur.fetchone()
                if existing is not None:
                    differing_fields = [
                        field_name
                        for field_name, desired_value in desired.items()
                        if existing[field_name] != desired_value
                    ]
                    if differing_fields:
                        raise ThemeResearchReportError(
                            "THEME_REPORT_VERSION_CONTENT_CONFLICT",
                            "theme research report version already has different content",
                            {"fields": differing_fields},
                        )
                    return _safe_result(
                        version_id,
                        manifest,
                        status=existing["status"],
                        result="unchanged",
                    )

                pdf_relative_path = manifest.pdf.relative_path if manifest.pdf else None
                pdf_sha256 = manifest.pdf.sha256 if manifest.pdf else None
                event_id = _stable_digest("theme-research-report-index-event", version_id)
                request_id = _stable_digest("theme-research-report-index-request", version_id)
                idempotency_key = _stable_digest(
                    "theme-research-report-index-idempotency",
                    version_id,
                )
                cur.execute(
                    """
                    SELECT research.register_theme_research_report_pending(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) AS inserted
                    """,
                    (
                        version_id,
                        manifest.theme_id,
                        manifest.version,
                        manifest.title,
                        manifest.summary,
                        manifest.markdown.relative_path,
                        manifest.markdown.sha256,
                        pdf_relative_path,
                        pdf_sha256,
                        manifest.manifest_relative_path,
                        manifest.manifest_sha256,
                        manifest.generator_name,
                        manifest.generator_version,
                        Jsonb({}),
                        manifest.generated_at,
                        Jsonb(metadata),
                        event_id,
                        request_id,
                        idempotency_key,
                    ),
                )
                inserted = cur.fetchone()["inserted"]
                if not inserted:
                    cur.execute(
                        """
                        SELECT report_version_id, title, summary,
                               markdown_relative_path, markdown_sha256,
                               pdf_relative_path, pdf_sha256,
                               manifest_relative_path, manifest_sha256,
                               generator_name, generator_version, generator_metadata,
                               generated_at, metadata, status
                        FROM research.theme_research_report_version
                        WHERE theme_id = %s AND version = %s
                        """,
                        (manifest.theme_id, manifest.version),
                    )
                    existing = cur.fetchone()
                    differing_fields = [
                        field_name
                        for field_name, desired_value in desired.items()
                        if existing is None or existing[field_name] != desired_value
                    ]
                    if differing_fields:
                        raise ThemeResearchReportError(
                            "THEME_REPORT_VERSION_CONTENT_CONFLICT",
                            "theme research report version already has different content",
                            {"fields": differing_fields},
                        )
                    return _safe_result(
                        version_id,
                        manifest,
                        status=existing["status"],
                        result="unchanged",
                    )
    except ThemeResearchReportError:
        raise
    except psycopg.errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "fk_theme_research_report_version_theme":
            raise ThemeResearchReportError(
                "THEME_REPORT_THEME_NOT_FOUND",
                "theme research report theme was not found",
            ) from exc
        raise ThemeResearchReportError(
            "THEME_REPORT_STORE_UNAVAILABLE",
            "theme research report store is unavailable",
        ) from exc
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "uq_theme_research_report_theme_version":
            raise ThemeResearchReportError(
                "THEME_REPORT_VERSION_CONTENT_CONFLICT",
                "theme research report version already exists",
                {"fields": ["theme_id", "version"]},
            ) from exc
        raise ThemeResearchReportError(
            "THEME_REPORT_STORE_UNAVAILABLE",
            "theme research report store is unavailable",
        ) from exc
    except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as exc:
        raise ThemeResearchReportError(
            "THEME_REPORT_STORE_UNAVAILABLE",
            "theme research report store is temporarily unavailable",
        ) from exc
    except psycopg.Error as exc:
        raise ThemeResearchReportError(
            "THEME_REPORT_STORE_UNAVAILABLE",
            "theme research report store is unavailable",
        ) from exc

    return _safe_result(
        version_id,
        manifest,
        status=_PENDING_REVIEW,
        result="indexed",
    )


def publish_report_version(
    report_version_id: str,
    *,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    comment: str,
    request_id: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    normalized = _validate_review_request(
        report_version_id=report_version_id,
        expected_row_version=expected_row_version,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        request_id=request_id,
        idempotency_key=idempotency_key,
        comment=comment,
    )
    return _mutate_review_state(
        action="publish",
        expected_row_version=expected_row_version,
        service=service,
        **normalized,
    )


def reject_report_version(
    report_version_id: str,
    *,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    reason: str,
    request_id: str,
    idempotency_key: str,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    normalized = _validate_review_request(
        report_version_id=report_version_id,
        expected_row_version=expected_row_version,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        request_id=request_id,
        idempotency_key=idempotency_key,
        reason=reason,
    )
    return _mutate_review_state(
        action="reject",
        expected_row_version=expected_row_version,
        service=service,
        **normalized,
    )


def list_admin_report_versions(
    *,
    status: str = _PENDING_REVIEW,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    if status not in _ADMIN_LIST_STATUSES:
        raise _read_invalid("status", "status must be pending_review or rejected")
    rows = _read_rows(
        """
        SELECT *
        FROM research.theme_research_report_version
        WHERE status = %s
        ORDER BY generated_at DESC, report_version_id
        """,
        (status,),
        service=service,
    )
    items = [_admin_safe_row(row) for row in rows]
    return {"total": len(items), "items": items}


def get_admin_report_version(
    report_version_id: str,
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    normalized_id = _required_read_identity(report_version_id, "report_version_id")
    rows = _read_rows(
        """
        SELECT *
        FROM research.theme_research_report_version
        WHERE report_version_id = %s
        """,
        (normalized_id,),
        service=service,
    )
    if not rows:
        raise _not_found()
    return _admin_internal_row(rows[0])


def list_approved_report_versions(
    theme_id: str,
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    normalized_theme_id = _required_read_identity(theme_id, "theme_id")
    try:
        with connect(service) as conn:
            with conn.cursor() as cur:
                _require_theme(cur, normalized_theme_id)
                cur.execute(
                    """
                    SELECT *
                    FROM research.theme_research_report_version
                    WHERE theme_id = %s AND status IN ('published', 'archived')
                    ORDER BY (status = 'published') DESC,
                             published_at DESC NULLS LAST,
                             report_version_id
                    """,
                    (normalized_theme_id,),
                )
                items = [_approved_safe_row(row) for row in cur.fetchall()]
                return {"total": len(items), "items": items}
    except ThemeResearchReportError:
        raise
    except psycopg.Error as exc:
        raise _store_unavailable() from exc


def get_approved_report_version(
    theme_id: str,
    report_version_id: str,
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    return _get_approved_row(
        theme_id,
        report_version_id,
        service=service,
        mapper=_approved_safe_row,
    )


def get_approved_report_artifact_record(
    theme_id: str,
    report_version_id: str,
    *,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    return _get_approved_row(
        theme_id,
        report_version_id,
        service=service,
        mapper=_artifact_record,
    )


def _mutate_review_state(
    *,
    action: str,
    report_version_id: str,
    expected_row_version: int,
    actor_user_id: str,
    request_id: str,
    idempotency_key: str,
    service: str,
    comment: str = "",
    reason: str = "",
) -> dict[str, Any]:
    try:
        with connect(service) as conn:
            with conn.cursor() as cur:
                event_comment = comment if action == "publish" else reason
                cur.execute(
                    """
                    SELECT replayed, event_to_status, event_created_at
                    FROM research.review_theme_research_report_version(
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        action,
                        report_version_id,
                        expected_row_version,
                        actor_user_id,
                        event_comment,
                        request_id,
                        idempotency_key,
                        _review_event_id(action, actor_user_id, idempotency_key),
                    ),
                )
                outcome = cur.fetchone()
                cur.execute(
                    """
                    SELECT *
                    FROM research.theme_research_report_version
                    WHERE report_version_id = %s
                    """,
                    (report_version_id,),
                )
                updated = cur.fetchone()
                if updated is None or outcome is None:
                    raise _store_unavailable()
                if outcome["replayed"]:
                    return _replayed_admin_safe_row(
                        updated,
                        {
                            "to_status": outcome["event_to_status"],
                            "created_at": outcome["event_created_at"],
                        },
                    )
                return _admin_safe_row(updated)
    except ThemeResearchReportError:
        raise
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "uq_theme_research_report_review_actor_idempotency":
            raise ThemeResearchReportError(
                "THEME_REPORT_IDEMPOTENCY_CONFLICT",
                "idempotency key was already used for another review action",
            ) from exc
        raise _store_unavailable() from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name in {
            "fk_theme_research_report_version_published_by",
            "fk_theme_research_report_version_rejected_by",
        }:
            raise ThemeResearchReportError(
                "THEME_REPORT_ACTOR_NOT_FOUND",
                "review actor was not found",
            ) from exc
        raise _store_unavailable() from exc
    except psycopg.Error as exc:
        database_code = _database_review_error_code(exc)
        if database_code is not None:
            raise ThemeResearchReportError(
                database_code,
                "theme research report review was rejected",
            ) from exc
        raise _store_unavailable() from exc


def _validate_review_request(
    *,
    report_version_id: str,
    expected_row_version: int,
    actor_user_id: str,
    actor_role: str,
    request_id: str,
    idempotency_key: str,
    comment: str | None = None,
    reason: str | None = None,
) -> dict[str, str]:
    if actor_role != "admin":
        raise ThemeResearchReportError(
            "THEME_REPORT_ADMIN_REQUIRED",
            "administrator role is required",
        )
    if (
        not isinstance(expected_row_version, int)
        or isinstance(expected_row_version, bool)
        or expected_row_version < 1
    ):
        raise _review_invalid(
            "expected_row_version",
            "expected_row_version must be at least 1",
        )
    values = {
        "report_version_id": _required_review_identity(
            report_version_id,
            "report_version_id",
        ),
        "actor_user_id": _required_review_identity(actor_user_id, "actor_user_id"),
        "request_id": _required_review_identity(request_id, "request_id"),
        "idempotency_key": _required_review_identity(
            idempotency_key,
            "idempotency_key",
        ),
    }
    if comment is not None:
        if not isinstance(comment, str):
            raise _review_invalid("comment", "comment must be a string")
        if "\x00" in comment:
            raise _review_invalid("comment", "comment must not contain NUL")
        if len(comment) > _COMMENT_MAX_LENGTH:
            raise _review_invalid("comment", "comment is too long")
        values["comment"] = comment
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip():
            raise _review_invalid("reason", "reason must be a non-empty string")
        if "\x00" in reason:
            raise _review_invalid("reason", "reason must not contain NUL")
        normalized_reason = reason.strip()
        if len(normalized_reason) > _REASON_MAX_LENGTH:
            raise _review_invalid("reason", "reason is too long")
        values["reason"] = normalized_reason
    return values


def _required_review_identity(value: str, field_name: str) -> str:
    return _required_request_identity(
        value,
        field_name,
        error_factory=_review_invalid,
    )


def _required_read_identity(value: str, field_name: str) -> str:
    return _required_request_identity(
        value,
        field_name,
        error_factory=_read_invalid,
    )


def _required_request_identity(
    value: str,
    field_name: str,
    *,
    error_factory: Any,
) -> str:
    if not isinstance(value, str) or not value:
        raise error_factory(field_name, f"{field_name} must be a non-empty string")
    if "\x00" in value:
        raise error_factory(field_name, f"{field_name} must not contain NUL")
    if value != value.strip():
        raise error_factory(field_name, f"{field_name} must not contain outer whitespace")
    if len(value) > _REQUEST_IDENTITY_MAX_LENGTH:
        raise error_factory(field_name, f"{field_name} is too long")
    return value


def _review_invalid(field_name: str, message: str) -> ThemeResearchReportError:
    return ThemeResearchReportError(
        "THEME_REPORT_REVIEW_REQUEST_INVALID",
        message,
        {"fields": [field_name]},
    )


def _read_invalid(field_name: str, message: str) -> ThemeResearchReportError:
    return ThemeResearchReportError(
        "THEME_REPORT_READ_REQUEST_INVALID",
        message,
        {"fields": [field_name]},
    )


def _not_found() -> ThemeResearchReportError:
    return ThemeResearchReportError(
        "THEME_REPORT_NOT_FOUND",
        "theme research report was not found",
    )


def _store_unavailable() -> ThemeResearchReportError:
    return ThemeResearchReportError(
        "THEME_REPORT_STORE_UNAVAILABLE",
        "theme research report store is unavailable",
    )


def _database_review_error_code(exc: psycopg.Error) -> str | None:
    code = getattr(exc.diag, "message_primary", None)
    return code if code in _DATABASE_REVIEW_ERROR_CODES else None


def _require_theme(cur: psycopg.Cursor, theme_id: str) -> None:
    cur.execute(
        "SELECT 1 FROM research.theme_research_theme WHERE theme_id = %s",
        (theme_id,),
    )
    if cur.fetchone() is None:
        raise ThemeResearchReportError(
            "THEME_REPORT_THEME_NOT_FOUND",
            "theme research report theme was not found",
        )


def _read_rows(
    sql: str,
    params: tuple[Any, ...],
    *,
    service: str,
) -> list[dict[str, Any]]:
    try:
        with connect(service) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except psycopg.Error as exc:
        raise _store_unavailable() from exc


def _get_approved_row(
    theme_id: str,
    report_version_id: str,
    *,
    service: str,
    mapper: Any,
) -> dict[str, Any]:
    normalized_theme_id = _required_read_identity(theme_id, "theme_id")
    normalized_id = _required_read_identity(report_version_id, "report_version_id")
    rows = _read_rows(
        """
        SELECT *
        FROM research.theme_research_report_version
        WHERE theme_id = %s AND report_version_id = %s
          AND status IN ('published', 'archived')
        """,
        (normalized_theme_id, normalized_id),
        service=service,
    )
    if not rows:
        raise _not_found()
    return mapper(rows[0])


def _base_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version_id": row["report_version_id"],
        "theme_id": row["theme_id"],
        "version": row["version"],
        "title": row["title"],
        "summary": row["summary"],
        "status": row["status"],
        "generated_at": row["generated_at"],
        "indexed_at": row["indexed_at"],
        "published_at": row["published_at"],
        "published_by_user_id": row["published_by_user_id"],
        "row_version": row["row_version"],
        "metadata": {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _admin_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    result = _base_safe_row(row)
    result.update(
        {
            "rejected_at": row["rejected_at"],
            "rejected_by_user_id": row["rejected_by_user_id"],
            "rejection_reason": row["rejection_reason"],
        }
    )
    return result


def _approved_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version_id": row["report_version_id"],
        "theme_id": row["theme_id"],
        "version": row["version"],
        "title": row["title"],
        "summary": row["summary"],
        "status": row["status"],
        "generated_at": row["generated_at"],
        "published_at": row["published_at"],
        "has_pdf": row["pdf_relative_path"] is not None,
    }


def _replayed_admin_safe_row(
    row: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    result = _admin_safe_row(row)
    result["status"] = event["to_status"]
    if event["to_status"] == _PUBLISHED and row["status"] == _ARCHIVED:
        result["row_version"] = row["row_version"] - 1
        result["updated_at"] = event["created_at"]
    return result


def _admin_internal_row(row: dict[str, Any]) -> dict[str, Any]:
    result = _admin_safe_row(row)
    result.update(
        {
            "metadata": copy.deepcopy(row["metadata"]),
            "markdown_relative_path": row["markdown_relative_path"],
            "markdown_sha256": row["markdown_sha256"],
            "pdf_relative_path": row["pdf_relative_path"],
            "pdf_sha256": row["pdf_sha256"],
            "manifest_relative_path": row["manifest_relative_path"],
            "manifest_sha256": row["manifest_sha256"],
            "generator_name": row["generator_name"],
            "generator_version": row["generator_version"],
            "generator_metadata": copy.deepcopy(row["generator_metadata"]),
        }
    )
    return result


def _artifact_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version_id": row["report_version_id"],
        "theme_id": row["theme_id"],
        "version": row["version"],
        "status": row["status"],
        "markdown_relative_path": row["markdown_relative_path"],
        "markdown_sha256": row["markdown_sha256"],
        "pdf_relative_path": row["pdf_relative_path"],
        "pdf_sha256": row["pdf_sha256"],
        "manifest_relative_path": row["manifest_relative_path"],
        "manifest_sha256": row["manifest_sha256"],
    }


def _review_event_id(action: str, actor_user_id: str, idempotency_key: str) -> str:
    return _stable_digest(
        "theme-research-report-review-event",
        action,
        actor_user_id,
        idempotency_key,
    )


def _required_identity(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ThemeResearchReportError(
            "THEME_REPORT_IDENTITY_INVALID",
            f"{field_name} must be a non-empty string",
            {"fields": [field_name]},
        )
    return value


def _stable_digest(namespace: str, *parts: str) -> str:
    payload = "\x00".join((namespace, *parts)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _advisory_lock_keys(theme_id: str, version: str) -> tuple[int, int]:
    digest = hashlib.sha256(
        "\x00".join(("theme-research-report-lock", theme_id, version)).encode("utf-8")
    ).digest()
    return (
        int.from_bytes(digest[:4], "big", signed=True),
        int.from_bytes(digest[4:8], "big", signed=True),
    )


def _immutable_values(
    manifest: ThemeResearchReportManifest,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": manifest.title,
        "summary": manifest.summary,
        "markdown_relative_path": manifest.markdown.relative_path,
        "markdown_sha256": manifest.markdown.sha256,
        "pdf_relative_path": manifest.pdf.relative_path if manifest.pdf else None,
        "pdf_sha256": manifest.pdf.sha256 if manifest.pdf else None,
        "manifest_relative_path": manifest.manifest_relative_path,
        "manifest_sha256": manifest.manifest_sha256,
        "generator_name": manifest.generator_name,
        "generator_version": manifest.generator_version,
        "generator_metadata": {},
        "generated_at": manifest.generated_at,
        "metadata": metadata,
    }


def _safe_result(
    version_id: str,
    manifest: ThemeResearchReportManifest,
    *,
    status: str,
    result: str,
) -> dict[str, str]:
    return {
        "report_version_id": version_id,
        "theme_id": manifest.theme_id,
        "version": manifest.version,
        "status": status,
        "result": result,
    }
