"""CAP-R2C P0a — machine-readable stage-trace integrity audit.

For every ``(node, company, stage)`` in a generated chain output, verify
that each trace element actually resolves: ``record_id`` exists in the
T3 record store or a company dossier's evidence matrix, ``source_id``
maps to a known source document, ``review_status`` / ``scope`` /
``effective_as_of`` are parseable.  A ``confirmed`` stage whose trace
cannot resolve is a gate breach; an unconfirmed stage with an empty or
partial trace is an expected gap, not a fault.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

VALID_REVIEW_STATUSES = {
    "accepted", "verified", "pending_review", "rejected",
    "needs_review", "superseded",
}
_DATE_RE = re.compile(r"^\d{4}(-\d{2})?(-\d{2})?([T ].*)?$")


def _date_ok(v: Any) -> bool:
    return isinstance(v, str) and bool(_DATE_RE.match(v.strip()))


def build_trace_resolver(
    t3_records_path: str | Path | None = None,
    dossier_dir: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    extra_records: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Collect the ID spaces a trace row may resolve against.

    ``records``   — T3 store rows (segment/order/customer/rival/...).
    ``evidence``  — dossier evidence_matrix rows keyed by evidence_id.
    ``sources``   — every resolvable source_id across T3 rows, dossier
                    evidence, and the T3 source manifest.
    """
    records: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    sources: set[str] = set()

    if t3_records_path:
        doc = json.loads(Path(t3_records_path).read_text(encoding="utf-8"))
        rows = doc if isinstance(doc, list) else [
            r for lst in doc.values() if isinstance(lst, list) for r in lst]
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = r.get("record_id")
            if rid:
                records[rid] = r
            if r.get("source_id"):
                sources.add(r["source_id"])

    for r in extra_records:
        if isinstance(r, dict) and r.get("record_id"):
            records[r["record_id"]] = r
            if r.get("source_id"):
                sources.add(r["source_id"])

    if dossier_dir:
        for p in Path(dossier_dir).glob("*_dossier.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for e in d.get("evidence_matrix") or []:
                eid = e.get("evidence_id")
                if not eid:
                    continue
                evidence[eid] = e
                if e.get("source_id"):
                    sources.add(e["source_id"])

    if source_manifest_path:
        try:
            m = json.loads(Path(source_manifest_path).read_text(
                encoding="utf-8"))
            for s in m.get("sources") or []:
                if s.get("source_id"):
                    sources.add(s["source_id"])
        except Exception:
            pass

    return {"records": records, "evidence": evidence, "sources": sources}


def _check_element(el: dict[str, Any], resolver: dict[str, Any],
                   ) -> list[str]:
    """Return unresolved-problem tokens for one trace element."""
    problems: list[str] = []
    rid = el.get("record_id")
    sid = el.get("source_id")
    if not rid:
        problems.append("record_id:<missing>")
    elif rid not in resolver["records"] and rid not in resolver["evidence"]:
        problems.append(f"record_id:{rid}")
    if not sid:
        problems.append("source_id:<missing>")
    elif sid not in resolver["sources"]:
        problems.append(f"source_id:{sid}")
    rs = el.get("review_status")
    if rs not in VALID_REVIEW_STATUSES:
        problems.append(f"review_status:{rs!r}")
    if not el.get("scope"):
        problems.append("scope:<missing>")
    if not _date_ok(el.get("effective_as_of")):
        problems.append(f"effective_as_of:{el.get('effective_as_of')!r}")
    return problems


def validate_stage_traces(
    theme_output: dict[str, Any],
    resolver: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate every stage's evidence trace.  One row per
    (node, company_code, stage) combination."""
    rows: list[dict[str, Any]] = []
    for node_id, envs in (theme_output.get("per_node") or {}).items():
        eco = (((envs.get("CAP-05") or {}).get("findings") or {})
               .get("economics") or {})
        for code, entry in eco.items():
            a = (entry or {}).get("commercialization_assessment") or {}
            for stage, sev in (a.get("stage_evidence") or {}).items():
                trace = sev.get("trace") or []
                unresolved: list[str] = []
                resolved_n = 0
                for el in trace:
                    probs = _check_element(el, resolver)
                    unresolved.extend(probs)
                    if not probs:
                        resolved_n += 1
                confirmed = bool(sev.get("confirmed"))
                complete = bool(trace) and resolved_n == len(trace)
                breach = confirmed and resolved_n == 0
                rows.append({
                    "node_id": node_id,
                    "company_code": code,
                    "stage": stage,
                    "confirmed": confirmed,
                    "trace_elements": len(trace),
                    "resolved_elements": resolved_n,
                    "trace_complete": complete,
                    "gate_breach": breach,
                    "unresolved": unresolved,
                    "classification": (
                        "resolved" if complete else
                        "gate_breach" if breach else
                        "partial_trace" if confirmed else
                        "expected_gap"),
                })
    return rows


def summarize_trace_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cls: dict[str, int] = {}
    for r in rows:
        cls[r["classification"]] = cls.get(r["classification"], 0) + 1
    return {
        "stage_rows": len(rows),
        "confirmed_rows": sum(1 for r in rows if r["confirmed"]),
        "gate_breaches": [f"{r['node_id']}/{r['company_code']}/{r['stage']}"
                          for r in rows if r["gate_breach"]],
        "partial_trace_confirmed":
            [f"{r['node_id']}/{r['company_code']}/{r['stage']}"
             for r in rows if r["classification"] == "partial_trace"],
        "by_classification": cls,
    }
