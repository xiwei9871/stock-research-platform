"""CAP-00 end-to-end chain: theme → node dossier → CAP-04..08 envelopes.

Stage-A skeleton: every stage answers an envelope; degraded stages return
``unknown``/``not_evaluated`` instead of breaking the chain.  The returned
``gap_backlog`` is the unified DATA-line interface.
"""

from __future__ import annotations

from typing import Any, Sequence

from stock_research.capabilities.adapters import (
    cap03_orchestrate, cap04_tech_supply, cap05_value_economics,
    cap06_competition, cap07_changes, cap08_synthesis,
)
from stock_research.capabilities.contract import ResearchEnvelope


def run_research_chain(
    theme_id: str,
    case_paths: Sequence[str],
    dossier_dir: str,
    as_of: str,
    run_id: str,
    baseline_fingerprints: dict[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Run one theme through the CAP-03..08 chain.  Returns envelopes +
    unified DATA gap backlog.  Never raises on missing data — every gap
    surfaces as an envelope status + backlog entry."""
    baselines = baseline_fingerprints or {}
    envelopes: dict[str, ResearchEnvelope] = {}

    env3 = cap03_orchestrate(theme_id, case_paths, as_of, run_id)
    envelopes["CAP-03"] = env3

    per_node: dict[str, dict[str, ResearchEnvelope]] = {}
    for case_path in case_paths:
        env4, dossier, dossier_by_code = cap04_tech_supply(
            case_path, dossier_dir, as_of, run_id,
        )
        node_id = dossier["node_id"]
        fp = dossier["dossier_fingerprint"]
        env5 = cap05_value_economics(node_id, dossier, as_of, run_id,
                                     upstream_fingerprints=[env4.fingerprint])
        env6 = cap06_competition(node_id, dossier, dossier_by_code, as_of, run_id,
                                 upstream_fingerprints=[env4.fingerprint, env5.fingerprint])
        env7 = cap07_changes(node_id, fp, baselines.get(node_id), as_of, run_id)
        env8 = cap08_synthesis(
            node_id, [env4, env5, env6, env7], as_of, run_id,
        )
        per_node[node_id] = {
            "CAP-04": env4, "CAP-05": env5, "CAP-06": env6,
            "CAP-07": env7, "CAP-08": env8,
        }

    gap_backlog = []
    for node_id, envs in per_node.items():
        for cap, env in envs.items():
            for g in env.data_gaps:
                gap_backlog.append({
                    "node_id": node_id, "capability": cap,
                    "kind": g.kind, "item": g.item,
                    "owner": g.owner, "note": g.note,
                })
    for g in env3.data_gaps:
        gap_backlog.append({
            "node_id": "", "capability": "CAP-03",
            "kind": g.kind, "item": g.item, "owner": g.owner, "note": g.note,
        })

    return {
        "theme_id": theme_id,
        "as_of": as_of,
        "run_id": run_id,
        "envelopes": {"CAP-03": env3.to_dict()},
        "per_node": {
            n: {c: e.to_dict() for c, e in envs.items()}
            for n, envs in per_node.items()
        },
        "gap_backlog": gap_backlog,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }
