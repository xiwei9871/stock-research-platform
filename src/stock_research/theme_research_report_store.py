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


_SYSTEM_ACTOR_USER_ID = "system"
_PENDING_REVIEW = "pending_review"


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
                cur.execute(
                    """
                    INSERT INTO research.theme_research_report_version (
                        report_version_id, theme_id, version, title, summary, status,
                        markdown_relative_path, markdown_sha256,
                        pdf_relative_path, pdf_sha256,
                        manifest_relative_path, manifest_sha256,
                        generator_name, generator_version, generator_metadata,
                        generated_at, metadata, row_version
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1
                    )
                    """,
                    (
                        version_id,
                        manifest.theme_id,
                        manifest.version,
                        manifest.title,
                        manifest.summary,
                        _PENDING_REVIEW,
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
                    ),
                )
                event_id = _stable_digest("theme-research-report-index-event", version_id)
                request_id = _stable_digest("theme-research-report-index-request", version_id)
                idempotency_key = _stable_digest(
                    "theme-research-report-index-idempotency",
                    version_id,
                )
                cur.execute(
                    """
                    INSERT INTO research.theme_research_report_review_event (
                        event_id, report_version_id, from_status, to_status,
                        actor_user_id, comment, request_id, idempotency_key
                    ) VALUES (%s, %s, NULL, %s, %s, '', %s, %s)
                    """,
                    (
                        event_id,
                        version_id,
                        _PENDING_REVIEW,
                        _SYSTEM_ACTOR_USER_ID,
                        request_id,
                        idempotency_key,
                    ),
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
