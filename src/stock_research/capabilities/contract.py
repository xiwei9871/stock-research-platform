"""CAP-00 unified research contract.

Every capability (CAP-01..CAP-10) answers through a ResearchEnvelope:
same fields, same degradation semantics, same fingerprint chain.  A
capability that lacks inputs still answers — with status
``not_evaluated``/``unknown`` and an explicit ``data_gaps`` list — so the
pipeline never breaks and DATA work never blocks CAP skeleton work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence

RULE_VERSION = "cap00-r0"

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_EVALUATED = "not_evaluated"
STATUSES = {STATUS_OK, STATUS_PARTIAL, STATUS_UNKNOWN, STATUS_NOT_EVALUATED}

# Data-gap kinds — the DATA-line backlog vocabulary.
GAP_MISSING_SOURCE = "missing_source"            # 缺整个数据源
GAP_UNPARSED = "unparsed"                        # 源已存在但未解析入库
GAP_PENDING_REVIEW = "pending_review"            # 已解析待核验
GAP_ATTRIBUTION_UNKNOWN = "attribution_unknown"  # 已核验但产品线归属不明
GAP_TRULY_UNDISCLOSED = "truly_undisclosed"      # 企业确实未披露
GAP_PIT_INCOMPATIBLE = "pit_incompatible"        # 历史 PIT 不可用
GAP_KINDS = {
    GAP_MISSING_SOURCE, GAP_UNPARSED, GAP_PENDING_REVIEW,
    GAP_ATTRIBUTION_UNKNOWN, GAP_TRULY_UNDISCLOSED, GAP_PIT_INCOMPATIBLE,
}


@dataclass(frozen=True)
class DataGap:
    kind: str           # GAP_KINDS
    item: str           # what is missing, e.g. "product_revenue:603757"
    owner: str = "DATA" # which line owns the fix
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in GAP_KINDS:
            raise ValueError(f"unknown gap kind: {self.kind}")


@dataclass(frozen=True)
class ResearchEnvelope:
    capability_id: str                # e.g. "CAP-05"
    subject_type: str                 # theme | node | company | product_line | portfolio
    subject_id: str
    as_of: str
    run_id: str
    status: str                       # STATUSES
    findings: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    data_gaps: tuple[DataGap, ...] = ()
    fingerprint: str = ""
    rule_version: str = RULE_VERSION
    research_only: bool = True
    used_for_signal: bool = False
    used_for_admission: bool = False
    upstream_fingerprints: tuple[str, ...] = ()   # 引用链：上游信封指纹

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "status": self.status,
            "findings": self.findings,
            "evidence_refs": list(self.evidence_refs),
            "uncertainties": list(self.uncertainties),
            "data_gaps": [g.__dict__ for g in self.data_gaps],
            "fingerprint": self.fingerprint,
            "rule_version": self.rule_version,
            "research_only": self.research_only,
            "used_for_signal": self.used_for_signal,
            "used_for_admission": self.used_for_admission,
            "upstream_fingerprints": list(self.upstream_fingerprints),
        }


def envelope_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: v for k, v in payload.items() if k != "fingerprint"},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_envelope(
    capability_id: str,
    subject_type: str,
    subject_id: str,
    as_of: str,
    run_id: str,
    *,
    status: str = STATUS_UNKNOWN,
    findings: dict[str, Any] | None = None,
    evidence_refs: Sequence[str] = (),
    uncertainties: Sequence[str] = (),
    data_gaps: Sequence[DataGap | dict[str, Any]] = (),
    upstream_fingerprints: Sequence[str] = (),
    research_only: bool = True,
    used_for_signal: bool = False,
    used_for_admission: bool = False,
) -> ResearchEnvelope:
    """Build an envelope and seal its fingerprint (covers upstream chain)."""
    if status not in STATUSES:
        raise ValueError(f"bad status {status}")
    gaps = tuple(
        g if isinstance(g, DataGap) else DataGap(**g) for g in data_gaps
    )
    env = ResearchEnvelope(
        capability_id=capability_id,
        subject_type=subject_type,
        subject_id=subject_id,
        as_of=as_of,
        run_id=run_id,
        status=status,
        findings=findings or {},
        evidence_refs=tuple(evidence_refs),
        uncertainties=tuple(uncertainties),
        data_gaps=gaps,
        upstream_fingerprints=tuple(upstream_fingerprints),
        research_only=research_only,
        used_for_signal=used_for_signal,
        used_for_admission=used_for_admission,
    )
    payload = env.to_dict()
    return ResearchEnvelope(
        **{**env.__dict__, "fingerprint": envelope_fingerprint(payload)}
    )
