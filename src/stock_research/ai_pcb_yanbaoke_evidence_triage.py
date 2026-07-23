from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re


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

ER_SIGNAL_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "PCB-ER-A02": {
        "objects": (
            "data rate",
            "baud rate",
            "serdes",
            "channel measurement",
            "通道测量",
            "速率",
            "reach",
        ),
        "denominators": (
            "ghz",
            "gbps",
            "gbaud",
            "nyquist",
            "mm",
            "cm",
            "meter",
            "topology",
            "拓扑",
            "connector",
            "retimer",
            "insertion loss",
            "return loss",
            "crosstalk",
            "ber",
        ),
    },
    "PCB-ER-A04": {
        "objects": (
            "insertion loss",
            "插入损耗",
            "插损",
            "s参数",
            "s-parameter",
            "s parameter",
        ),
        "denominators": (
            "fixture removal",
            "de-embedding",
            "deembedding",
            "reference plane",
            "test coupon",
            "校准",
            "夹具",
            "去嵌",
            "参考平面",
            "coupon",
            "uncertainty",
        ),
    },
    "PCB-ER-B01": {
        "objects": (
            "介电常数",
            "介质损耗",
            "dissipation factor",
            "dielectric constant",
            "design dk",
            "test dk",
            "dk",
            "df",
        ),
        "denominators": (
            "test method",
            "测试方法",
            "ipc-tm-650",
            "spdr",
            "clamped stripline",
            "ghz",
            "mhz",
            "resin content",
            "树脂含量",
            "glass style",
            "样品厚度",
            "temperature",
            "humidity",
        ),
    },
    "PCB-ER-B02": {
        "objects": (
            "铜箔粗糙度",
            "copper foil roughness",
            "surface roughness",
            "surface profile",
            "hvlp",
            "vlp",
            "rtf",
            "rz",
            "ra",
            "rq",
            "rms roughness",
        ),
        "denominators": (
            "ghz",
            "mhz",
            "vna",
            "stripline",
            "microstrip",
            "insertion loss",
            "插入损耗",
            "插损",
            "mm",
            "mil",
            "simulation",
            "仿真",
            "measurement",
            "测量",
        ),
    },
}


@dataclass(frozen=True)
class RelevanceResult:
    selected: bool
    relevance_domains: tuple[str, ...]
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class UtilityResult:
    primary_classification: str
    traceable_source_types: tuple[str, ...]
    traceable_source_leads: tuple[str, ...]
    classification_reason: str
    prohibited_use: str


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


def classify_utility(*, title: str, body_text: str) -> UtilityResult:
    text = f"{title}\n{body_text}"
    doi_leads = tuple(
        sorted(
            {
                match.rstrip(".,;。；）)")
                for match in re.findall(
                    r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
                    text,
                    flags=re.IGNORECASE,
                )
            }
        )
    )
    standard_leads = tuple(
        sorted(
            {
                match.strip().rstrip(".,;。；")
                for match in re.findall(
                    r"(?:IPC|IEEE|OIF|PCIe?)[-\s][A-Z0-9][A-Z0-9.\-/]*",
                    text,
                    flags=re.IGNORECASE,
                )
            }
        )
    )
    source_types = tuple(
        name
        for name, leads in (
            ("doi", doi_leads),
            ("standard_number", standard_leads),
        )
        if leads
    )
    leads = doi_leads + standard_leads
    investment = any(
        term in text
        for term in (
            "买入评级",
            "目标价",
            "盈利预测",
            "投资建议",
            "确定受益",
            "推荐评级",
        )
    )
    company_specific = any(
        term in text
        for term in (
            "公司公告",
            "年报",
            "客户认证",
            "公司产能",
            "公司收入",
            "产品收入",
        )
    )
    if investment and not leads:
        primary = "investment_opinion_non_evidence"
    elif leads:
        primary = "primary_source_lead"
    elif company_specific:
        primary = "company_evidence_lead"
    else:
        primary = "contextual_industry"
    validate_primary_classification(primary)
    return UtilityResult(
        primary_classification=primary,
        traceable_source_types=source_types,
        traceable_source_leads=leads,
        classification_reason=f"deterministic_rule:{primary}",
        prohibited_use=(
            "not_direct_evidence;not_er_sufficiency;"
            "not_company_conclusion;not_investment_conclusion"
        ),
    )


def map_er_dispositions(title: str, *, body_text: str) -> dict[str, str]:
    text = f"{title}\n{body_text}".casefold()
    mappings: dict[str, str] = {}
    for er_id, rule in ER_SIGNAL_RULES.items():
        object_match = any(term.casefold() in text for term in rule["objects"])
        denominator_match = any(
            term.casefold() in text for term in rule["denominators"]
        )
        if object_match and denominator_match:
            disposition = "source_discovery_only"
        elif object_match:
            disposition = "contextual_candidate"
        else:
            disposition = "not_relevant"
        validate_er_disposition(disposition)
        mappings[er_id] = disposition
    return mappings
