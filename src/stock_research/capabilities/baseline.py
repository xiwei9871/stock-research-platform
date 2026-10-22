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


def _snapshot_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Content used for dedupe — everything except bookkeeping fields."""
    return {k: v for k, v in snapshot.items()
            if k not in {"version", "saved_at"}}


def save_baseline(
    store_root: str | Path,
    node_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Append a versioned baseline (atomic replace).  Identical content
    re-runs are NOT appended — returns the existing last version with
    ``deduped=True`` instead of growing history with no change."""
    p = _store_path(store_root, node_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    versions = load_baselines(store_root, node_id)
    if versions and _snapshot_content(versions[-1]) == _snapshot_content(snapshot):
        return {**versions[-1], "deduped": True}
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
        }
    def _attr(e: Any, key: str) -> Any:
        return e.get(key) if isinstance(e, dict) else getattr(e, key, None)

    return {
        "as_of": dossier.get("as_of"),
        "dossier_fingerprint": dossier.get("dossier_fingerprint"),
        "node_verdict": (dossier.get("conclusion") or {}).get("node_verdict"),
        "claims": claims,
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
    """Explainable diff vs the most recent baseline — added / removed /
    changed across claims, companies (economics), evidence refs, node
    verdict and capability statuses."""
    if not baselines:
        return {"baseline_found": False, "changes": []}
    prev = baselines[-1]
    changes: list[dict[str, Any]] = []
    changes += _diff_maps(
        {"node_verdict": prev.get("node_verdict")},
        {"node_verdict": current.get("node_verdict")}, "node")
    changes += _diff_maps(
        {k: v.get("verdict") for k, v in (prev.get("claims") or {}).items()},
        {k: v.get("verdict") for k, v in current.get("claims", {}).items()},
        "claim")
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
    changes += _diff_maps(
        prev.get("cap_statuses") or {}, current.get("cap_statuses") or {},
        "cap_status")
    return {
        "baseline_found": True,
        "baseline_version": prev.get("version"),
        "baseline_as_of": prev.get("as_of"),
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
