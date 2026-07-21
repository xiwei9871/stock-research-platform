# AI PCB Targeted Evidence Acquisition Wave 1 Design

## Scope

Execute one continuous acquisition wave for exactly `PCB-ER-A01`, `A02`, `A03`, `A04`, `B01`, and `B02`. The frozen Gate decision is the sole authorization source. No Evidence Assessment, cognition update, bottleneck/value judgment, company mapping, Stage A2 or Stage B is permitted.

## Architecture

Reuse `DirectHttpProvider`, immutable raw storage and the existing normalizer. Add one focused Wave 1 governance module that validates the Gate, screens candidates, enforces internal phase order, records Wave-specific candidate/attempt/inventory JSONL, adapts acquired v2.3 metadata to the existing deterministic normalizer, and validates one final checkpoint. Global immutable raw/metadata/normalized stores remain canonical; the Wave directory contains references and governance records rather than duplicate raw content.

## Data flow

```text
frozen Gate
→ explicit candidate record
→ exact-list authorization check
→ direct_http attempt
→ immutable global raw/evidence artifact
→ deterministic normalized document
→ Wave inventory/reference records
→ one acquisition checkpoint and factual summary
```

Discovery may use public search only to identify URLs. Search snippets never enter evidence coverage. Whole documents may be retained, but formal associations and coverage are restricted to authorized ER IDs.

## Security and stopping

Every public fetch uses `proxy_mode=direct`, provider-local `trust_env=False`, TLS validation, bounded redirects/bytes/timeouts and existing SSRF checks. No fallback is silent. Blocked attempts remain attempts and never count as acquired. Duplicate content shares one raw hash and one provisional evidence chain.

## Outputs

One directory under `artifacts/research_projects/v2_1/acquisition/wave_1/` contains candidates, Wave attempt references, normalized association records, evidence inventory, checkpoint and summary. Existing global acquisition artifacts remain authoritative. A dedicated exact allowlist prevents changes to cognition, gap-review and Gate artifacts.
