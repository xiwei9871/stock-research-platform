# Theme Research Ingestion v1 Design

## Purpose

Phase 8 adds an artifact-first ingestion and human-review boundary to the Theme-driven Research Engine. It converts local research inputs into traceable source and claim candidates without allowing automation to mutate reviewed research.

The v1 flow is:

```text
local input
  -> normalize and fingerprint
  -> extract claim candidates
  -> match theme nodes
  -> suggest evidence classification
  -> immutable staging run
  -> append-only human review
  -> validated promotion into a canonical theme artifact
```

The module does not crawl the internet, write a database, modify node scores, create company mappings, or let model output become reviewed evidence without a human decision.

## Inputs

Four adapters share one normalized document contract:

1. `manual_claim_json`: structured source metadata and one or more manually recorded claims.
2. `text_document`: local Markdown, text, or HTML. HTML is reduced to readable text without network access.
3. `docling_document`: a local PDF parsed through the existing Docling parser. Docling output is converted to normalized Markdown; parse failures are explicit.
4. `existing_record`: a JSON export from an existing news, filing, or Daily Review record.

Remote URLs are metadata only. A URL is never fetched by Phase 8.

Every normalized input records:

- adapter type and adapter version;
- original path or reference;
- canonical UTF-8 content;
- normalized source metadata;
- SHA-256 content fingerprint;
- parsing diagnostics and provenance.

## Run Package

Generated runs live under:

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

The current package schema is `theme_research_ingestion_run_v1_1`, which includes the anchored ledger-head contract.

`run_id` is a content address derived from the normalized input fingerprint, immutable source/claim/match/queue payloads, adapter version, extractor version, matcher version, and theme hint. Re-ingesting identical content with identical versions returns the same run and does not duplicate candidates. Candidate mutation cannot be authorized by editing the manifest checksum because validation recomputes the content-addressed run identity.

The normalized source, claim, match, and queue JSON files are immutable after run creation. Normalized source text and claim extraction spans remain available for reviewer traceability. `review_events.jsonl` is append-only and hash-chained from a run-specific seed, while `review_ledger_head.json` anchors the terminal hash and event count to detect tail truncation. A head that is a verified prefix of a longer valid chain is advanced automatically after an interrupted head write; a head ahead of the ledger remains an integrity failure. `promotion_preview.json` is a derived cache and may be rebuilt from immutable candidates plus the event ledger.

Generated run directories are local runtime artifacts and are ignored by Git. Tests use temporary directories.

## Candidate Schemas

### Source candidate

Each source candidate contains:

- `candidate_id`, `candidate_type=source_candidate`;
- canonical `source_item` fields required by `theme_decomposition_v1_5`;
- `content_sha256` and provenance;
- `suggested_review_status`;
- `suggestion_reasons`;
- `candidate_status=pending_human_review`.

Reliability suggestions are conservative:

- formal local reports and filings may be suggested as S0 when full text is present;
- official public articles may be suggested as S1;
- references to unavailable reports are S2;
- media and secondary exports are S3;
- video, social, and oral claims are S4.

S4 sources can never be promoted with `review_status=accepted`.

### Claim candidate

Each claim candidate contains:

- `candidate_id`, `candidate_type=claim_candidate`;
- proposed `content_claim` fields;
- source candidate/source ID linkage;
- extraction span and extractor provenance;
- suggested theme and node matches;
- `candidate_status=pending_human_review`.

Automated extraction can only suggest `platform_use_status=research_lead` or `draft`. It cannot suggest `reviewed`.

## Extraction and Matching

The extractor interface accepts normalized text and emits deterministic claim spans. v1 ships `rule_based_sentence_v1`:

- split text into sentences and list items;
- discard empty, very short, and obvious heading-only fragments;
- classify claim type with explicit keyword rules;
- keep extraction offsets and the matched rule names;
- use stable IDs based on content and source identity.

The matcher loads existing theme artifacts through `load_theme_package()` and uses:

