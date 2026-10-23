"""CAP-07 versioned baselines + explainable change diff.

A baseline is the per-node snapshot of a completed chain run: capability
statuses, node verdict, claim verdicts, economics states, fingerprints.
Baselines are append-only versioned JSON — replayable and diffable, not
just a fingerprint hash.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from stock_research.atomic_json import atomic_write_json


def _store_path(store_root: str | Path, node_id: str) -> Path:
    return Path(store_root) / f"{node_id}_baselines.json"


def load_baselines(store_root: str | Path, node_id: str) -> list[dict[str, Any]]:
    p = _store_path(store_root, node_id)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("versions", [])


# Self-referential / derived run states — never part of research-fact
# identity.  CAP-07 reports its own diff state; CAP-08's status is a
# deterministic function of the upstream envelopes (real changes already
# surface via claims/economics/evidence diffs).
_DERIVED_CAPS = {"CAP-07", "CAP-08"}


def _snapshot_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Research-fact identity used for dedupe.  Derived run metadata —
    envelope fingerprints (CAP-07's own fp embeds its diff output, so
    keeping it would force a new version every run) and CAP-07/CAP-08
    statuses — are excluded; only substantive facts version history."""
    content = {k: v for k, v in snapshot.items()
               if k not in {"version", "saved_at", "envelope_fingerprints"}}
    caps = dict(content.get("cap_statuses") or {})
    for c in _DERIVED_CAPS:
        caps.pop(c, None)
    content["cap_statuses"] = caps
    return content


def _eligible_baselines(
    versions: Sequence[dict[str, Any]], as_of: str | None,
) -> list[dict[str, Any]]:
    """Only baselines at or before ``as_of`` may serve as comparison —
    a historical replay must never diff against future-dated state."""
    if not as_of:
        return list(versions)
    return [v for v in versions
            if str(v.get("as_of") or "") <= str(as_of)]


