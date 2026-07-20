from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_contracts import validate_acquisition_attempt
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import read_layered_canonical_json
from stock_research.research_project_v2_1.snapshot import _publish_bytes


_ATTEMPT_ID = re.compile(r"acquisition_attempt:[a-f0-9]{24}")
_EXTENSIONS = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/json": "json",
    "text/csv": "csv",
    "application/vnd.docling+json": "json",
    "image/png": "png",
    "image/jpeg": "jpg",
}


@dataclass(frozen=True)
class PublishedRawBytes:
    path: Path
    relative_path: str
    content_hash: str
    byte_size: int
    content_type: str


def write_acquisition_attempt(
    attempt: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> Path:
    effective = LayeredResearchLayout.default() if layout is None else layout
    validated = validate_acquisition_attempt(attempt)
    wrapper = {
        "schema_version": "2.3.0",
        "artifact_kind": "acquisition_attempt",
        "acquisition_attempt": validated,
    }
    return _publish_bytes(
        effective.acquisition_attempts_dir,
        f"{validated['attempt_id']}.json",
        canonical_bytes(wrapper),
    )


def read_acquisition_attempt(
    attempt_id: str,
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    if _ATTEMPT_ID.fullmatch(attempt_id) is None:
        raise ResearchProjectV2Error(
            "Acquisition attempt not found",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_ATTEMPT_NOT_FOUND",
            details={"attempt_id": attempt_id},
        )
    effective = LayeredResearchLayout.default() if layout is None else layout
    wrapper = read_layered_canonical_json(
        f"acquisition/attempts/{attempt_id}.json", layout=effective
    )
    return validate_acquisition_attempt(wrapper["acquisition_attempt"])


def publish_raw_bytes(
    data: bytes,
    *,
    content_type: str,
    layout: LayeredResearchLayout | None = None,
) -> PublishedRawBytes:
    if content_type not in _EXTENSIONS:
        raise ResearchProjectV2Error(
            "Unsupported acquisition content type",
            code="RESEARCH_PROJECT_V2_1_ACQUISITION_UNSUPPORTED_FORMAT",
            details={"content_type": content_type},
        )
    effective = LayeredResearchLayout.default() if layout is None else layout
    digest = sha256(data).hexdigest()
    extension = _EXTENSIONS[content_type]
    relative = f"evidence/raw/{digest[:2]}/{digest}.{extension}"
    path = _publish_bytes(
        effective.evidence_raw_dir / digest[:2],
        f"{digest}.{extension}",
        data,
    )
    return PublishedRawBytes(
        path=path,
        relative_path=relative,
        content_hash=digest,
        byte_size=len(data),
        content_type=content_type,
    )
