"""Read model + research-only review sidecar for company-intelligence dossiers.

Dossiers are produced offline by ``company-intelligence-dossier`` CLI into
``outputs/research/company_intelligence/``. This module serves them to the
existing research workbench and records manual review/disagreement notes in a
JSONL sidecar next to the dossier — no production database writes, consistent
with the CAP-01 research-only boundary.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VALID_REVIEW_STATUSES = {"accepted", "rejected", "disagreed", "needs_more_evidence"}
_REVIEW_REQUIRED_FIELDS = ("claim_id", "review_status", "reviewer", "comment")


def company_intelligence_dir() -> Path:
    raw = os.environ.get("STOCK_RESEARCH_COMPANY_INTELLIGENCE_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path("outputs/research/company_intelligence")


def _sanitize_stock_code(stock_code: str) -> str:
    code = "".join(ch for ch in str(stock_code) if ch.isalnum())
    if not code:
        raise ValueError("invalid_stock_code")
    return code


def _dossier_path(stock_code: str) -> Path:
    return company_intelligence_dir() / f"{_sanitize_stock_code(stock_code)}_dossier.json"


def _markdown_path(stock_code: str) -> Path:
    return company_intelligence_dir() / f"{_sanitize_stock_code(stock_code)}_dossier.md"


def _reviews_path(stock_code: str) -> Path:
    return company_intelligence_dir() / f"{_sanitize_stock_code(stock_code)}_reviews.jsonl"


def list_company_intelligence_dossiers() -> dict[str, Any]:
    root = company_intelligence_dir()
    items: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*_dossier.json")):
            try:
                dossier = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append(
                {
                    "stock_code": dossier.get("company_code", path.name.removesuffix("_dossier.json")),
                    "company_name": dossier.get("company_name", ""),
                    "as_of": dossier.get("as_of", ""),
                    "overall_verdict": (dossier.get("conclusion") or {}).get("overall_verdict", ""),
                    "confidence": (dossier.get("conclusion") or {}).get("confidence"),
                    "generated_at": dossier.get("generated_at", ""),
                    "code_sha": (dossier.get("provenance") or {}).get("code_sha", ""),
                }
            )
    return {"items": items}


def load_company_intelligence_dossier(stock_code: str) -> dict[str, Any] | None:
    path = _dossier_path(stock_code)
    if not path.is_file():
        return None
    dossier = json.loads(path.read_text(encoding="utf-8"))
    dossier["reviews"] = list_company_intelligence_reviews(stock_code)["items"]
    dossier["markdown_available"] = _markdown_path(stock_code).is_file()
    return dossier


def load_company_intelligence_markdown(stock_code: str) -> str | None:
    path = _markdown_path(stock_code)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def list_company_intelligence_reviews(stock_code: str) -> dict[str, Any]:
    path = _reviews_path(stock_code)
    items: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"items": items}


def record_company_intelligence_review(stock_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    code = _sanitize_stock_code(stock_code)
    if not _dossier_path(code).is_file():
        raise ValueError("dossier_not_found")
    missing = [field for field in _REVIEW_REQUIRED_FIELDS if not str(payload.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing_fields:{','.join(missing)}")
    status = str(payload["review_status"]).strip()
    if status not in _VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid_review_status:{status}")
    record = {
        "stock_code": code,
        "claim_id": str(payload["claim_id"]).strip(),
        "review_status": status,
        "reviewer": str(payload["reviewer"]).strip(),
        "comment": str(payload["comment"]).strip(),
        "dimension": str(payload.get("dimension", "")).strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _reviews_path(stock_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
