from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import pandas as pd
from pypdf import PdfReader


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


@dataclass(frozen=True)
class TriageRunResult:
    queue_rows_considered: int
    selected_source_records: int
    selected_content_identities: int
    duplicate_source_records: int
    output_paths: tuple[Path, ...]


def validate_primary_classification(value: str) -> None:
    if value not in PRIMARY_CLASSIFICATIONS:
        raise ValueError(f"unsupported primary classification: {value}")


def validate_er_disposition(value: str) -> None:
    if value not in ER_DISPOSITIONS:
        raise ValueError(f"unsupported ER disposition: {value}")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(path: Path) -> tuple[str, str]:
    try:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001 - unreadable files remain auditable.
        return "", f"unreadable:{type(exc).__name__}"
    return text, "readable" if text else "empty_text"


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
        domain: tuple(signal for signal in signals if _contains_signal(haystack, signal))
        for domain, signals in DOMAIN_SIGNALS.items()
    }
    pcb_context = any(
        _contains_signal(haystack, signal)
        for signal in (
            "pcb",
            "印制电路板",
            "高速pcb",
            "高多层板",
            "hdi",
            "msap",
            "覆铜板",
            "ccl",
            "铜箔",
            "hvlp",
            "vlp",
            "rtf",
        )
    )
    copper_context = any(
        _contains_signal(haystack, signal)
        for signal in ("铜箔", "copper foil", "hvlp", "vlp", "rtf")
    )
    copper_specific = {"铜箔", "hvlp", "vlp", "rtf", "surface profile"}
    if matches["copper_foil"] and not (
        copper_context or copper_specific.intersection(matches["copper_foil"])
    ):
        matches["copper_foil"] = ()
    manufacturing_specific = {
        "背钻",
        "压合",
        "层间对位",
        "直接成像",
        "pcb主轴",
        "pcb设备",
    }
    if matches["manufacturing_and_test"] and not (
        pcb_context
        or manufacturing_specific.intersection(matches["manufacturing_and_test"])
    ):
        matches["manufacturing_and_test"] = ()
    domains = tuple(sorted(domain for domain, signals in matches.items() if signals))
    signals = tuple(sorted({signal for domain in domains for signal in matches[domain]}))
    return RelevanceResult(
        selected=bool(domains),
        relevance_domains=domains,
        matched_signals=signals,
    )


def _contains_signal(text: str, signal: str) -> bool:
    normalized = signal.casefold()
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._+\-/]*", normalized):
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])",
                text,
            )
        )
    return normalized in text


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


