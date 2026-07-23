from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


PRIMARY_CLASSIFICATIONS = frozenset(
    {
        "primary_source_lead",
        "contextual_industry",
        "company_evidence_lead",
        "investment_opinion_non_evidence",
    }
)

ER_DISPOSITIONS = frozenset(
    {
        "source_discovery_only",
        "contextual_candidate",
        "not_relevant",
    }
)

DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "pcb_design": (
        "印制电路板",
        "高多层板",
        "高速pcb",
        "pcb",
        "hdi",
        "msap",
        "类载板",
        "封装基板",
        "背板",
    ),
    "laminate_materials": (
        "覆铜板",
        "高速材料",
        "低损耗材料",
        "介电常数",
        "介质损耗",
        "树脂体系",
        "dk",
        "df",
        "ccl",
    ),
    "copper_foil": (
        "铜箔",
        "hvlp",
        "vlp",
        "rtf",
        "表面粗糙度",
        "surface profile",
        "rz",
        "ra",
        "rq",
        "rms roughness",
    ),
    "manufacturing_and_test": (
        "背钻",
        "压合",
        "层间对位",
        "直接成像",
        "ldi",
        "钻孔",
        "电测",
        "可靠性测试",
        "良率",
        "pcb主轴",
        "pcb设备",
    ),
}


@dataclass(frozen=True)
class RelevanceResult:
    selected: bool
    relevance_domains: tuple[str, ...]
    matched_signals: tuple[str, ...]


def validate_primary_classification(value: str) -> None:
    if value not in PRIMARY_CLASSIFICATIONS:
        raise ValueError(f"unsupported primary classification: {value}")


def validate_er_disposition(value: str) -> None:
    if value not in ER_DISPOSITIONS:
        raise ValueError(f"unsupported ER disposition: {value}")


def classify_relevance(
    row: Mapping[str, object],
    *,
    body_text: str,
) -> RelevanceResult:
    parts = [
        str(row.get(key) or "")
        for key in (
            "report_title",
            "title",
            "stock_name",
            "themes",
            "node_name",
            "content",
        )
    ]
    haystack = " ".join(parts + [body_text]).casefold()
    matches = {
        domain: tuple(signal for signal in signals if signal.casefold() in haystack)
        for domain, signals in DOMAIN_SIGNALS.items()
    }
    domains = tuple(sorted(domain for domain, signals in matches.items() if signals))
    signals = tuple(sorted({signal for domain in domains for signal in matches[domain]}))
    return RelevanceResult(
        selected=bool(domains),
        relevance_domains=domains,
        matched_signals=signals,
    )


def collapse_content_identities(
    rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        content_hash = str(row.get("content_sha256") or "").strip()
        uuid = str(row.get("uuid") or "").strip()
        identity = f"sha256:{content_hash}" if content_hash else f"uuid:{uuid}"
        grouped.setdefault(identity, []).append(row)

    collapsed: list[dict[str, object]] = []
    for identity, members in sorted(grouped.items()):
        canonical = dict(members[0])
        canonical["content_identity"] = identity
        canonical["source_record_uuids"] = sorted(
            str(item.get("uuid") or "") for item in members
        )
        canonical["duplicate_record_count"] = len(members) - 1
        collapsed.append(canonical)
    return collapsed