1. an explicit `theme_hint` when supplied;
2. exact node ID/name aliases;
3. normalized token overlap against node name, description, key metrics, and known players;
4. a minimum score threshold, otherwise no node is attached.

Matches are suggestions. They do not modify the node graph.

## Review Ledger

Review decisions are append-only events:

```text
accept_as_lead
accept_draft
accept_reviewed
reject
request_evidence
defer
```

Every event requires `reviewer`, `comment`, timestamp, candidate ID, decision, event ID, prior-event hash, and event hash. The latest event for a candidate defines its projected state; history remains intact. Successful promotion freezes the candidate, and any correction must enter through a new run.

The local hash chain is an integrity control for malformed or accidental file mutation, not reviewer authentication. v1 treats `reviewer` as an operator-supplied audit label. Cryptographically authenticated reviewer identity and controlled write APIs are Phase 9 responsibilities.

Decision gates:

- `accept_reviewed` is forbidden for source candidates;
- source `accept_draft` maps to `review_status=accepted`, but is forbidden for S4;
- source `accept_as_lead` maps to `review_status=lead_only`;
- claim `accept_as_lead` maps to `research_lead/unverified`;
- claim `accept_draft` maps to `draft` and cannot claim `verified` without an accepted canonical source;
- claim `accept_reviewed` requires an accepted non-S4 canonical source and explicit human review;
- rejected, deferred, or evidence-requested candidates are not promotable.

## Promotion

Promotion is explicit and theme-scoped. It requires:

- a target canonical theme artifact;
- the caller's expected SHA-256 of that artifact;
- at least one promotable reviewed candidate;
- complete validation before replacement.

The promoter:

1. verifies the expected SHA-256 to prevent lost updates;
2. projects the latest review decisions;
3. builds source additions before claim additions;
4. deduplicates by canonical source/claim IDs;
5. acquires one shared lock for the complete canonical artifact package, resolves outstanding prepared transactions across all current-version runs, then acquires the active run lock;
6. writes a temporary candidate artifact;
7. validates a temporary copy of the full canonical package using the existing `theme_decomposition_v1_5` loader;
8. writes a timestamped backup and durable `prepared` audit event;
9. atomically replaces the canonical file;
10. appends a `committed` audit event, restoring the exact backup bytes if that commit cannot be recorded.

Prepared events retain the exact added source and claim rows. If the process stops after replacement and before the committed event, exact row presence freezes the affected candidates even if a later valid addition changes the whole-file hash. Before any new package mutation, recovery reconciles an exact after-hash or exact prepared-row presence to committed, a matching pre-promotion hash to failed, and rejects any other state as a recovery conflict. Candidate freezing follows the latest terminal event for each promotion ID, so a later rolled-back state does not remain frozen.

Promotion never changes theme nodes, scores, value-capture assessments, company mappings, crosswalks, or priority policy. Repeating a successful promotion is idempotent.

## CLI

The module is exposed as `stock-research theme-research-ingestion` and as `python -m stock_research.theme_research_ingestion`.

Commands:

```text
ingest
validate-run
summary
show-queue
review
promotion-preview
promote
```

All commands emit JSON. Validation and policy errors use stable error codes and a non-zero exit status.

## Read-only API

Phase 8 does not add a write-capable dashboard. The existing Theme Research dashboard remains read-only. CLI review and promotion keep the first production boundary auditable and avoid introducing authentication-sensitive write APIs before Phase 9.

## Failure Handling

- malformed input produces no partial run;
- Docling import/parse errors are surfaced with parser diagnostics;
- an incomplete run directory is removed before returning an error;
- an invalid review event is never appended;
- hash mismatch or validation failure leaves the canonical artifact unchanged;
- promotion backup and audit records preserve recovery information.

## v1 Boundaries

Phase 8 intentionally excludes:

- remote crawling, login, anti-bot handling, and scheduled collection;
- model-based extraction or autonomous research conclusions;
- database persistence;
- dashboard review controls;
- automatic source acceptance;
- automatic node creation, score changes, company admission, or stock recommendations.