def _resolve_pdf_path(value: object, *, input_dir: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("downloaded manifest row has no pdf_path")
    candidate = Path(raw).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate
    direct = Path.cwd() / candidate
    if direct.exists():
        return direct.resolve()
    relative_to_input = input_dir / candidate
    if relative_to_input.exists():
        return relative_to_input.resolve()
    raise FileNotFoundError(f"manifest PDF does not exist: {raw}")


def _publication_date_status(value: object) -> str:
    return "provided_in_queue" if str(value or "").strip() else "unknown"


def _stringify_sequence(value: object) -> str:
    if isinstance(value, (tuple, list, set)):
        return "|".join(str(item) for item in value)
    return str(value or "")


def _build_triage_rows(
    *,
    queue: pd.DataFrame,
    manifest: pd.DataFrame,
    input_dir: Path,
) -> tuple[list[dict[str, object]], list[Path]]:
    queue_by_uuid = {
        str(row.get("uuid") or ""): row
        for row in queue.fillna("").to_dict("records")
    }
    rows: list[dict[str, object]] = []
    inspected_pdfs: list[Path] = []
    downloaded_rows = manifest.loc[
        manifest["status"].astype(str).eq("downloaded")
    ].fillna("").to_dict("records")
    for manifest_row in downloaded_rows:
        uuid = str(manifest_row.get("uuid") or "")
        queue_row = queue_by_uuid.get(uuid)
        source_row = dict(manifest_row)
        if queue_row is not None:
            source_row.update(queue_row)
        pdf_path = _resolve_pdf_path(manifest_row.get("pdf_path"), input_dir=input_dir)
        inspected_pdfs.append(pdf_path)
        body_text, body_status = extract_pdf_text(pdf_path)
        relevance = classify_relevance(source_row, body_text=body_text)
        if not relevance.selected:
            continue
        title = str(source_row.get("report_title") or source_row.get("title") or "")
        utility = classify_utility(title=title, body_text=body_text)
        er_mappings = map_er_dispositions(title, body_text=body_text)
        content_hash = sha256_path(pdf_path)
        row: dict[str, object] = {
            "uuid": uuid,
            "report_title": title,
            "queue_kind": str(source_row.get("queue_kind") or "formal"),
            "stock_name": str(source_row.get("stock_name") or ""),
            "ts_code": str(source_row.get("ts_code") or ""),
            "broker": str(source_row.get("broker") or source_row.get("org_name") or ""),
            "publisher": str(source_row.get("org_name") or source_row.get("broker") or ""),
            "publish_date": str(source_row.get("publish_date") or ""),
            "publication_date_status": _publication_date_status(source_row.get("publish_date")),
            "local_pdf_path": str(pdf_path),
            "content_sha256": content_hash,
            "body_review_status": body_status,
            "body_char_count": len(body_text),
            "relevance_domains": relevance.relevance_domains,
            "matched_signals": relevance.matched_signals,
            "primary_classification": utility.primary_classification,
            "classification_reason": utility.classification_reason,
            "traceable_source_types": utility.traceable_source_types,
            "traceable_source_leads": utility.traceable_source_leads,
            "prohibited_use": utility.prohibited_use,
            "PCB-ER-A02": er_mappings["PCB-ER-A02"],
            "PCB-ER-A04": er_mappings["PCB-ER-A04"],
            "PCB-ER-B01": er_mappings["PCB-ER-B01"],
            "PCB-ER-B02": er_mappings["PCB-ER-B02"],
            "manual_review_priority": (
                "P0"
                if utility.primary_classification == "primary_source_lead"
                else "P1"
                if "source_discovery_only" in er_mappings.values()
                else "P2"
            ),
            "limitations": (
                "sell_side_secondary_source;trace_original_source_before_evidence_use"
            ),
        }
        rows.append(row)
    return rows, inspected_pdfs


def _validate_selected_frame(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise ValueError("triage selected no report identities")
    if not frame["content_identity"].is_unique:
        raise ValueError("content identities are not unique")
    for value in frame["primary_classification"].astype(str):
        validate_primary_classification(value)
    for column in ("PCB-ER-A02", "PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02"):
        for value in frame[column].astype(str):
            validate_er_disposition(value)


def _serializable_selected(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in (
        "source_record_uuids",
        "relevance_domains",
        "matched_signals",
        "traceable_source_types",
        "traceable_source_leads",
    ):
        output[column] = output[column].map(_stringify_sequence)
    return output.sort_values(
        ["manual_review_priority", "primary_classification", "report_title", "content_identity"]
    ).reset_index(drop=True)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _atomic_write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        frame.to_csv(handle, index=False)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _distribution(frame: pd.DataFrame, column: str) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in frame[column].value_counts().sort_index().to_dict().items()
    }


def _build_audit_payload(
    *,
    before_hashes: Mapping[str, str],
    queue: pd.DataFrame,
    selected_source_records: int,
    selected: pd.DataFrame,
    formal_queue_missing_download_count: int,
    replacement_download_count: int,
) -> dict[str, object]:
    er_distributions = {
        er_id: _distribution(selected, er_id)
        for er_id in ("PCB-ER-A02", "PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02")
    }
    duplicate_records = selected_source_records - len(selected)
    records = _serializable_selected(selected).fillna("").to_dict("records")
    return {
        "artifact_type": "ai_pcb_yanbaoke_evidence_triage_audit",
        "artifact_version": "1.0.0",
        "execution_mode": "offline_read_only_triage",
        "input_hashes": dict(sorted(before_hashes.items())),
        "queue_rows_considered": int(len(queue)),
        "selected_source_records": int(selected_source_records),
        "selected_content_identities": int(len(selected)),
        "duplicate_source_records": int(duplicate_records),
        "formal_queue_missing_download_count": int(formal_queue_missing_download_count),
        "replacement_download_count": int(replacement_download_count),
        "primary_classification_distribution": _distribution(
            selected, "primary_classification"
        ),
        "er_disposition_distribution": er_distributions,
        "selected_records": records,
        "validation": {
            "counts_reconciled": selected_source_records == len(selected) + duplicate_records,
            "content_identities_unique": bool(selected["content_identity"].is_unique),
            "direct_evidence_state_count": 0,
            "er_sufficiency_state_count": 0,
        },
        "evidence_assessment_updated": False,
        "cognition_updated": False,
        "database_written": False,
        "network_access_used": False,
    }


def render_summary(audit: Mapping[str, object]) -> str:
    classifications = json.dumps(
        audit["primary_classification_distribution"],
        ensure_ascii=False,
        sort_keys=True,
    )
    er_dispositions = audit["er_disposition_distribution"]
    lines = [
        "# AI PCB Yanbaoke Evidence Triage v1",
        "",
        f"- Queue rows considered: {audit['queue_rows_considered']}",
        f"- Selected source records: {audit['selected_source_records']}",
        f"- Selected content identities: {audit['selected_content_identities']}",
        f"- Duplicate source records collapsed: {audit['duplicate_source_records']}",
        f"- Primary classifications: {classifications}",
        "- Evidence Assessment updated: no",
        "- Cognition package updated: no",
        "",
        "## Technical ER lead dispositions",
        "",
    ]
    for er_id in ("PCB-ER-A02", "PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02"):
        lines.append(
            f"- {er_id}: {json.dumps(er_dispositions[er_id], ensure_ascii=False, sort_keys=True)}"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "All mappings are source-discovery or contextual leads. No selected broker report is treated as direct technical evidence, an independent evidence chain, or proof that an Evidence Requirement is sufficient.",
            "",
            "Company, capacity, benefit, valuation, and recommendation statements require separate primary-source verification and are not technical evidence in this audit.",
            "",
        ]
    )
    return "\n".join(lines)


def run_triage(
    *,
    input_dir: Path,
    output_dir: Path,
    expected_queue_rows: int = 474,
) -> TriageRunResult:
    queue_path = input_dir / "yanbaoke_download_queue_474.csv"
    mappings_path = input_dir / "theme_company_mappings.csv"
    manifest_path = input_dir / "download" / "yanbaoke_direct_uuid_downloads.csv"
    replacement_path = input_dir / "yanbaoke_replacement_queue.csv"
    input_paths = (queue_path, mappings_path, manifest_path) + (
        (replacement_path,) if replacement_path.exists() else ()
    )
    before_hashes = {str(path): sha256_path(path) for path in input_paths}
    queue = pd.read_csv(queue_path, dtype=object).fillna("")
    pd.read_csv(mappings_path, dtype=object).fillna("")
    manifest = pd.read_csv(manifest_path, dtype=object).fillna("")
    if len(queue) != expected_queue_rows:
        raise ValueError(
            f"expected {expected_queue_rows} queue rows, found {len(queue)}"
        )
    downloaded = manifest.loc[manifest["status"].astype(str).eq("downloaded")].copy()
    queue_uuids = set(queue["uuid"].astype(str))
    downloaded_uuids = set(downloaded["uuid"].astype(str))
    missing_formal_uuids = queue_uuids - downloaded_uuids
    replacement_uuids = downloaded_uuids - queue_uuids
    if len(missing_formal_uuids) != len(replacement_uuids):
        raise ValueError(
            "formal/replacement download substitution is not one-for-one: "
            f"missing={len(missing_formal_uuids)} replacement={len(replacement_uuids)}"
        )
    if replacement_uuids:
        if not replacement_path.exists():
            raise ValueError("replacement downloads exist without replacement queue lineage")
        replacement_queue = pd.read_csv(replacement_path, dtype=object).fillna("")
        allowed_replacements = set(replacement_queue["uuid"].astype(str))
        unknown_replacements = replacement_uuids - allowed_replacements
        if unknown_replacements:
            raise ValueError(
                "download manifest contains replacements absent from replacement queue: "
                + ",".join(sorted(unknown_replacements))
            )
    rows, inspected_pdfs = _build_triage_rows(
        queue=queue,
        manifest=manifest,
        input_dir=input_dir,
    )
    selected = pd.DataFrame(collapse_content_identities(rows))
    _validate_selected_frame(selected)
    serializable = _serializable_selected(selected)
    audit = _build_audit_payload(
        before_hashes=before_hashes,
        queue=queue,
        selected_source_records=len(rows),
        selected=selected,
        formal_queue_missing_download_count=len(missing_formal_uuids),
        replacement_download_count=len(replacement_uuids),
    )
    csv_path = output_dir / "ai_pcb_evidence_triage_v1.csv"
    audit_path = output_dir / "ai_pcb_evidence_triage_audit_v1.json"
    summary_path = output_dir / "ai_pcb_evidence_triage_summary_v1.md"
    _atomic_write_csv(csv_path, serializable)
    _atomic_write_text(
        audit_path,
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(summary_path, render_summary(audit))
    after_hashes = {str(path): sha256_path(path) for path in input_paths}
    if after_hashes != before_hashes:
        raise RuntimeError("upstream input drift detected")
    for pdf_path in inspected_pdfs:
        if not pdf_path.exists():
            raise RuntimeError(f"inspected PDF disappeared during audit: {pdf_path}")
    return TriageRunResult(
        queue_rows_considered=len(queue),
        selected_source_records=len(rows),
        selected_content_identities=len(selected),
        duplicate_source_records=len(rows) - len(selected),
        output_paths=(csv_path, audit_path, summary_path),
    )
