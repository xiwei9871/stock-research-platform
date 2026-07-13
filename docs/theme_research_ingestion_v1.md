# Theme Research Ingestion v1

## Scope

Phase 8 converts local research material into a versioned staging run for human review. It does not crawl remote pages, write a database, alter node scores, create company mappings, or allow extracted claims to enter reviewed research automatically.

Supported adapters:

| Adapter | Input | Default evidence treatment |
| --- | --- | --- |
| `manual_claim_json` | Structured source and claims | Uses explicit metadata; S4 remains lead-only |
| `text_document` | Local Markdown, TXT, or HTML | Conservative source-type-based suggestion |
| `docling_document` | Local PDF | Existing Docling parser; full-text report may be S0 |
| `existing_record` | Exported news, filing, or Daily Review JSON | Preserves record ID and local provenance |

URLs are references only. The module performs no network requests.

## Run Package

Each unique input/version/theme combination creates:

```text
artifacts/theme_decomposition/ingestion_runs/<run_id>/
  manifest.json
  normalized_sources.json
  claim_candidates.json
  theme_node_matches.json
  review_queue.json
  review_events.jsonl
  review_ledger_head.json
  promotion_preview.json
```

The current run-package schema identifier is `theme_research_ingestion_run_v1_1`. The `v1_1` revision adds the anchored ledger head; earlier local development runs remain isolated under their original content-addressed directories.

The normalized source text, source candidate, claim candidates with extraction spans, matches, and initial queue are checksum-protected and content-addressed by `run_id`. Updating a candidate and merely rewriting the manifest checksum therefore invalidates the run identity. Human decisions and two-phase promotion audits are appended to a hash-chained `review_events.jsonl`; `review_ledger_head.json` anchors both the expected event count and terminal hash so suffix truncation is detected. If a fully valid chained event was fsynced but the head update stopped, validation advances the stale head from its verified prefix. Re-ingesting identical content with the same adapter, extractor, matcher, and theme hint returns the existing run, including under concurrent calls.

Generated runs are ignored by Git. The checked-in sample is:

```text
artifacts/theme_decomposition/ingestion_samples/ai_power_video_claim_lead_v1.json
```

It is intentionally S4 and demonstrates that a video claim can only start as a research lead.

## Ingest

```bash
rtk .venv/bin/stock-research theme-research-ingestion \
  --runs-dir artifacts/theme_decomposition/ingestion_runs \
  ingest \
  --input artifacts/theme_decomposition/ingestion_samples/ai_power_video_claim_lead_v1.json \
  --input-type manual_claim_json \
  --theme-hint ai_power_value_capture_v1
```

For an unstructured local file, source metadata can be supplied as JSON:

```bash
rtk .venv/bin/stock-research theme-research-ingestion ingest \
  --input /path/to/local-note.md \
  --input-type text_document \
  --theme-hint ai_power_value_capture_v1 \
  --source-metadata-json '{"title":"Local note","source_type":"media_article"}'
```

## Inspect And Validate

```bash
rtk .venv/bin/stock-research theme-research-ingestion validate-run --run <run-dir>
rtk .venv/bin/stock-research theme-research-ingestion summary --run <run-dir>
rtk .venv/bin/stock-research theme-research-ingestion show-queue --run <run-dir>
```

## Review

Available decisions:

```text
accept_as_lead
accept_draft
accept_reviewed
reject
request_evidence
defer
```

Every decision requires a reviewer and a non-empty comment:

```bash
rtk .venv/bin/stock-research theme-research-ingestion review \
  --run <run-dir> \
  --candidate-id <candidate-id> \
  --decision accept_as_lead \
  --reviewer <reviewer> \
  --comment "Retain as a lead; primary evidence is still missing."
```

Policy gates:

- an S4 source cannot be accepted;
- automated claims start only as `research_lead`;
- `accept_reviewed` applies only to claims;
- a reviewed claim requires an accepted non-S4 source;
- rejected, deferred, and evidence-requested candidates are not promotable.
- a successfully promoted candidate is frozen; corrections require a new ingestion run so canonical evidence cannot silently diverge from its review ledger.

The hash chain detects malformed appends, edits, reordering, and truncation by ordinary tooling. In v1, `reviewer` is an audit label rather than a cryptographically authenticated user identity; authenticated write APIs and durable reviewer identity belong to Phase 9.

## Preview And Promote

Generate the projected additions:

```bash
rtk .venv/bin/stock-research theme-research-ingestion promotion-preview \
  --run <run-dir> \
  --target-artifact artifacts/theme_decomposition/ai_power_value_capture_v1.json
```

Promotion requires the current canonical artifact SHA-256:

```bash
rtk shasum -a 256 artifacts/theme_decomposition/ai_power_value_capture_v1.json

rtk .venv/bin/stock-research theme-research-ingestion promote \
  --run <run-dir> \
  --target-artifact artifacts/theme_decomposition/ai_power_value_capture_v1.json \
  --expected-sha256 <sha256>
```

The promoter acquires one shared canonical-package lock before any run lock. Before a new mutation, it scans all current-version runs and resolves every outstanding prepared transaction, so promotions to different theme files cannot race package-wide validation or leave an older transaction behind. Each prepared event stores the exact source/claim rows being added. Recovery commits when either the original after-hash matches or every prepared row still exists byte-for-byte at the target; it marks the transaction failed when the before-hash still matches and blocks on any other state. It then validates a temporary copy of the full canonical `theme_decomposition_v1_5` package, creates a timestamped backup, verifies the expected hash, writes a durable `prepared` audit event, and performs an atomic replacement. A `committed` audit failure restores the exact backup bytes, and candidate freezing follows each promotion ID's latest terminal state. It only appends reviewed source and claim rows. Theme nodes, scores, assessments, mappings, crosswalks, and priority policies remain unchanged.

## Verification

```bash
rtk .venv/bin/pytest tests/test_theme_research_ingestion.py -q
```

The formal design and implementation plan are:

- `docs/superpowers/specs/2026-07-11-theme-research-ingestion-v1-design.md`
- `docs/superpowers/plans/2026-07-11-theme-research-ingestion-v1.md`
