"""CAP-00 end-to-end chain: theme → node dossier → CAP-04..08 envelopes.

Stage-A skeleton: every stage answers an envelope; degraded stages return
``unknown``/``not_evaluated`` instead of breaking the chain.  The returned
``gap_backlog`` is the unified DATA-line interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from stock_research.capabilities.adapters import (
    cap03_orchestrate, cap03_orchestrate_theme, cap04_tech_supply,
    cap05_value_economics, cap06_competition, cap07_changes,
    cap08_synthesis,
)
from stock_research.capabilities.baseline import (
    load_baselines, save_baseline, snapshot_from_node_chain,
)
from stock_research.capabilities.contract import ResearchEnvelope, make_envelope
from stock_research.capabilities.workbench import write_workbench_index


def _node_snapshot(dossier: dict[str, Any],
                   envelopes: dict[str, ResearchEnvelope]) -> dict[str, Any]:
    return snapshot_from_node_chain(dossier, envelopes)


def run_research_chain(
    theme_id: str,
    case_paths: Sequence[str],
    dossier_dir: str,
    as_of: str,
    run_id: str,
    baseline_dir: str | None = None,
    workbench_dir: str | None = None,
) -> dict[str, Any]:
    """Run one theme through the CAP-03..08 chain.  Returns envelopes +
    unified DATA gap backlog.  Never raises on missing data — every gap
    surfaces as an envelope status + backlog entry.  ``baseline_dir`` /
    ``workbench_dir`` opt into persisted baselines / workbench index."""
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
            if case_as_of > as_of:
                raise ValueError(
                    f"as_of violation: case data {case_as_of} postdates "
                    f"request {as_of} (no reconstructable snapshot)"
                )
            # Envelopes are labeled with the case's own PIT — an earlier
            # evidence cutoff answering a later request is honest; the
            # reverse is prohibited.
            env_as_of = case_as_of
            env4, dossier, dossier_by_code = cap04_tech_supply(
                case_path, dossier_dir, env_as_of, run_id,
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
        env5 = cap05_value_economics(node_id, dossier, env_as_of, run_id,
                                     upstream_fingerprints=[env4.fingerprint])
        env6 = cap06_competition(node_id, dossier, dossier_by_code, env_as_of, run_id,
                                 upstream_fingerprints=[env4.fingerprint, env5.fingerprint])
        node_envs = {
            "CAP-04": env4, "CAP-05": env5, "CAP-06": env6,
        }
        # CAP-07: versioned baseline snapshot + explainable content diff.
        snapshot = _node_snapshot(dossier, node_envs)
        prior = load_baselines(baseline_dir, node_id) if baseline_dir else []
        env7 = cap07_changes(node_id, snapshot, prior, env_as_of, run_id)
        env8 = cap08_synthesis(
            node_id, [env4, env5, env6, env7], env_as_of, run_id,
        )
        node_envs["CAP-07"], node_envs["CAP-08"] = env7, env8
        if baseline_dir:
            save_baseline(baseline_dir, node_id, {
                **snapshot,
                "cap_statuses": {c: e.status for c, e in node_envs.items()},
                "envelope_fingerprints": {c: e.fingerprint for c, e in node_envs.items()},
            })
        per_node[node_id] = node_envs

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

    out: dict[str, Any] = {}

    out = {
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
    # R2A: theme-level structured research summary (findings /
    # competing hypotheses / unresolved / next verification / coverage).
    from stock_research.capabilities.reasoning import theme_synthesis
    out["theme_synthesis"] = theme_synthesis(
        {n: {c: e.to_dict() for c, e in envs.items()}
         for n, envs in per_node.items()},
        env3.findings,
    )
    if workbench_dir:
        out["workbench_index"] = write_workbench_index(out, workbench_dir)
    return out


def run_theme_chain(
    theme_id: str,
    dossier_dir: str,
    as_of: str,
    run_id: str,
    case_dir: str = "docs/cap02/cases",
    baseline_dir: str | None = None,
    workbench_dir: str | None = None,
) -> dict[str, Any]:
    """R1: theme-DB-driven chain.  CAP-03 reads the theme package + company
    mappings, auto-discovers runnable node cases, then runs CAP-04..08 per
    matched case.  Nodes without cases stay in the CAP-03 gap list — no
    silent skipping."""
    env3 = cap03_orchestrate_theme(theme_id, as_of, run_id, case_dir=case_dir)
    case_paths: list[str] = []
    for n in env3.findings.get("nodes", []):
        for m in n.get("runnable_cases", []):
            p = m["path"] if isinstance(m, dict) else m
            if p not in case_paths:
                case_paths.append(p)
    # Inner run must NOT write the index yet — the CAP-03 envelope and gap
    # backlog are finalized here first, THEN the workbench index reflects
    # the final research state.
    out = run_research_chain(
        theme_id, case_paths, dossier_dir, as_of, run_id,
        baseline_dir=baseline_dir, workbench_dir=None,
    )
    out["envelopes"]["CAP-03"] = env3.to_dict()
    for g in env3.data_gaps:
        out["gap_backlog"].append({
            "node_id": "", "kind": g.kind, "item": g.item,
            "owner": g.owner, "note": g.note,
            "source_capabilities": ["CAP-03"],
        })
    # Theme summary must reflect the theme-library CAP-03 (coverage),
    # not the inner case-list envelope.
    from stock_research.capabilities.reasoning import theme_synthesis
    out["theme_synthesis"] = theme_synthesis(
        out["per_node"], env3.findings)
    if workbench_dir:
        out["workbench_index"] = write_workbench_index(out, workbench_dir)
    return out
