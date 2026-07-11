from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

import fcntl

from stock_research.data_to_brief_docling_parser_poc import parse_with_docling
from stock_research.theme_decomposition import (
    ACCESS_LEVELS,
    ARTIFACT_DIR as THEME_ARTIFACT_DIR,
    CLAIM_FIELDS,
    CLAIM_PLATFORM_USE_STATUSES,
    CLAIM_TYPES,
    EVIDENCE_STATUSES,
    RELIABILITY_LEVELS,
    SOURCE_FIELDS,
    SOURCE_REVIEW_STATUSES,
    SOURCE_TYPES,
    ThemeDecompositionValidationError,
    load_theme_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = THEME_ARTIFACT_DIR / "ingestion_runs"
RUN_VERSION = "theme_research_ingestion_run_v1_1"
EXTRACTOR_VERSION = "rule_based_sentence_v1"
MATCHER_VERSION = "theme_node_matcher_v1"
ADAPTER_VERSIONS = {
    "manual_claim_json": "manual_claim_json_v1",
    "text_document": "text_document_v1",
    "docling_document": "docling_document_v1",
    "existing_record": "existing_record_v1",
}
REVIEW_DECISIONS = {
    "accept_as_lead",
    "accept_draft",
    "accept_reviewed",
    "reject",
    "request_evidence",
    "defer",
}
IMMUTABLE_RUN_FILES = (
    "normalized_sources.json",
    "claim_candidates.json",
    "theme_node_matches.json",
    "review_queue.json",
)
ALL_RUN_FILES = (
    "manifest.json",
    *IMMUTABLE_RUN_FILES,
    "review_events.jsonl",
    "review_ledger_head.json",
    "promotion_preview.json",
)


class IngestionValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "INGESTION_VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return _normalize_text("".join(self.parts))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_input(
    input_path: str | Path,
    input_type: str,
    *,
    source_metadata: dict[str, Any] | None = None,
    docling_parser: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    path = Path(input_path)
    if input_type not in ADAPTER_VERSIONS:
        raise IngestionValidationError(f"unsupported input_type: {input_type}", code="UNSUPPORTED_INPUT_TYPE")
    if not path.is_file():
        raise IngestionValidationError(f"input not found: {path}", code="INPUT_NOT_FOUND")

    metadata = dict(source_metadata or {})
    manual_claims: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {
        "adapter_type": input_type,
        "adapter_version": ADAPTER_VERSIONS[input_type],
        "input_ref": str(path),
    }

    if input_type == "manual_claim_json":
        payload = _read_json_object(path)
        raw_source = payload.get("source")
        if not isinstance(raw_source, dict):
            raise IngestionValidationError("manual source object is required", code="MANUAL_SOURCE_REQUIRED")
        metadata = {**raw_source, **metadata}
        raw_claims = payload.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise IngestionValidationError("manual claims are required", code="MANUAL_CLAIMS_REQUIRED")
        manual_claims = [_normalize_manual_claim(row, index) for index, row in enumerate(raw_claims)]
        text = _normalize_text("\n".join(row["claim_text"] for row in manual_claims))
    elif input_type == "text_document":
        raw_text = _read_text_input(path)
        if path.suffix.lower() in {".html", ".htm"}:
            parser = _TextHTMLParser()
            parser.feed(raw_text)
            text = parser.text()
        else:
            text = _normalize_text(raw_text)
    elif input_type == "docling_document":
        parser_fn = docling_parser or parse_with_docling
        try:
            parsed = parser_fn(path)
        except Exception as exc:
            raise IngestionValidationError(
                f"Docling parse failed: {type(exc).__name__}: {exc}", code="DOCLING_PARSE_FAILED"
            ) from exc
        if not isinstance(parsed, dict):
            raise IngestionValidationError(
                "Docling parser returned a non-object result", code="DOCLING_PARSE_FAILED"
            )
        if parsed.get("status") != "parsed":
            message = str(parsed.get("error_message") or parsed.get("status") or "unknown parser error")
            raise IngestionValidationError(f"Docling parse failed: {message}", code="DOCLING_PARSE_FAILED")
        text = _normalize_text(str(parsed.get("markdown") or parsed.get("text") or ""))
        tables = parsed.get("tables") or []
        if not isinstance(tables, list):
            raise IngestionValidationError(
                "Docling parser returned invalid tables", code="DOCLING_PARSE_FAILED"
            )
        provenance.update(
            {
                "parser": str(parsed.get("parser") or "docling"),
                "parser_json_present": bool(parsed.get("json")),
                "table_count": len(tables),
            }
        )
    else:
        payload = _read_json_object(path)
        record_id = str(payload.get("record_id") or payload.get("id") or "").strip()
        text = _normalize_text(str(payload.get("content") or payload.get("body") or payload.get("text") or ""))
        metadata = {
            "title": payload.get("title", ""),
            "source_type": payload.get("source_type", "unknown"),
            "publisher": payload.get("publisher", ""),
            "author": payload.get("author", ""),
            "publish_date": payload.get("publish_date", payload.get("trade_date", "")),
            "url_or_ref": payload.get("url_or_ref") or (f"existing_record:{record_id}" if record_id else str(path)),
            "access_level": payload.get("access_level", "unknown"),
            "reliability_level": payload.get("reliability_level", ""),
            "notes": payload.get("notes", "Imported from an existing local record."),
            **metadata,
        }
        provenance["record_id"] = record_id

    if not text:
        raise IngestionValidationError("normalized input text is empty", code="EMPTY_NORMALIZED_TEXT")

    source_item = _normalize_source_item(metadata, path=path, input_type=input_type, text=text)
    fingerprint_payload = {
        "adapter_version": ADAPTER_VERSIONS[input_type],
        "source_item": source_item,
        "text": text,
        "manual_claims": manual_claims,
    }
    return {
        "input_type": input_type,
        "text": text,
        "source_item": source_item,
        "manual_claims": manual_claims,
        "content_sha256": hashlib.sha256(canonical_json(fingerprint_payload).encode("utf-8")).hexdigest(),
        "provenance": provenance,
    }


def create_ingestion_run(
    input_path: str | Path,
    *,
    input_type: str,
    theme_hint: str = "",
    source_metadata: dict[str, Any] | None = None,
    theme_artifact_dir: str | Path = THEME_ARTIFACT_DIR,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    docling_parser: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_input(
        input_path,
        input_type,
        source_metadata=source_metadata,
        docling_parser=docling_parser,
    )
    package = load_theme_package(theme_artifact_dir)
    _validate_theme_hint(theme_hint, package)
    source_candidate = _build_source_candidate(normalized)
    claim_candidates, matches = _build_claim_candidates(
        normalized,
        source_candidate=source_candidate,
        package=package,
        theme_hint=theme_hint,
    )
    queue = [
        _queue_item(source_candidate),
        *(_queue_item(candidate) for candidate in claim_candidates),
    ]
    run_id = _derive_run_id(
        input_type=input_type,
        content_sha256=normalized["content_sha256"],
        theme_hint=theme_hint,
        sources=[source_candidate],
        claims=claim_candidates,
        matches=matches,
        queue=queue,
    )
    root = Path(runs_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / _filesystem_id(run_id)
    ingest_lock = root / f".{_filesystem_id(run_id)}.ingest.lock"
    with _exclusive_lock(ingest_lock):
        if run_dir.exists():
            validate_run(run_dir)
            return {"status": "ok", "created": False, "run_id": run_id, "run_dir": str(run_dir)}
        created_at = _utc_now()
        payloads = {
            "normalized_sources.json": _run_items_payload(run_id, [source_candidate]),
            "claim_candidates.json": _run_items_payload(run_id, claim_candidates),
            "theme_node_matches.json": _run_items_payload(run_id, matches),
            "review_queue.json": _run_items_payload(run_id, queue),
            "promotion_preview.json": {
                "run_version": RUN_VERSION,
                "run_id": run_id,
                "generated_at": created_at,
                "latest_decisions": {},
                "promotable_sources": [],
                "promotable_claims": [],
                "blocked_candidates": [],
            },
        }
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{_filesystem_id(run_id)}-", dir=root))
        try:
            for name, payload in payloads.items():
                _write_json(temp_dir / name, payload)
            (temp_dir / "review_events.jsonl").write_text("", encoding="utf-8")
            _write_json(
                temp_dir / "review_ledger_head.json",
                {
                    "run_version": RUN_VERSION,
                    "run_id": run_id,
                    "event_count": 0,
                    "last_event_sha256": _ledger_seed(run_id),
                },
            )
            manifest = {
                "run_version": RUN_VERSION,
                "run_id": run_id,
                "created_at": created_at,
                "status": "pending_human_review",
                "input_type": input_type,
                "input_ref": normalized["provenance"]["input_ref"],
                "content_sha256": normalized["content_sha256"],
                "theme_hint": theme_hint,
                "adapter_version": ADAPTER_VERSIONS[input_type],
                "extractor_version": EXTRACTOR_VERSION,
                "matcher_version": MATCHER_VERSION,
                "immutable_file_sha256": {name: file_sha256(temp_dir / name) for name in IMMUTABLE_RUN_FILES},
            }
            _write_json(temp_dir / "manifest.json", manifest)
            os.replace(temp_dir, run_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    validate_run(run_dir)
    return {"status": "ok", "created": True, "run_id": run_id, "run_dir": str(run_dir)}


def validate_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    if not root.is_dir():
        raise IngestionValidationError(f"run directory not found: {root}", code="RUN_NOT_FOUND")
    missing = [name for name in ALL_RUN_FILES if not (root / name).is_file()]
    if missing:
        raise IngestionValidationError(f"run files missing: {', '.join(missing)}", code="RUN_FILE_MISSING")
    manifest = _read_json_object(root / "manifest.json")
    if manifest.get("run_version") != RUN_VERSION:
        raise IngestionValidationError("unsupported run version", code="UNSUPPORTED_RUN_VERSION")
    checksums = manifest.get("immutable_file_sha256")
    if not isinstance(checksums, dict):
        raise IngestionValidationError("manifest checksums are required", code="RUN_CHECKSUMS_REQUIRED")
    for name in IMMUTABLE_RUN_FILES:
        if checksums.get(name) != file_sha256(root / name):
            raise IngestionValidationError(f"run checksum mismatch: {name}", code="RUN_CHECKSUM_MISMATCH")

    run_id = str(manifest.get("run_id") or "")
    data = load_run(root, validate=False)
    for name in ("normalized_sources", "claim_candidates", "theme_node_matches", "review_queue"):
        payload = data[f"_{name}_payload"]
        if payload.get("run_version") != RUN_VERSION or payload.get("run_id") != run_id:
            raise IngestionValidationError(f"run identity mismatch: {name}", code="RUN_IDENTITY_MISMATCH")
    candidate_ids = {
        row.get("candidate_id")
        for row in [*data["normalized_sources"], *data["claim_candidates"]]
    }
    if None in candidate_ids or "" in candidate_ids:
        raise IngestionValidationError("candidate_id is required", code="CANDIDATE_ID_REQUIRED")
    _validate_run_candidates(data)
    for item in data["review_queue"]:
        if item.get("candidate_id") not in candidate_ids:
            raise IngestionValidationError("review queue references missing candidate", code="ORPHAN_REVIEW_QUEUE_ITEM")
    derived_run_id = _derive_run_id(
        input_type=str(manifest.get("input_type") or ""),
        content_sha256=str(manifest.get("content_sha256") or ""),
        theme_hint=str(manifest.get("theme_hint") or ""),
        sources=data["normalized_sources"],
        claims=data["claim_candidates"],
        matches=data["theme_node_matches"],
        queue=data["review_queue"],
    )
    if derived_run_id != run_id or root.name != _filesystem_id(run_id):
        raise IngestionValidationError(
            "run content does not match its content-addressed identity",
            code="CONTENT_ADDRESSED_RUN_MISMATCH",
        )
    candidate_by_id = {
        row["candidate_id"]: row
        for row in [*data["normalized_sources"], *data["claim_candidates"]]
    }
    events = _read_review_events(
        root, candidate_by_id=candidate_by_id, run_id=run_id, validate_policy=True
    )
    _validate_ledger_head(root, run_id=run_id, events=events)
    return {
        "status": "ok",
        "run_id": run_id,
        "source_candidate_count": len(data["normalized_sources"]),
        "claim_candidate_count": len(data["claim_candidates"]),
        "match_count": len(data["theme_node_matches"]),
    }


def load_run(run_dir: str | Path, *, validate: bool = True) -> dict[str, Any]:
    root = Path(run_dir)
    if validate:
        validate_run(root)
    manifest = _read_json_object(root / "manifest.json")
    sources_payload = _read_json_object(root / "normalized_sources.json")
    claims_payload = _read_json_object(root / "claim_candidates.json")
    matches_payload = _read_json_object(root / "theme_node_matches.json")
    queue_payload = _read_json_object(root / "review_queue.json")
    sources = _payload_items(sources_payload, "normalized_sources")
    claims = _payload_items(claims_payload, "claim_candidates")
    candidate_by_id = {row["candidate_id"]: row for row in [*sources, *claims]}
    return {
        "run_dir": str(root),
        "manifest": manifest,
        "normalized_sources": sources,
        "claim_candidates": claims,
        "theme_node_matches": _payload_items(matches_payload, "theme_node_matches"),
        "review_queue": _payload_items(queue_payload, "review_queue"),
        "review_events": _read_review_events(
            root,
            candidate_by_id=candidate_by_id,
            run_id=str(manifest.get("run_id") or ""),
            validate_policy=True,
        ),
        "review_ledger_head": _read_json_object(root / "review_ledger_head.json"),
        "promotion_preview": _read_json_object(root / "promotion_preview.json"),
        "_normalized_sources_payload": sources_payload,
        "_claim_candidates_payload": claims_payload,
        "_theme_node_matches_payload": matches_payload,
        "_review_queue_payload": queue_payload,
    }


def append_review_event(
    run_dir: str | Path,
    *,
    candidate_id: str,
    decision: str,
    reviewer: str,
    comment: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    with _exclusive_lock(_run_operation_lock(root)):
        validate_run(root)
        reviewer = reviewer.strip()
        comment = comment.strip()
        if not reviewer or not comment:
            raise IngestionValidationError(
                "reviewer and comment are required", code="REVIEWER_AND_COMMENT_REQUIRED"
            )
        if decision not in REVIEW_DECISIONS:
            raise IngestionValidationError(
                f"invalid review decision: {decision}", code="INVALID_REVIEW_DECISION"
            )
        run = load_run(root, validate=False)
        candidates = {
            row["candidate_id"]: row
            for row in [*run["normalized_sources"], *run["claim_candidates"]]
        }
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise IngestionValidationError(f"candidate not found: {candidate_id}", code="CANDIDATE_NOT_FOUND")
        if candidate_id in _effectively_promoted_candidate_ids(run["review_events"]):
            raise IngestionValidationError(
                "promoted candidate is frozen; use a corrective run",
                code="CANDIDATE_ALREADY_PROMOTED",
            )
        _validate_review_decision(candidate, decision, run)
        timestamp = reviewed_at or _utc_now()
        _parse_iso_timestamp(timestamp, field="reviewed_at")
        event = {
            "event_type": "candidate_review",
            "event_id": _stable_id(
                "theme_review_event",
                run["manifest"]["run_id"],
                candidate_id,
                decision,
                reviewer,
                comment,
                timestamp,
            ),
            "run_id": run["manifest"]["run_id"],
            "candidate_id": candidate_id,
            "candidate_type": candidate["candidate_type"],
            "decision": decision,
            "reviewer": reviewer,
            "comment": comment,
            "reviewed_at": timestamp,
        }
        stored = _append_ledger_event(root, event)
        _build_promotion_preview_unlocked(root)
        return stored


def build_promotion_preview(
    run_dir: str | Path,
    *,
    target_artifact: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    with _exclusive_lock(_run_operation_lock(root)):
        return _build_promotion_preview_unlocked(root, target_artifact=target_artifact)


def _build_promotion_preview_unlocked(
    run_dir: str | Path,
    *,
    target_artifact: str | Path | None = None,
) -> dict[str, Any]:
    validate_run(run_dir)
    run = load_run(run_dir, validate=False)
    latest = _latest_review_events(run["review_events"])
    source_candidates = {row["candidate_id"]: row for row in run["normalized_sources"]}
    claim_candidates = {row["candidate_id"]: row for row in run["claim_candidates"]}
    canonical_sources: dict[str, dict[str, Any]] = {}
    if target_artifact is not None:
        target = _read_json_object(Path(target_artifact))
        canonical_sources = {row["source_id"]: row for row in target.get("sources", [])}

    promotable_sources: list[dict[str, Any]] = []
    available_source_ids = set(canonical_sources)
    accepted_source_ids = {
        source_id
        for source_id, source in canonical_sources.items()
        if source.get("review_status") == "accepted" and source.get("reliability_level") != "S4"
    }
    blocked: list[dict[str, str]] = []
    for candidate_id, candidate in source_candidates.items():
        event = latest.get(candidate_id)
        if event is None:
            continue
        projected = _project_source(candidate, event["decision"])
        if projected is not None:
            promotable_sources.append(projected)
            available_source_ids.add(projected["source_id"])
            if projected["review_status"] == "accepted" and projected["reliability_level"] != "S4":
                accepted_source_ids.add(projected["source_id"])

    promotable_claims: list[dict[str, Any]] = []
    for candidate_id, candidate in claim_candidates.items():
        event = latest.get(candidate_id)
        if event is None:
            continue
        projected = _project_claim(candidate, event["decision"])
        if projected is None:
            continue
        required_source_ids = {projected["source_id"], *projected.get("supporting_source_ids", [])}
        if not required_source_ids.issubset(available_source_ids):
            blocked.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "claim source is not present or promotable",
                }
            )
            continue
        if projected["platform_use_status"] == "reviewed" and not (
            {projected["source_id"], *projected.get("supporting_source_ids", [])} & accepted_source_ids
        ):
            blocked.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "reviewed claim requires an accepted non-S4 source",
                }
            )
            continue
        promotable_claims.append(projected)

    preview = {
        "run_version": RUN_VERSION,
        "run_id": run["manifest"]["run_id"],
        "generated_at": _utc_now(),
        "latest_decisions": latest,
        "promotable_sources": promotable_sources,
        "promotable_claims": promotable_claims,
        "blocked_candidates": blocked,
    }
    _atomic_write_json(Path(run_dir) / "promotion_preview.json", preview)
    return preview


def promote_run(
    run_dir: str | Path,
    *,
    target_artifact: str | Path,
    expected_sha256: str,
) -> dict[str, Any]:
    root = Path(run_dir)
    target_path = Path(target_artifact)
    with _exclusive_lock(target_path.parent / ".theme_decomposition.package.lock"):
        _recover_outstanding_package_promotions(root.parent)
        with _exclusive_lock(_run_operation_lock(root)):
            return _promote_run_locked(
                root,
                target_path=target_path,
                expected_sha256=expected_sha256,
            )


def _promote_run_locked(
    run_dir: Path,
    *,
    target_path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    validate_run(run_dir)
    if not target_path.is_file():
        raise IngestionValidationError(f"target artifact not found: {target_path}", code="TARGET_ARTIFACT_NOT_FOUND")
    before_hash = file_sha256(target_path)
    if before_hash != expected_sha256:
        raise IngestionValidationError("canonical artifact hash changed", code="CANONICAL_HASH_MISMATCH")
    canonical = _read_json_object(target_path)
    run = load_run(run_dir, validate=False)
    preview = _build_promotion_preview_unlocked(run_dir, target_artifact=target_path)
    theme_id = str(canonical.get("theme", {}).get("theme_id") or "")
    run_theme_hint = str(run["manifest"].get("theme_hint") or "")
    if run_theme_hint and run_theme_hint != theme_id:
        raise IngestionValidationError(
            f"run theme {run_theme_hint} does not match target {theme_id}",
            code="PROMOTION_THEME_MISMATCH",
        )
    for claim in preview["promotable_claims"]:
        if claim["theme_id"] != theme_id:
            raise IngestionValidationError(
                f"claim theme {claim['theme_id']} does not match target {theme_id}",
                code="PROMOTION_THEME_MISMATCH",
            )

    candidate_artifact = copy.deepcopy(canonical)
    existing_sources = {row["source_id"]: row for row in candidate_artifact.get("sources", [])}
    existing_claims = {row["claim_id"]: row for row in candidate_artifact.get("claims", [])}
    added_sources: list[str] = []
    added_claims: list[str] = []
    for source in preview["promotable_sources"]:
        existing = existing_sources.get(source["source_id"])
        if existing is not None:
            if canonical_json(existing) != canonical_json(source):
                raise IngestionValidationError(
                    f"source ID collision: {source['source_id']}", code="PROMOTION_SOURCE_ID_COLLISION"
                )
            continue
        candidate_artifact.setdefault("sources", []).append(source)
        existing_sources[source["source_id"]] = source
        added_sources.append(source["source_id"])
    for claim in preview["promotable_claims"]:
        existing = existing_claims.get(claim["claim_id"])
        if existing is not None:
            if canonical_json(existing) != canonical_json(claim):
                raise IngestionValidationError(
                    f"claim ID collision: {claim['claim_id']}", code="PROMOTION_CLAIM_ID_COLLISION"
                )
            continue
        candidate_artifact.setdefault("claims", []).append(claim)
        existing_claims[claim["claim_id"]] = claim
        added_claims.append(claim["claim_id"])

    if not added_sources and not added_claims:
        return {
            "status": "no_changes",
            "run_id": preview["run_id"],
            "target_artifact": str(target_path),
            "before_sha256": before_hash,
            "after_sha256": before_hash,
            "added_source_count": 0,
            "added_claim_count": 0,
            "backup_path": "",
        }

    source_candidate_by_id = {
        row["proposed_source"]["source_id"]: row["candidate_id"]
        for row in run["normalized_sources"]
    }
    claim_candidate_by_id = {
        row["proposed_claim"]["claim_id"]: row["candidate_id"]
        for row in run["claim_candidates"]
    }
    promoted_candidate_ids = [
        *(source_candidate_by_id[source_id] for source_id in added_sources),
        *(claim_candidate_by_id[claim_id] for claim_id in added_claims),
    ]
    temp_path = _write_candidate_temp(target_path, candidate_artifact)
    prepared_event: dict[str, Any] | None = None
    try:
        _validate_candidate_artifact(
            temp_path,
            artifact_dir=target_path.parent,
            target_name=target_path.name,
        )
        if file_sha256(target_path) != expected_sha256:
            raise IngestionValidationError("canonical artifact hash changed", code="CANONICAL_HASH_MISMATCH")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = target_path.with_name(f"{target_path.name}.backup-{stamp}")
        shutil.copy2(target_path, backup_path)
        candidate_hash = file_sha256(temp_path)
        promotion_id = _stable_id("theme_promotion", preview["run_id"], before_hash, candidate_hash)
        prepared_event = _append_ledger_event(
            run_dir,
            {
                "event_type": "promotion",
                "event_id": _stable_id("theme_promotion_event", promotion_id, "prepared"),
                "run_id": preview["run_id"],
                "promotion_id": promotion_id,
                "promotion_status": "prepared",
                "recorded_at": _utc_now(),
                "target_artifact": str(target_path),
                "before_sha256": before_hash,
                "after_sha256": candidate_hash,
                "backup_path": str(backup_path),
                "added_source_ids": added_sources,
                "added_claim_ids": added_claims,
                "added_source_rows": [
                    source for source in preview["promotable_sources"] if source["source_id"] in added_sources
                ],
                "added_claim_rows": [
                    claim for claim in preview["promotable_claims"] if claim["claim_id"] in added_claims
                ],
                "promoted_candidate_ids": promoted_candidate_ids,
            },
        )
        os.replace(temp_path, target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        if prepared_event is not None:
            _append_promotion_terminal_event(run_dir, prepared_event, "failed")
        raise
    after_hash = file_sha256(target_path)
    try:
        _append_ledger_event(
            run_dir,
            {
                "event_type": "promotion",
                "event_id": _stable_id("theme_promotion_event", prepared_event["promotion_id"], "committed"),
                "run_id": preview["run_id"],
                "promotion_id": prepared_event["promotion_id"],
                "promotion_status": "committed",
                "recorded_at": _utc_now(),
                "target_artifact": str(target_path),
                "before_sha256": before_hash,
                "after_sha256": after_hash,
                "backup_path": str(backup_path),
                "added_source_ids": added_sources,
                "added_claim_ids": added_claims,
                "added_source_rows": prepared_event["added_source_rows"],
                "added_claim_rows": prepared_event["added_claim_rows"],
                "promoted_candidate_ids": promoted_candidate_ids,
            },
        )
    except Exception as exc:
        _restore_file_atomically(backup_path, target_path)
        try:
            _append_promotion_terminal_event(run_dir, prepared_event, "rolled_back")
        except Exception:
            pass
        raise IngestionValidationError(
            f"promotion audit commit failed and canonical artifact was rolled back: {exc}",
            code="PROMOTION_AUDIT_COMMIT_FAILED",
        ) from exc
    return {
        "status": "promoted",
        "run_id": preview["run_id"],
        "target_artifact": str(target_path),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "added_source_count": len(added_sources),
        "added_claim_count": len(added_claims),
        "backup_path": str(backup_path),
    }


def summarize_run(run_dir: str | Path) -> dict[str, Any]:
    validation = validate_run(run_dir)
    run = load_run(run_dir, validate=False)
    latest = _latest_review_events(run["review_events"])
    decision_counts: dict[str, int] = {}
    for event in latest.values():
        decision = event["decision"]
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    return {
        **validation,
        "pending_review_count": validation["source_candidate_count"]
        + validation["claim_candidate_count"]
        - len(latest),
        "latest_decisions": dict(sorted(decision_counts.items())),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-ingestion")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--theme-artifact-dir", default=str(THEME_ARTIFACT_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--input", required=True)
    ingest.add_argument("--input-type", choices=sorted(ADAPTER_VERSIONS), required=True)
    ingest.add_argument("--theme-hint", default="")
    ingest.add_argument("--source-metadata-json", default="{}")

    for command in ("validate-run", "summary", "show-queue", "promotion-preview"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--run", required=True)
        if command == "promotion-preview":
            sub.add_argument("--target-artifact")

    review = subparsers.add_parser("review")
    review.add_argument("--run", required=True)
    review.add_argument("--candidate-id", required=True)
    review.add_argument("--decision", choices=sorted(REVIEW_DECISIONS), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--comment", required=True)

    promote = subparsers.add_parser("promote")
    promote.add_argument("--run", required=True)
    promote.add_argument("--target-artifact", required=True)
    promote.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            metadata = json.loads(args.source_metadata_json)
            if not isinstance(metadata, dict):
                raise IngestionValidationError("source metadata must be an object", code="INVALID_SOURCE_METADATA")
            result = create_ingestion_run(
                args.input,
                input_type=args.input_type,
                theme_hint=args.theme_hint,
                source_metadata=metadata,
                theme_artifact_dir=args.theme_artifact_dir,
                runs_dir=args.runs_dir,
            )
        elif args.command == "validate-run":
            result = validate_run(args.run)
        elif args.command == "summary":
            result = summarize_run(args.run)
        elif args.command == "show-queue":
            run = load_run(args.run)
            result = {"status": "ok", "run_id": run["manifest"]["run_id"], "items": run["review_queue"]}
        elif args.command == "review":
            result = {
                "status": "ok",
                "event": append_review_event(
                    args.run,
                    candidate_id=args.candidate_id,
                    decision=args.decision,
                    reviewer=args.reviewer,
                    comment=args.comment,
                ),
            }
        elif args.command == "promotion-preview":
            result = build_promotion_preview(args.run, target_artifact=args.target_artifact)
        elif args.command == "promote":
            result = promote_run(
                args.run,
                target_artifact=args.target_artifact,
                expected_sha256=args.expected_sha256,
            )
        else:  # pragma: no cover
            raise AssertionError(f"unhandled command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (IngestionValidationError, ThemeDecompositionValidationError, json.JSONDecodeError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        print(
            json.dumps({"status": "error", "error_code": code, "message": str(exc)}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": "IO_ERROR",
                    "message": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def main() -> None:
    raise SystemExit(cli())


def _normalize_manual_claim(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IngestionValidationError(f"claims[{index}] must be an object", code="INVALID_MANUAL_CLAIM")
    text = _normalize_text(str(value.get("claim_text") or ""))
    if not text:
        raise IngestionValidationError(f"claims[{index}].claim_text is required", code="CLAIM_TEXT_REQUIRED")
    claim_type = str(value.get("claim_type") or _classify_claim(text))
    if claim_type not in CLAIM_TYPES:
        raise IngestionValidationError(f"claims[{index}].claim_type invalid", code="INVALID_CLAIM_TYPE")
    nodes = value.get("affected_theme_nodes") or []
    if not isinstance(nodes, list):
        raise IngestionValidationError(
            f"claims[{index}].affected_theme_nodes must be a list", code="INVALID_AFFECTED_NODES"
        )
    return {
        "claim_text": text,
        "claim_type": claim_type,
        "confidence": _bounded_confidence(value.get("confidence", 0.6)),
        "theme_id": str(value.get("theme_id") or ""),
        "affected_theme_nodes": [str(node) for node in nodes if str(node).strip()],
    }


def _normalize_source_item(
    metadata: dict[str, Any], *, path: Path, input_type: str, text: str
) -> dict[str, Any]:
    source_type = str(metadata.get("source_type") or "unknown")
    if source_type not in SOURCE_TYPES:
        raise IngestionValidationError(f"invalid source_type: {source_type}", code="INVALID_SOURCE_TYPE")
    access_level = str(metadata.get("access_level") or "unknown")
    if access_level not in ACCESS_LEVELS:
        raise IngestionValidationError(f"invalid access_level: {access_level}", code="INVALID_ACCESS_LEVEL")
    reliability = str(metadata.get("reliability_level") or _suggest_reliability(source_type, input_type))
    if reliability not in RELIABILITY_LEVELS:
        raise IngestionValidationError(
            f"invalid reliability_level: {reliability}", code="INVALID_RELIABILITY_LEVEL"
        )
    title = str(metadata.get("title") or path.stem).strip()
    identity = {
        "source_type": source_type,
        "title": title,
        "publisher": str(metadata.get("publisher") or ""),
        "publish_date": str(metadata.get("publish_date") or ""),
        "url_or_ref": str(metadata.get("url_or_ref") or f"local:{path.name}"),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    source_id = str(metadata.get("source_id") or _stable_id("theme_source", identity))
    review_status = "lead_only" if reliability == "S4" else "needs_full_text" if reliability == "S2" else "unknown"
    return {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "publisher": str(metadata.get("publisher") or ""),
        "author": str(metadata.get("author") or ""),
        "publish_date": str(metadata.get("publish_date") or ""),
        "url_or_ref": str(metadata.get("url_or_ref") or f"local:{path.name}"),
        "access_level": access_level,
        "reliability_level": reliability,
        "review_status": review_status,
        "notes": str(metadata.get("notes") or "Pending human review after local ingestion."),
    }


def _suggest_reliability(source_type: str, input_type: str) -> str:
    if source_type in {"video_claim", "social_post", "unknown"}:
        return "S4"
    if source_type == "media_article":
        return "S3"
    if source_type == "official_article":
        return "S1"
    if source_type in {"official_report", "broker_report", "company_filing"}:
        return "S0" if input_type == "docling_document" else "S2"
    return "S4"


def _build_source_candidate(normalized: dict[str, Any]) -> dict[str, Any]:
    source = copy.deepcopy(normalized["source_item"])
    return {
        "candidate_id": _stable_id("source_candidate", source["source_id"], normalized["content_sha256"]),
        "candidate_type": "source_candidate",
        "candidate_status": "pending_human_review",
        "content_sha256": normalized["content_sha256"],
        "normalized_text": normalized["text"],
        "normalized_text_sha256": hashlib.sha256(normalized["text"].encode("utf-8")).hexdigest(),
        "proposed_source": source,
        "suggested_review_status": source["review_status"],
        "suggestion_reasons": _source_suggestion_reasons(source),
        "provenance": copy.deepcopy(normalized["provenance"]),
    }


def _source_suggestion_reasons(source: dict[str, Any]) -> list[str]:
    if source["reliability_level"] == "S4":
        return ["oral, video, social, or unknown-origin material remains lead-only"]
    if source["reliability_level"] == "S2":
        return ["referenced report requires full-text review"]
    return ["source metadata and full text require human acceptance"]


def _build_claim_candidates(
    normalized: dict[str, Any],
    *,
    source_candidate: dict[str, Any],
    package: dict[str, Any],
    theme_hint: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_claims = normalized["manual_claims"] or _extract_sentences(normalized["text"])
    source_id = source_candidate["proposed_source"]["source_id"]
    candidates: list[dict[str, Any]] = []
    all_matches: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    for index, raw_claim in enumerate(raw_claims):
        explicit_nodes = raw_claim.get("affected_theme_nodes") or []
        preferred_theme = str(raw_claim.get("theme_id") or theme_hint)
        matches = _match_nodes(
            raw_claim["claim_text"],
            package=package,
            theme_hint=preferred_theme,
            explicit_nodes=explicit_nodes,
        )
        matched_nodes = [row["node_id"] for row in matches]
        matched_theme = preferred_theme or (matches[0]["theme_id"] if matches else "")
        claim_id = _stable_id("theme_claim", matched_theme, source_id, raw_claim["claim_text"])
        candidate_id = _stable_id("claim_candidate", claim_id, EXTRACTOR_VERSION)
        if candidate_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(candidate_id)
        proposed = {
            "claim_id": claim_id,
            "theme_id": matched_theme,
            "source_id": source_id,
            "claim_text": raw_claim["claim_text"],
            "claim_type": raw_claim.get("claim_type") or _classify_claim(raw_claim["claim_text"]),
            "confidence": _bounded_confidence(raw_claim.get("confidence", 0.5)),
            "evidence_status": "unverified",
            "platform_use_status": "research_lead",
            "supporting_source_ids": [],
            "affected_theme_nodes": matched_nodes,
        }
        span = raw_claim.get("span")
        if not isinstance(span, dict):
            start = normalized["text"].find(raw_claim["claim_text"])
            start = max(start, 0)
            span = {"start": start, "end": start + len(raw_claim["claim_text"])}
        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": "claim_candidate",
                "candidate_status": "pending_human_review",
                "source_candidate_id": source_candidate["candidate_id"],
                "proposed_claim": proposed,
                "extractor": EXTRACTOR_VERSION,
                "extraction_index": index,
                "extraction_span": span,
                "suggestion_reasons": ["automated extraction is staging-only"],
            }
        )
        all_matches.extend({"candidate_id": candidate_id, **row} for row in matches)
    return candidates, all_matches


def _extract_sentences(text: str) -> list[dict[str, Any]]:
    prepared = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    fragments = re.split(r"(?<=[.!?。！？])\s+|\n+", prepared)
    claims: list[dict[str, Any]] = []
    offset = 0
    for fragment in fragments:
        sentence = _normalize_text(fragment).lstrip("# ").strip()
        if len(sentence) < 12 or _looks_like_heading(sentence):
            continue
        start = text.find(sentence, offset)
        if start < 0:
            start = offset
        offset = start + len(sentence)
        claims.append(
            {
                "claim_text": sentence,
                "claim_type": _classify_claim(sentence),
                "confidence": 0.5,
                "theme_id": "",
                "affected_theme_nodes": [],
                "span": {"start": start, "end": offset},
            }
        )
    if not claims and len(_normalize_text(text)) >= 12:
        sentence = _normalize_text(text).lstrip("# ").strip()
        claims.append(
            {
                "claim_text": sentence,
                "claim_type": _classify_claim(sentence),
                "confidence": 0.4,
                "theme_id": "",
                "affected_theme_nodes": [],
                "span": {"start": 0, "end": len(sentence)},
            }
        )
    return claims


def _looks_like_heading(text: str) -> bool:
    return len(text) < 40 and not re.search(r"[.!?。！？]$", text) and len(text.split()) <= 4


def _classify_claim(text: str) -> str:
    lowered = text.lower()
    rules = (
        ("localization", ("国产替代", "domestic substitution", "localization", "进口替代")),
        ("value_capture", ("价值量", "value capture", "profit pool", "毛利率", "asp")),
        ("supply_constraint", ("供给约束", "capacity constraint", "shortage", "交付周期", "产能")),
        ("bottleneck", ("卡脖子", "bottleneck", "瓶颈", "constraint")),
        ("cost_structure", ("bom", "成本", "cost structure")),
        ("tech_route", ("技术路线", "architecture", "hvdc", "sic", "gan")),
        ("company_mapping", ("公司映射", "supplier", "上市公司", "公司")),
        ("valuation_signal", ("估值", "valuation", "multiple")),
        ("demand_shock", ("需求", "demand", "增长", "increase", "rises")),
    )
    for claim_type, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return claim_type
    return "tech_route"


def _match_nodes(
    text: str,
    *,
    package: dict[str, Any],
    theme_hint: str,
    explicit_nodes: list[str],
) -> list[dict[str, Any]]:
    nodes = [node for node in package["nodes"] if not theme_hint or node["theme_id"] == theme_hint]
    node_by_id = {node["node_id"]: node for node in nodes}
    matches: list[dict[str, Any]] = []
    for node_id in explicit_nodes:
        node = node_by_id.get(node_id)
        if node is None:
            raise IngestionValidationError(
                f"explicit node not found in selected theme: {node_id}", code="EXPLICIT_NODE_NOT_FOUND"
            )
        matches.append(
            {
                "theme_id": node["theme_id"],
                "node_id": node_id,
                "score": 1.0,
                "match_method": "explicit_node_id",
                "matched_terms": [node_id],
            }
        )
    if matches:
        return matches

    normalized_text = _normalized_match_text(text)
    text_tokens = _match_tokens(text)
    for node in nodes:
        aliases = _node_aliases(node)
        exact = [alias for alias in aliases if len(alias) >= 4 and alias in normalized_text]
        node_tokens = set().union(*(_match_tokens(alias) for alias in aliases))
        overlap = text_tokens & node_tokens
        score = 0.0
        method = ""
        terms: list[str] = []
        if exact:
            score = 0.95
            method = "alias_containment"
            terms = exact[:3]
        elif overlap:
            score = len(overlap) / max(1, min(len(text_tokens), len(node_tokens)))
            if score >= 0.5 and len(overlap) >= 2:
                method = "token_overlap"
                terms = sorted(overlap)
            else:
                score = 0.0
        if score:
            matches.append(
                {
                    "theme_id": node["theme_id"],
                    "node_id": node["node_id"],
                    "score": round(score, 4),
                    "match_method": method,
                    "matched_terms": terms,
                }
            )
    matches.sort(key=lambda row: (-row["score"], row["node_id"]))
    return matches[:5]


def _node_aliases(node: dict[str, Any]) -> set[str]:
    values: list[Any] = [node["node_id"].replace("_", " "), node["node_name"], node.get("description", "")]
    values.extend(node.get("key_metrics") or [])
    values.extend(node.get("overseas_leaders") or [])
    values.extend(node.get("domestic_players") or [])
    return {_normalized_match_text(str(value)) for value in values if str(value).strip()}


def _normalized_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", text.lower())).strip()


def _match_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
        if len(token) >= 2
    }


def _validate_theme_hint(theme_hint: str, package: dict[str, Any]) -> None:
    if theme_hint and theme_hint not in {theme["theme_id"] for theme in package["themes"]}:
        raise IngestionValidationError(f"theme hint not found: {theme_hint}", code="THEME_HINT_NOT_FOUND")


def _queue_item(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate["candidate_type"] == "source_candidate":
        label = candidate["proposed_source"]["title"]
    else:
        label = candidate["proposed_claim"]["claim_text"]
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_type": candidate["candidate_type"],
        "status": "pending_human_review",
        "label": label,
    }


def _validate_review_decision(candidate: dict[str, Any], decision: str, run: dict[str, Any]) -> None:
    if candidate["candidate_type"] == "source_candidate":
        if decision == "accept_reviewed":
            raise IngestionValidationError(
                "accept_reviewed applies only to claims", code="INVALID_SOURCE_REVIEW_DECISION"
            )
        if decision == "accept_draft" and candidate["proposed_source"]["reliability_level"] == "S4":
            raise IngestionValidationError("S4 source cannot be accepted", code="S4_SOURCE_CANNOT_BE_ACCEPTED")
        return
    if decision != "accept_reviewed":
        return
    source_candidate_id = candidate["source_candidate_id"]
    latest = _latest_review_events(run["review_events"])
    source_event = latest.get(source_candidate_id)
    sources = {row["candidate_id"]: row for row in run["normalized_sources"]}
    source = sources[source_candidate_id]["proposed_source"]
    if source_event is None or source_event["decision"] != "accept_draft" or source["reliability_level"] == "S4":
        raise IngestionValidationError(
            "reviewed claim requires accepted non-S4 source",
            code="REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE",
        )


def _project_source(candidate: dict[str, Any], decision: str) -> dict[str, Any] | None:
    if decision not in {"accept_as_lead", "accept_draft"}:
        return None
    source = copy.deepcopy(candidate["proposed_source"])
    source["review_status"] = "lead_only" if decision == "accept_as_lead" else "accepted"
    return source


def _project_claim(candidate: dict[str, Any], decision: str) -> dict[str, Any] | None:
    if decision not in {"accept_as_lead", "accept_draft", "accept_reviewed"}:
        return None
    claim = copy.deepcopy(candidate["proposed_claim"])
    if decision == "accept_as_lead":
        claim["platform_use_status"] = "research_lead"
        claim["evidence_status"] = "unverified"
    elif decision == "accept_draft":
        claim["platform_use_status"] = "draft"
        claim["evidence_status"] = "unverified"
    else:
        claim["platform_use_status"] = "reviewed"
        claim["evidence_status"] = "partially_verified"
    return claim


def _latest_review_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != "candidate_review":
            continue
        latest[event["candidate_id"]] = event
    return latest


def _read_review_events(
    run_dir: Path,
    *,
    candidate_by_id: dict[str, dict[str, Any]] | None = None,
    run_id: str = "",
    validate_policy: bool = False,
) -> list[dict[str, Any]]:
    path = run_dir / "review_events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise IngestionValidationError(
            f"cannot read review ledger: {type(exc).__name__}: {exc}", code="REVIEW_LEDGER_READ_FAILED"
        ) from exc
    events: list[dict[str, Any]] = []
    expected_previous = _ledger_seed(run_id) if run_id else ""
    prepared_promotions: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionValidationError(
                f"invalid review event at line {line_number}: {exc}", code="INVALID_REVIEW_EVENT_JSON"
            ) from exc
        if not isinstance(event, dict) or event.get("event_type") not in {"candidate_review", "promotion"}:
            raise IngestionValidationError(
                f"invalid review event at line {line_number}", code="INVALID_REVIEW_EVENT"
            )
        required_common = {"event_type", "event_id", "run_id", "previous_event_sha256", "event_sha256"}
        if not required_common.issubset(event) or not all(str(event.get(field) or "").strip() for field in required_common):
            raise IngestionValidationError(
                f"review event fields missing at line {line_number}", code="INVALID_REVIEW_EVENT"
            )
        if run_id and event["run_id"] != run_id:
            raise IngestionValidationError(
                f"review event run mismatch at line {line_number}", code="INVALID_REVIEW_EVENT"
            )
        if event["previous_event_sha256"] != expected_previous:
            raise IngestionValidationError(
                f"review event hash chain mismatch at line {line_number}", code="REVIEW_EVENT_CHAIN_MISMATCH"
            )
        unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
        actual_event_hash = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
        if event["event_sha256"] != actual_event_hash:
            raise IngestionValidationError(
                f"review event hash mismatch at line {line_number}", code="REVIEW_EVENT_HASH_MISMATCH"
            )
        if event["event_type"] == "candidate_review":
            required = {
                "candidate_id",
                "candidate_type",
                "decision",
                "reviewer",
                "comment",
                "reviewed_at",
            }
            if not required.issubset(event) or not all(str(event.get(field) or "").strip() for field in required):
                raise IngestionValidationError(
                    f"candidate review fields missing at line {line_number}", code="INVALID_REVIEW_EVENT"
                )
            if event.get("decision") not in REVIEW_DECISIONS:
                raise IngestionValidationError(
                    f"invalid review decision at line {line_number}", code="INVALID_REVIEW_EVENT"
                )
            _parse_iso_timestamp(str(event["reviewed_at"]), field="reviewed_at")
            expected_event_id = _stable_id(
                "theme_review_event",
                event["run_id"],
                event["candidate_id"],
                event["decision"],
                event["reviewer"],
                event["comment"],
                event["reviewed_at"],
            )
            if event["event_id"] != expected_event_id:
                raise IngestionValidationError(
                    f"candidate review ID mismatch at line {line_number}", code="INVALID_REVIEW_EVENT"
                )
            if candidate_by_id is not None and event.get("candidate_id") not in candidate_by_id:
                raise IngestionValidationError(
                    f"orphan review event at line {line_number}", code="ORPHAN_REVIEW_EVENT"
                )
            if candidate_by_id is not None:
                candidate = candidate_by_id[event["candidate_id"]]
                if event["candidate_type"] != candidate["candidate_type"]:
                    raise IngestionValidationError(
                        f"candidate type mismatch at line {line_number}", code="INVALID_REVIEW_EVENT"
                    )
                if event["candidate_id"] in _effectively_promoted_candidate_ids(events):
                    raise IngestionValidationError(
                        f"review after promotion at line {line_number}", code="CANDIDATE_ALREADY_PROMOTED"
                    )
                if validate_policy:
                    _validate_review_decision(
                        candidate,
                        event["decision"],
                        {
                            "review_events": events,
                            "normalized_sources": [
                                row for row in candidate_by_id.values() if row["candidate_type"] == "source_candidate"
                            ],
                        },
                    )
        else:
            required = {
                "promotion_id",
                "promotion_status",
                "recorded_at",
                "target_artifact",
                "before_sha256",
                "after_sha256",
                "backup_path",
                "added_source_ids",
                "added_claim_ids",
                "added_source_rows",
                "added_claim_rows",
                "promoted_candidate_ids",
            }
            if not required.issubset(event):
                raise IngestionValidationError(
                    f"promotion event fields missing at line {line_number}", code="INVALID_PROMOTION_EVENT"
                )
            if event["promotion_status"] not in {"prepared", "committed", "failed", "rolled_back"}:
                raise IngestionValidationError(
                    f"promotion status invalid at line {line_number}", code="INVALID_PROMOTION_EVENT"
                )
            _parse_iso_timestamp(str(event["recorded_at"]), field="recorded_at")
            expected_event_id = _stable_id(
                "theme_promotion_event", event["promotion_id"], event["promotion_status"]
            )
            if event["event_id"] != expected_event_id:
                raise IngestionValidationError(
                    f"promotion event ID mismatch at line {line_number}", code="INVALID_PROMOTION_EVENT"
                )
            for list_field in (
                "added_source_ids",
                "added_claim_ids",
                "added_source_rows",
                "added_claim_rows",
                "promoted_candidate_ids",
            ):
                if not isinstance(event[list_field], list):
                    raise IngestionValidationError(
                        f"promotion event list invalid at line {line_number}", code="INVALID_PROMOTION_EVENT"
                    )
            if candidate_by_id is not None and not set(event["promoted_candidate_ids"]).issubset(candidate_by_id):
                raise IngestionValidationError(
                    f"promotion references missing candidate at line {line_number}", code="INVALID_PROMOTION_EVENT"
                )
            if event["promotion_status"] == "prepared":
                prepared_promotions[event["promotion_id"]] = event
            else:
                prepared = prepared_promotions.get(event["promotion_id"])
                if prepared is None or any(
                    event[field] != prepared[field]
                    for field in (
                        "target_artifact",
                        "before_sha256",
                        "after_sha256",
                        "backup_path",
                        "added_source_ids",
                        "added_claim_ids",
                        "added_source_rows",
                        "added_claim_rows",
                        "promoted_candidate_ids",
                    )
                ):
                    raise IngestionValidationError(
                        f"promotion commit mismatch at line {line_number}", code="INVALID_PROMOTION_EVENT"
                    )
        events.append(event)
        expected_previous = event["event_sha256"]
    return events


def _append_ledger_event(run_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    events = _read_review_events(run_dir, run_id=str(event.get("run_id") or ""))
    previous_hash = events[-1]["event_sha256"] if events else _ledger_seed(event["run_id"])
    stored = {**event, "previous_event_sha256": previous_hash}
    stored["event_sha256"] = hashlib.sha256(canonical_json(stored).encode("utf-8")).hexdigest()
    path = run_dir / "review_events.jsonl"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(stored) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _atomic_write_json(
            run_dir / "review_ledger_head.json",
            {
                "run_version": RUN_VERSION,
                "run_id": event["run_id"],
                "event_count": len(events) + 1,
                "last_event_sha256": stored["event_sha256"],
            },
        )
    except OSError as exc:
        raise IngestionValidationError(
            f"cannot append review ledger: {type(exc).__name__}: {exc}", code="REVIEW_LEDGER_WRITE_FAILED"
        ) from exc
    return stored


def _validate_ledger_head(
    run_dir: Path,
    *,
    run_id: str,
    events: list[dict[str, Any]],
) -> None:
    head = _read_json_object(run_dir / "review_ledger_head.json")
    expected_hash = events[-1]["event_sha256"] if events else _ledger_seed(run_id)
    event_count = head.get("event_count")
    if (
        head.get("run_version") != RUN_VERSION
        or head.get("run_id") != run_id
        or not isinstance(event_count, int)
        or event_count < 0
        or event_count > len(events)
    ):
        raise IngestionValidationError(
            "review ledger head does not match the event log",
            code="REVIEW_LEDGER_HEAD_MISMATCH",
        )
    anchored_hash = events[event_count - 1]["event_sha256"] if event_count else _ledger_seed(run_id)
    if head.get("last_event_sha256") != anchored_hash:
        raise IngestionValidationError(
            "review ledger head does not match the event log",
            code="REVIEW_LEDGER_HEAD_MISMATCH",
        )
    if event_count < len(events):
        _atomic_write_json(
            run_dir / "review_ledger_head.json",
            {
                "run_version": RUN_VERSION,
                "run_id": run_id,
                "event_count": len(events),
                "last_event_sha256": expected_hash,
            },
        )


def _append_promotion_terminal_event(
    run_dir: Path,
    prepared_event: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return _append_ledger_event(
        run_dir,
        {
            key: value
            for key, value in prepared_event.items()
            if key not in {"event_id", "promotion_status", "recorded_at", "previous_event_sha256", "event_sha256"}
        }
        | {
            "event_id": _stable_id("theme_promotion_event", prepared_event["promotion_id"], status),
            "promotion_status": status,
            "recorded_at": _utc_now(),
        },
    )


def _effectively_promoted_candidate_ids(events: list[dict[str, Any]]) -> set[str]:
    latest_by_id: dict[str, dict[str, Any]] = {}
    prepared_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != "promotion":
            continue
        latest_by_id[event["promotion_id"]] = event
        if event["promotion_status"] == "prepared":
            prepared_by_id[event["promotion_id"]] = event
    frozen: set[str] = set()
    for promotion_id, latest in latest_by_id.items():
        if latest["promotion_status"] == "committed" and _prepared_rows_match_target(
            prepared_by_id[promotion_id]
        ):
            frozen.update(latest["promoted_candidate_ids"])
        elif latest["promotion_status"] == "prepared" and _prepared_rows_match_target(
            prepared_by_id[promotion_id]
        ):
            frozen.update(prepared_by_id[promotion_id]["promoted_candidate_ids"])
    return frozen


def _recover_prepared_promotions(run_dir: Path) -> bool:
    run = load_run(run_dir, validate=False)
    terminal_by_id: dict[str, str] = {}
    prepared_by_id: dict[str, dict[str, Any]] = {}
    for event in run["review_events"]:
        if event.get("event_type") != "promotion":
            continue
        terminal_by_id[event["promotion_id"]] = event["promotion_status"]
        if event["promotion_status"] == "prepared":
            prepared_by_id[event["promotion_id"]] = event
    recovered = False
    for promotion_id, status in terminal_by_id.items():
        prepared = prepared_by_id[promotion_id]
        target = Path(prepared["target_artifact"])
        if status == "committed":
            if _prepared_rows_match_target(prepared):
                continue
            if target.is_file() and file_sha256(target) == prepared["before_sha256"]:
                _append_promotion_terminal_event(run_dir, prepared, "rolled_back")
                recovered = True
                continue
            raise IngestionValidationError(
                "committed promotion rows are absent from an unexpected target state",
                code="PROMOTION_RECOVERY_CONFLICT",
            )
        if status != "prepared":
            continue
        if not target.is_file():
            raise IngestionValidationError(
                f"prepared promotion target is missing: {target}", code="PROMOTION_RECOVERY_CONFLICT"
            )
        current_hash = file_sha256(target)
        if current_hash == prepared["after_sha256"] or _prepared_rows_match_target(prepared):
            terminal_status = "committed"
        elif current_hash == prepared["before_sha256"]:
            terminal_status = "failed"
        else:
            raise IngestionValidationError(
                "prepared promotion target has an unexpected hash", code="PROMOTION_RECOVERY_CONFLICT"
            )
        _append_promotion_terminal_event(run_dir, prepared, terminal_status)
        recovered = True
    return recovered


def _recover_outstanding_package_promotions(runs_root: Path) -> None:
    if not runs_root.is_dir():
        return
    for candidate_run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        manifest_path = candidate_run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = _read_json_object(manifest_path)
        except IngestionValidationError:
            continue
        if manifest.get("run_version") != RUN_VERSION:
            continue
        with _exclusive_lock(_run_operation_lock(candidate_run_dir)):
            validate_run(candidate_run_dir)
            if _recover_prepared_promotions(candidate_run_dir):
                validate_run(candidate_run_dir)


def _prepared_rows_match_target(prepared: dict[str, Any]) -> bool:
    target = Path(str(prepared.get("target_artifact") or ""))
    if not target.is_file():
        return False
    try:
        artifact = _read_json_object(target)
    except IngestionValidationError:
        return False
    source_by_id = {row.get("source_id"): row for row in artifact.get("sources", []) if isinstance(row, dict)}
    claim_by_id = {row.get("claim_id"): row for row in artifact.get("claims", []) if isinstance(row, dict)}
    source_rows = prepared.get("added_source_rows", [])
    claim_rows = prepared.get("added_claim_rows", [])
    if not source_rows and not claim_rows:
        return False
    return all(
        canonical_json(source_by_id.get(row["source_id"])) == canonical_json(row)
        for row in source_rows
    ) and all(
        canonical_json(claim_by_id.get(row["claim_id"])) == canonical_json(row)
        for row in claim_rows
    )


def _validate_candidate_artifact(
    candidate_path: Path,
    *,
    artifact_dir: Path,
    target_name: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="theme-promotion-validate-") as temp_dir:
        validation_root = Path(temp_dir)
        for canonical_path in artifact_dir.glob("*.json"):
            if canonical_path.name != target_name:
                shutil.copy2(canonical_path, validation_root / canonical_path.name)
        shutil.copy2(candidate_path, validation_root / target_name)
        try:
            load_theme_package(validation_root)
        except ThemeDecompositionValidationError as exc:
            raise IngestionValidationError(
                f"promoted artifact failed validation: {exc}", code="PROMOTION_VALIDATION_FAILED"
            ) from exc


def _write_candidate_temp(target_path: Path, payload: dict[str, Any]) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent)
    temp_path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _restore_file_atomically(source_path: Path, target_path: Path) -> None:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target_path.name}.rollback.", suffix=".tmp", dir=target_path.parent
    )
    temp_path = Path(raw_path)
    try:
        with source_path.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = _write_candidate_temp(path, payload)
    os.replace(temp_path, path)


def _run_items_payload(run_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"run_version": RUN_VERSION, "run_id": run_id, "items": items}


def _derive_run_id(
    *,
    input_type: str,
    content_sha256: str,
    theme_hint: str,
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    queue: list[dict[str, Any]],
) -> str:
    if input_type not in ADAPTER_VERSIONS:
        raise IngestionValidationError(
            f"unsupported run input_type: {input_type}", code="UNSUPPORTED_INPUT_TYPE"
        )
    return _stable_id(
        "theme_ingestion_run",
        {
            "run_version": RUN_VERSION,
            "content_sha256": content_sha256,
            "theme_hint": theme_hint,
            "adapter_version": ADAPTER_VERSIONS[input_type],
            "extractor_version": EXTRACTOR_VERSION,
            "matcher_version": MATCHER_VERSION,
            "sources": sources,
            "claims": claims,
            "matches": matches,
            "queue": queue,
        },
    )


def _validate_run_candidates(data: dict[str, Any]) -> None:
    sources = data["normalized_sources"]
    claims = data["claim_candidates"]
    matches = data["theme_node_matches"]
    queue = data["review_queue"]
    if len(sources) != 1:
        raise IngestionValidationError("a v1 run requires one source candidate", code="INVALID_RUN_PAYLOAD")
    source_by_candidate_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(sources):
        required = {
            "candidate_id",
            "candidate_type",
            "candidate_status",
            "content_sha256",
            "normalized_text",
            "normalized_text_sha256",
            "proposed_source",
            "suggested_review_status",
            "suggestion_reasons",
            "provenance",
        }
        if not required.issubset(candidate) or candidate["candidate_type"] != "source_candidate":
            raise IngestionValidationError(
                f"source candidate invalid at index {index}", code="INVALID_RUN_PAYLOAD"
            )
        if candidate["candidate_status"] != "pending_human_review":
            raise IngestionValidationError("source candidate status invalid", code="INVALID_RUN_PAYLOAD")
        if hashlib.sha256(candidate["normalized_text"].encode("utf-8")).hexdigest() != candidate[
            "normalized_text_sha256"
        ]:
            raise IngestionValidationError("normalized source text hash mismatch", code="INVALID_RUN_PAYLOAD")
        source = candidate["proposed_source"]
        if not isinstance(source, dict) or not SOURCE_FIELDS.issubset(source):
            raise IngestionValidationError("proposed source fields missing", code="INVALID_RUN_PAYLOAD")
        if source["source_type"] not in SOURCE_TYPES:
            raise IngestionValidationError("proposed source type invalid", code="INVALID_RUN_PAYLOAD")
        if source["access_level"] not in ACCESS_LEVELS:
            raise IngestionValidationError("proposed source access invalid", code="INVALID_RUN_PAYLOAD")
        if source["reliability_level"] not in RELIABILITY_LEVELS:
            raise IngestionValidationError("proposed source reliability invalid", code="INVALID_RUN_PAYLOAD")
        if source["review_status"] not in SOURCE_REVIEW_STATUSES:
            raise IngestionValidationError("proposed source review status invalid", code="INVALID_RUN_PAYLOAD")
        if source["reliability_level"] == "S4" and source["review_status"] == "accepted":
            raise IngestionValidationError("S4 source cannot be accepted", code="S4_SOURCE_CANNOT_BE_ACCEPTED")
        source_by_candidate_id[candidate["candidate_id"]] = candidate

    claim_by_candidate_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(claims):
        required = {
            "candidate_id",
            "candidate_type",
            "candidate_status",
            "source_candidate_id",
            "proposed_claim",
            "extractor",
            "extraction_index",
            "extraction_span",
            "suggestion_reasons",
        }
        if not required.issubset(candidate) or candidate["candidate_type"] != "claim_candidate":
            raise IngestionValidationError(
                f"claim candidate invalid at index {index}", code="INVALID_RUN_PAYLOAD"
            )
        if candidate["candidate_status"] != "pending_human_review":
            raise IngestionValidationError("claim candidate status invalid", code="INVALID_RUN_PAYLOAD")
        source_candidate = source_by_candidate_id.get(candidate["source_candidate_id"])
        if source_candidate is None:
            raise IngestionValidationError("claim source candidate missing", code="INVALID_RUN_PAYLOAD")
        claim = candidate["proposed_claim"]
        if not isinstance(claim, dict) or not CLAIM_FIELDS.issubset(claim):
            raise IngestionValidationError("proposed claim fields missing", code="INVALID_RUN_PAYLOAD")
        if claim["source_id"] != source_candidate["proposed_source"]["source_id"]:
            raise IngestionValidationError("claim source ID mismatch", code="INVALID_RUN_PAYLOAD")
        if claim["claim_type"] not in CLAIM_TYPES or claim["evidence_status"] not in EVIDENCE_STATUSES:
            raise IngestionValidationError("proposed claim enum invalid", code="INVALID_RUN_PAYLOAD")
        if claim["platform_use_status"] not in CLAIM_PLATFORM_USE_STATUSES:
            raise IngestionValidationError("proposed claim status invalid", code="INVALID_RUN_PAYLOAD")
        if claim["platform_use_status"] != "research_lead" or claim["evidence_status"] != "unverified":
            raise IngestionValidationError(
                "automated claim must start as an unverified research lead", code="INVALID_RUN_PAYLOAD"
            )
        span = candidate["extraction_span"]
        if (
            not isinstance(span, dict)
            or not isinstance(span.get("start"), int)
            or not isinstance(span.get("end"), int)
            or span["start"] < 0
            or span["end"] < span["start"]
            or span["end"] > len(source_candidate["normalized_text"])
        ):
            raise IngestionValidationError("claim extraction span invalid", code="INVALID_RUN_PAYLOAD")
        claim_by_candidate_id[candidate["candidate_id"]] = candidate

    candidate_ids = {*source_by_candidate_id, *claim_by_candidate_id}
    queue_ids = [row.get("candidate_id") for row in queue]
    if set(queue_ids) != candidate_ids or len(queue_ids) != len(candidate_ids):
        raise IngestionValidationError("review queue does not cover candidates exactly", code="INVALID_RUN_PAYLOAD")
    for match in matches:
        if match.get("candidate_id") not in claim_by_candidate_id:
            raise IngestionValidationError("theme-node match references missing claim", code="INVALID_RUN_PAYLOAD")
        claim_nodes = claim_by_candidate_id[match["candidate_id"]]["proposed_claim"]["affected_theme_nodes"]
        if match.get("node_id") not in claim_nodes:
            raise IngestionValidationError("theme-node match differs from claim nodes", code="INVALID_RUN_PAYLOAD")


def _payload_items(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise IngestionValidationError(f"{label}.items must be a list of objects", code="INVALID_RUN_PAYLOAD")
    return items


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestionValidationError(f"invalid JSON in {path}: {exc}", code="INVALID_JSON") from exc
    except (OSError, UnicodeError) as exc:
        raise IngestionValidationError(
            f"cannot read {path}: {type(exc).__name__}: {exc}", code="INPUT_READ_FAILED"
        ) from exc
    if not isinstance(payload, dict):
        raise IngestionValidationError(f"JSON root must be an object: {path}", code="INVALID_JSON_ROOT")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _read_text_input(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IngestionValidationError(
            f"cannot read input {path}: {type(exc).__name__}: {exc}", code="INPUT_READ_FAILED"
        ) from exc


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise IngestionValidationError("confidence must be numeric", code="INVALID_CONFIDENCE") from exc
    if not 0 <= confidence <= 1:
        raise IngestionValidationError("confidence must be between 0 and 1", code="INVALID_CONFIDENCE")
    return confidence


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _ledger_seed(run_id: str) -> str:
    return hashlib.sha256(f"{RUN_VERSION}|{run_id}|review-ledger".encode("utf-8")).hexdigest()


def _parse_iso_timestamp(value: str, *, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestionValidationError(f"{field} must be ISO-8601", code="INVALID_REVIEW_EVENT") from exc


def _run_operation_lock(run_dir: Path) -> Path:
    return run_dir.parent / f".{run_dir.name}.operation.lock"


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _filesystem_id(value: str) -> str:
    return value.replace(":", "-")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