def save_baseline(
    store_root: str | Path,
    node_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Append a versioned baseline (atomic replace).  Content-identical
    re-runs are NOT appended — dedupe is checked against the newest
    PIT-eligible baseline (as_of <= snapshot.as_of), so replaying an
    older date never collapses newer history and newer baselines are
    never overwritten."""
    p = _store_path(store_root, node_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    versions = load_baselines(store_root, node_id)
    eligible = _eligible_baselines(versions, snapshot.get("as_of"))
    if eligible and _snapshot_content(eligible[-1]) == _snapshot_content(snapshot):
        return {**eligible[-1], "deduped": True}
    record = {
        "version": len(versions) + 1,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **snapshot,
    }
    versions.append(record)
    atomic_write_json(p, {
        "node_id": node_id, "versions": versions,
    })
    return record


def snapshot_from_node_chain(
    dossier: dict[str, Any],
    envelopes: dict[str, Any],
) -> dict[str, Any]:
    """Extract the diffable summary from one node's chain output."""
    claims = {}
    for c in dossier.get("node_claims", []):
        claims[c["claim_id"]] = {
            "verdict": c.get("verdict"),
            "role": c.get("claim_role"),
        }
    econ = {}
    vm = dossier.get("value_matrix") or {}
    for row in vm.get("rows") or []:
        econ[row["stock_code"]] = {
            "revenue": _cell(row.get("revenue_profit")),
            "delivery": _cell(row.get("validation_delivery")),
            "order": _cell(row.get("verified_orders")),
            # sourced product-line revenue/margin VALUES (not just state)
            # — a real change in disclosed numbers is a research change.
            "revenue_facts": _revenue_facts(row.get("revenue_profit")),
        }
    def _attr(e: Any, key: str) -> Any:
        return e.get(key) if isinstance(e, dict) else getattr(e, key, None)

    from stock_research.capabilities.reasoning import hypothesis_state_map
    ev_index = {e["evidence_id"]: e
                for e in dossier.get("evidence_matrix", [])}
    return {
        "as_of": dossier.get("as_of"),
        "dossier_fingerprint": dossier.get("dossier_fingerprint"),
        "node_verdict": (dossier.get("conclusion") or {}).get("node_verdict"),
        "claims": claims,
        # R2A: hypothesis assessment states are research facts — a state
        # flip (e.g. unresolved → contested) versions the baseline.
        "hypotheses": hypothesis_state_map(
            dossier.get("node_claims") or [], ev_index),
        "economics": econ,
        "evidence_refs": sorted(
            r["evidence_id"] for r in dossier.get("evidence_matrix", [])
        ),
        "cap_statuses": {cap: _attr(e, "status") for cap, e in envelopes.items()},
        "envelope_fingerprints": {
            cap: _attr(e, "fingerprint") for cap, e in envelopes.items()},
    }


def _diff_maps(
    prev_map: dict[str, Any], cur_map: dict[str, Any], prefix: str,
) -> list[dict[str, Any]]:
    """added / removed / changed entries over a flat dict of leaf values."""
    changes: list[dict[str, Any]] = []
    for key, cur in cur_map.items():
        if key not in prev_map:
            changes.append({"kind": "added", "field": f"{prefix}:{key}",
                            "from": None, "to": cur})
        elif prev_map[key] != cur:
            changes.append({"kind": "changed", "field": f"{prefix}:{key}",
                            "from": prev_map[key], "to": cur})
    for key in prev_map:
        if key not in cur_map:
            changes.append({"kind": "removed", "field": f"{prefix}:{key}",
                            "from": prev_map[key], "to": None})
    return changes


def diff_baselines(
    current: dict[str, Any],
    baselines: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Explainable diff vs the newest PIT-eligible baseline — added /
    removed / changed across claims, companies (economics incl. sourced
    revenue/margin facts), evidence refs, node verdict and capability
    statuses.  CAP-07/CAP-08 self/derived statuses are excluded;
    future-dated baselines never participate."""
    eligible = _eligible_baselines(baselines, current.get("as_of"))
    if not eligible:
        return {"baseline_found": False, "changes": [],
                "skipped_future_versions": len(baselines)}
    prev = eligible[-1]
    changes: list[dict[str, Any]] = []
    changes += _diff_maps(
        {"node_verdict": prev.get("node_verdict")},
        {"node_verdict": current.get("node_verdict")}, "node")
    changes += _diff_maps(
        {k: v.get("verdict") for k, v in (prev.get("claims") or {}).items()},
        {k: v.get("verdict") for k, v in current.get("claims", {}).items()},
        "claim")
    changes += _diff_maps(
        prev.get("hypotheses") or {}, current.get("hypotheses") or {},
        "hypothesis")
    changes += _diff_maps(
        {f"{c}.{cell}": v for c, cells in (prev.get("economics") or {}).items()
         for cell, v in cells.items()},
        {f"{c}.{cell}": v for c, cells in current.get("economics", {}).items()
         for cell, v in cells.items()},
        "econ")
    changes += _diff_maps(
        {e: True for e in (prev.get("evidence_refs") or [])},
        {e: True for e in current.get("evidence_refs", [])},
        "evidence_ref")
    prev_caps = {k: v for k, v in (prev.get("cap_statuses") or {}).items()
                 if k not in _DERIVED_CAPS}
    cur_caps = {k: v for k, v in (current.get("cap_statuses") or {}).items()
                if k not in _DERIVED_CAPS}
    changes += _diff_maps(prev_caps, cur_caps, "cap_status")
    return {
        "baseline_found": True,
        "baseline_version": prev.get("version"),
        "baseline_as_of": prev.get("as_of"),
        "skipped_future_versions": len(baselines) - len(eligible),
        "state_changed": bool(changes),
        "changes": changes,
        "added": sum(1 for c in changes if c["kind"] == "added"),
        "removed": sum(1 for c in changes if c["kind"] == "removed"),
        "changed": sum(1 for c in changes if c["kind"] == "changed"),
    }


def _cell(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("state") or "missing")
    return str(v or "missing")


def _revenue_facts(cell: Any) -> list[dict[str, Any]]:
    """Compact sourced revenue/margin facts from a matrix cell — diffable
    values, not just disclosure state."""
    if not isinstance(cell, dict):
        return []
    facts = []
    for f in cell.get("facts") or []:
        facts.append({
            "product_line": f.get("product_line") or f.get("label"),
            "period": f.get("period"),
            "revenue": f.get("revenue"),
            "gross_margin": f.get("gross_margin"),
            "scope": f.get("scope"),
            "source_id": f.get("source_id"),
        })
    return sorted(facts, key=lambda x: (str(x["product_line"]), str(x["period"])))
