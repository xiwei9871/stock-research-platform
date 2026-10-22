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


def _store_path(store_root: str | Path, node_id: str) -> Path:
    return Path(store_root) / f"{node_id}_baselines.json"


def load_baselines(store_root: str | Path, node_id: str) -> list[dict[str, Any]]:
    p = _store_path(store_root, node_id)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("versions", [])


def save_baseline(
    store_root: str | Path,
    node_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Append a versioned baseline.  Returns the stored record."""
    p = _store_path(store_root, node_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    versions = load_baselines(store_root, node_id)
    record = {
        "version": len(versions) + 1,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **snapshot,
    }
    versions.append(record)
    p.write_text(json.dumps({
        "node_id": node_id, "versions": versions,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
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
        "cap_statuses": {cap: _attr(e, "status") for cap, e in envelopes.items()},
        "envelope_fingerprints": {
            cap: _attr(e, "fingerprint") for cap, e in envelopes.items()},
    }


def diff_baselines(
    current: dict[str, Any],
    baselines: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Explainable diff vs the most recent baseline — content changes, not
    just fingerprint inequality."""
    if not baselines:
        return {"baseline_found": False, "changes": []}
    prev = baselines[-1]
    changes: list[dict[str, Any]] = []
    if prev.get("node_verdict") != current.get("node_verdict"):
        changes.append({
            "field": "node_verdict",
            "from": prev.get("node_verdict"), "to": current.get("node_verdict"),
        })
    for cid, cur in current.get("claims", {}).items():
        old = (prev.get("claims") or {}).get(cid)
        if old is None:
            changes.append({"field": f"claim:{cid}", "from": None,
                            "to": cur.get("verdict")})
        elif old.get("verdict") != cur.get("verdict"):
            changes.append({"field": f"claim:{cid}",
                            "from": old.get("verdict"), "to": cur.get("verdict")})
    for code, cur in current.get("economics", {}).items():
        old = (prev.get("economics") or {}).get(code) or {}
        for cell, v in cur.items():
            if old.get(cell) != v:
                changes.append({"field": f"econ:{code}.{cell}",
                                "from": old.get(cell), "to": v})
    for cap, st in current.get("cap_statuses", {}).items():
        old_st = (prev.get("cap_statuses") or {}).get(cap)
        if old_st != st:
            changes.append({"field": f"cap_status:{cap}",
                            "from": old_st, "to": st})
    return {
        "baseline_found": True,
        "baseline_version": prev.get("version"),
        "baseline_as_of": prev.get("as_of"),
        "state_changed": bool(changes),
        "changes": changes,
    }


def _cell(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("state") or "missing")
    return str(v or "missing")
