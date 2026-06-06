from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchInfraArtifactIndexRecord:
    run_id: str
    run_type: str
    trade_date: str
    strategy_variant: str
    created_at: str
    research_infra_dir: str
    run_card_json_path: str
    research_signals_json_path: str
    attribution_cards_json_path: str
    attribution_cards_md_path: str
    experiment_registry_path: str
    metrics: dict[str, Any]
    warnings: list[str]
    caveats: list[str]


def export_artifact_index_record(
    record: ResearchInfraArtifactIndexRecord,
) -> dict[str, Any]:
    return dict(sorted(asdict(record).items()))


def append_artifact_index_record(
    path: str | Path,
    record: ResearchInfraArtifactIndexRecord,
) -> None:
    index_path = Path(path)
    existing_records = read_artifact_index(index_path)
    record_key = (record.run_id, record.research_infra_dir)
    existing_keys = {
        (existing.run_id, existing.research_infra_dir)
        for existing in existing_records
    }
    if record_key in existing_keys:
        return

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                export_artifact_index_record(record),
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def read_artifact_index(path: str | Path) -> list[ResearchInfraArtifactIndexRecord]:
    index_path = Path(path)
    if not index_path.exists():
        return []

    records: list[ResearchInfraArtifactIndexRecord] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(ResearchInfraArtifactIndexRecord(**payload))
    return records
