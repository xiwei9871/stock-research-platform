# Research Operating Layer V2 R2B — External Evidence Acquisition Recovery Phase B

## 1. Outcome

Phase B extends the existing R2A acquisition pipeline instead of creating a parallel crawler:

```text
Discovery
→ Explicit Acquisition Provider
→ Acquisition Attempt
→ Immutable Raw Artifact
→ Optional Normalization
→ Pending Assessment
```

The implementation stops before the AI Compute PCB Phase C smoke batch. It does not create an Evidence Assessment, change a claim or bottleneck status, create `v0.2.2`, enter Phase 3, or start the medical-device pilot.

## 2. Schema 2.3.0 standalone artifacts

The following standalone, additive schemas were added without changing the 2.1 or 2.2 schemas:

- `acquisition_attempt_v2_3`
- `evidence_artifact_v2_3`
- `manual_import_request_v2_3`
- `acquisition_checkpoint_v2_3`
- `provider_diagnostic_v2_3`

Acquisition schema versioning is independent from research semantic versioning. Acquisition artifacts refer to project and research-version context by explicit IDs; they are not embedded research conclusions.

## 3. Provider behavior

### Direct HTTP

- `proxy_mode=direct` is explicit and default.
- The direct provider creates its own `requests.Session` and sets `trust_env=False` on that session only.
- Global requests behavior is not patched.
- Environment and explicit proxy modes fail closed until a trusted-proxy design exists.
- Provider fallback is never silent; another provider invocation creates another attempt.
- TLS verification remains enabled.
- Timeouts, redirect count, response size, retry count and retry classes are bounded.
- Non-transient HTTP failures are not retried.
- Raw writes use the existing immutable and atomic storage mechanisms.

The existing SSRF boundary remains active: scheme, credentials, host, DNS results, connected peer, every redirect target, address class, port, MIME and maximum size are checked. `security_policy_blocked` distinguishes a local policy decision from target unavailability.

### Manual/local import

The formal import path accepts PDF, HTML, text/Markdown, JSON, CSV and existing Docling JSON artifacts. It records source metadata, import actor, MIME, byte size, SHA-256, access note and provenance. Missing metadata is marked incomplete rather than invented. Successful import ends at `pending_assessment`.

### Search discovery

Search remains a structured unavailable provider with `search_provider_error`. It may create discovery state only and does not produce evidence artifacts or satisfy evidence requirements.

### Browser and normalization

- Browser support is an optional adapter with runtime detection and structured unavailable state. It is not browser-first and does not silently replace direct HTTP.
- Existing HTML and PDF parsers remain available.
- Docling is an optional normalization adapter. Raw acquisition success is independent of parser success, and each normalized representation records raw hash, parser name, version, configuration and timestamp.

## 4. Acquisition records and provenance

Every provider invocation creates an immutable attempt, including failures. Attempts record project/version context, requirement and candidate IDs, provider, request/proxy mode, requested and resolved URL, timestamps, duration, status, failure code, HTTP status, redirects, MIME, bytes, retries, raw artifact ID, diagnostic summary and provenance.

Exact content hash, canonical URL and redirect aliases support deterministic deduplication. Different wording with a suspected common origin is not automatically treated as independent evidence.

The checkpoint artifact summarizes attempts, raw artifacts and normalization records without producing a research version or assessment.

## 5. Diagnostics and CLI

The existing `research-project-v2-1` CLI now has one bounded `acquisition` group:

- `doctor`
- `fetch`
- `import`
- `show-attempt`
- `smoke`

Doctor reports DNS, TLS, direct HTML/PDF, redirect, proxy detection, requests trust mode, browser runtime, search-provider state, normalizers and security-policy state. Proxy endpoints are redacted; credentials, cookies and tokens are not persisted.

The `smoke` command remains deliberately disabled and returns `not_run` until Phase C is separately approved.

## 6. Test and security coverage

Offline coverage includes:

- standalone schema validation and backward compatibility;
- provider contracts and structured failure taxonomy;
- explicit direct mode and absence of silent proxy inheritance;
- no silent provider fallback;
- SSRF, redirect and DNS/peer safety;
- maximum size, MIME, empty body, HTTP error and retry behavior;
- hashing, exact deduplication, immutable/atomic storage and rollback;
- manual import and provenance;
- normalization separation and raw-artifact retention;
- optional browser/Docling available and unavailable paths;
- CLI dry-run behavior;
- exact scope guard.

A controlled local HTTP server verifies that the direct transport can acquire HTML and PDF while invalid environment proxy variables are present. Higher-layer SSRF tests intentionally continue to reject localhost; redirects, error responses, empty content, oversized content and partial failures are covered with controlled transport fixtures so no real internet is required by regression tests.

Final verification results are recorded in the implementation handoff and were run after the final code and documentation changes.

## 7. Scope and immutability audit

The exact allowlist is machine readable at `artifacts/research_projects/v2_1/acquisition/phase_b_exact_allowlist.json` and is enforced by the R2B scope guard.

The following remained untouched by Phase B:

- Theme Research V1 and all 27 themes;
- Industry Catalog V1;
- Dashboard and production API;
- database and migrations;
- medical-device, humanoid-robot and storage pilots;
- company, stock, watchlist and strategy artifacts;
- AI PCB `v0.2.0` and `v0.2.1`.

The canonical hashes embedded in the two immutable AI PCB versions remain:

- `v0.2.0`: `1fa8ec9026ae9fcb8d16824f058f1746c158316f49e18378551de460ade3667b`
- `v0.2.1`: `ff0e2e152029df98254668f8a6fbb9ee7bd162fd85bfe8e4f49ed8dfe47e232b`

## 8. Deferred work

- Trusted proxy support is intentionally not implemented.
- Search provider recovery or replacement is deferred.
- Browser rendering acquisition remains optional and must be explicitly invoked in a later approved scope.
- Docling remains optional rather than a success condition.
- Phase C must be separately approved before any AI PCB online acquisition smoke batch is run.

