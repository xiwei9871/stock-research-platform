"""CAP-00 end-to-end chain: theme → node dossier → CAP-04..08 envelopes.

Stage-A skeleton: every stage answers an envelope; degraded stages return
``unknown``/``not_evaluated`` instead of breaking the chain.  The returned
``gap_backlog`` is the unified DATA-line interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from stock_research.capabilities.adapters import (
    cap03_orchestrate, cap04_tech_supply, cap05_value_economics,
    cap06_competition, cap07_changes, cap08_synthesis,
)
from stock_research.capabilities.contract import ResearchEnvelope, make_envelope


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
    errors: list[dict[str, str]] = []
    for case_path in case_paths:
        # P0-3: per-node isolation — one bad case degrades to an error
        # envelope; other nodes keep running.  as_of must match the case
        # exactly: there is no snapshot-reconstruction path yet, so later
        # case data must never answer an earlier-date envelope.
        try:
            from stock_research.chain_bottleneck import load_node_case

            case_meta = load_node_case(case_path)
            node_id = case_meta["node_id"]
            case_as_of = case_meta["as_of"]
            if case_as_of != as_of:
                raise ValueError(
                    f"as_of mismatch: request={as_of} case={case_as_of} "
                    "(no reconstructable snapshot)"
                )
            env4, dossier, dossier_by_code = cap04_tech_supply(
                case_path, dossier_dir, as_of, run_id,
            )
        except Exception as exc:
            err = make_envelope(
                "CAP-04", "node", Path(case_path).stem, as_of, run_id,
                status="not_evaluated",
                findings={"error": str(exc)},
                uncertainties=(f"node_case_error:{exc}",),
            )
            key = f"{Path(case_path).stem}__error"
            per_node[key] = {"CAP-04": err}
            errors.append({"case_path": case_path, "error": str(exc)})
            continue
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

    # P1: dedupe backlog by (node_id, kind, item, owner); retain the list of
    # capabilities that surfaced each gap.
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for node_id, envs in per_node.items():
        for cap, env in envs.items():
            for g in env.data_gaps:
                key = (node_id, g.kind, g.item, g.owner)
                row = deduped.setdefault(key, {
                    "node_id": node_id, "kind": g.kind, "item": g.item,
                    "owner": g.owner, "note": g.note,
                    "source_capabilities": [],
                })
                if cap not in row["source_capabilities"]:
                    row["source_capabilities"].append(cap)
    for g in env3.data_gaps:
        key = ("", g.kind, g.item, g.owner)
        row = deduped.setdefault(key, {
            "node_id": "", "kind": g.kind, "item": g.item,
            "owner": g.owner, "note": g.note,
            "source_capabilities": [],
        })
        if "CAP-03" not in row["source_capabilities"]:
            row["source_capabilities"].append("CAP-03")
    gap_backlog = list(deduped.values())

    return {
        "theme_id": theme_id,
        "as_of": as_of,
        "run_id": run_id,
        "envelopes": {"CAP-03": env3.to_dict()},
        "per_node": {
            n: {c: e.to_dict() for c, e in envs.items()}
            for n, envs in per_node.items()
        },
        "errors": errors,
        "gap_backlog": gap_backlog,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }
