# Research Operating Layer V2 R2B — Phase C AI Compute PCB Stage A Acquisition Smoke

## 1. Current commit and workspace state

- Execution baseline: `d76c95f`
- Workspace: `/Users/xiwei/stock_research/.worktrees/research-platform-validation-20260713`
- Project: `research_project:ai_compute_pcb_industry_bottleneck`
- Research-version context: `research_version:ai_compute_pcb_industry_bottleneck:0.2.1`
- The Phase C changes are confined by the machine-readable Phase C exact allowlist.

## 2. Selected Evidence Requirements

Four existing Stage A requirements were selected:

- `r2b_er01`: primary system-level AI compute architecture question;
- `r2b_er02`: AI server versus general-purpose server board topology;
- `r2b_er03`: compute node, NIC/DPU, rack switch and data-center network placement;
- `r2b_er17`: open counter/substitution requirement for alternative interconnect architectures.

No effective-capacity, supply-gap, margin, company qualification, order, revenue or stock requirement was selected.

## 3. Candidate sources and selection reasons

| Candidate | Organization | Form | Requirement | Reason |
|---|---|---|---|---|
| NVIDIA DGX B200 User Guide — Introduction | NVIDIA | HTML | ER02 | Official accelerator-server system documentation |
| NVIDIA DGX B200 Datasheet via Widen | NVIDIA | PDF redirect | ER01 | Official current DGX B200 system datasheet candidate |
| NVIDIA BlueField-2 DPU Product Brief | NVIDIA | PDF | ER03 | Official direct PDF covering DPU/system placement |
| Broadcom Tomahawk 5 BCM78900 Series | Broadcom | HTML | ER03 | Official switching-silicon product page from a second organization |
| Lightmatter Passage | Lightmatter | HTML | ER17 | Primary alternative photonic-interconnect candidate; no stance assigned |
| Controlled localhost target | Controlled fixture | blocked target | ER01 | Deterministic SSRF failure without contacting a public site |

Search snippets and the V1 source pack were not promoted to evidence. Publication dates that could not be independently confirmed remain `null`.

## 4. Acquisition attempts overview

Seven immutable attempts were retained. The original five-attempt design expanded because the first official PDF exposed a transport-classification defect; the failed attempt and the post-fix retry were both preserved.

| Attempt | Result | Failure code | Raw artifact |
|---|---|---|---|
| `f470653cf66455c093974ca8` | acquired | — | `df8cb3fd0943596cdde66cd6` |
| `057c44df439c4f842a4108a5` | failed | `unknown_failure` | — |
| `e8df32785e5f9f3ab8c2b307` | acquired | — | `b37fa65c89137b99055bf363` |
| `daa8e15dbde6b81d862f741d` | acquired | — | `164d6d7a272660c4edad6aeb` |
| `9f07debf59a3b22604467ebe` | acquired | — | `41921ed38ab6990d795c270b` |
| `a71d7df00cba6375f9681f93` | blocked | `security_policy_blocked` | — |
| `d9322b574d572032111aeeff` | blocked | `security_policy_blocked` | — |

Final distribution: four acquired, two fail-closed security blocks and one immutable pre-fix `unknown_failure`.

## 5. Successful HTML

Three HTML artifacts were acquired through the explicit direct provider:

- NVIDIA DGX B200 User Guide: 47,528 bytes;
- Broadcom Tomahawk 5: 48,342 bytes;
- Lightmatter Passage: 83,135 bytes.

The NVIDIA and Lightmatter HTML artifacts normalized successfully. The Broadcom raw acquisition succeeded, but deterministic normalization returned `unsupported_format`; the raw artifact was retained.

## 6. Successful PDF

The NVIDIA BlueField-2 DPU product brief was acquired as a direct `application/pdf` response:

- 165,224 bytes;
- SHA-256 `e2a678f07c7d626227c1f6c64b0602341ad8b9fb7c43769ece6643609b2e524a`;
- normalized with `pypdf`;
- four pages represented in the normalized document.

The current DGX B200 Widen URL was not used as a substitute after its redirect failed strict peer verification.

## 7. Counter candidate

Lightmatter Passage was acquired under ER17 as a boundary/alternative-route candidate. It remains `pending_assessment`; no `supports`, `opposes`, strength, directness or claim relationship was created.

## 8. Expected failure case

`http://127.0.0.1/private` was submitted through the direct provider. DNS/address policy rejected it before content acquisition:

- status: `blocked`;
- failure code: `security_policy_blocked`;
- policy: `public_network_only`;
- bytes: zero;
- raw artifact: none;
- CLI exit code: 8;
- no provider fallback occurred.

## 9. Provider and proxy mode

All seven attempts used:

- provider: `direct_http`;
- proxy mode: `direct`;
- provider-owned `requests.Session`;
- local `trust_env=False`;
- TLS verification enabled;
- bounded timeouts;
- zero retries for the smoke;
- no environment proxy, browser or manual-import fallback.

## 10. Raw artifact list

| Artifact | MIME | Bytes | SHA-256 |
|---|---:|---:|---|
| `df8cb3fd0943596cdde66cd6` | `text/html` | 47,528 | `d98d8d20c3cb36f90b4b5163230dfbef4a9348e52ea2a4674b75b52a96171de3` |
| `b37fa65c89137b99055bf363` | `application/pdf` | 165,224 | `e2a678f07c7d626227c1f6c64b0602341ad8b9fb7c43769ece6643609b2e524a` |
| `164d6d7a272660c4edad6aeb` | `text/html` | 48,342 | `b0e55cb3d8d8eabe454b8b7ea2382e8751edbe6d6ad46ade580a2b814f8d181c` |
| `41921ed38ab6990d795c270b` | `text/html` | 83,135 | `9e2be009b7c2dad89b4e9bac5dcd01e60a6f2c330abc41e62b6ed78b88c4988b` |

All raw artifacts are immutable and remain under content-addressed paths.

## 11. Normalization results

| Raw artifact | Result | Parser | Normalized document |
|---|---|---|---|
| `df8cb3fd0943596cdde66cd6` | normalized | `stdlib.html.parser` | `8d9b94b1ce2f98ff9290a021` |
| `b37fa65c89137b99055bf363` | normalized | `pypdf` | `6ab0c383b7a9cc3a5cd4bcd8` |
| `164d6d7a272660c4edad6aeb` | normalization failed | deterministic adapter | — |
| `41921ed38ab6990d795c270b` | normalized | `stdlib.html.parser` | `f95a1102582bb956c52f8997` |

Normalization failure did not alter or delete the Broadcom raw artifact. Docling and Browser were not used.

## 12. Hash and dedup results

- All four raw files match their recorded SHA-256 and byte size.
- All four content hashes are distinct.
- No exact duplicate was detected or claimed.
- Every normalized document points to its raw artifact ID, whose metadata records the verified raw hash.

## 13. Provenance completeness

All attempts, evidence artifacts and checkpoints contain the required provenance fields:

- `created_by`;
- `actor_type`;
- `agent_run_id`;
- `created_at`;
- `created_in_version`;
- `review_status`.

The final checkpoint records `provenance_completeness=complete`.

## 14. Failure taxonomy results

The expected localhost block was classified correctly. The Widen URL returns `303` with `Content-Length: 0`; Requests/urllib3 releases the connection before the current transport can read the connected peer. The original attempt was immutably recorded as `unknown_failure`.

The classifier was then corrected so `FETCH_PEER_UNAVAILABLE` fails closed as `security_policy_blocked`, with `peer_address_class=unknown`. A new independent retry confirmed that behavior. The old attempt was not overwritten.

## 15. Security and SSRF audit

- Public targets were validated by scheme, host, DNS result and connected peer.
- Redirect handling remained enabled only through the existing per-hop validator.
- Localhost was blocked.
- No proxy allowlist was broadened.
- No SSRF, TLS, MIME or access-control check was disabled.
- No silent fallback occurred.
- No partial or temporary artifact remains.
- Sensitive-data scans found no credentials, API keys, proxy credentials, cookies or URL userinfo in Phase C metadata and code. The only password-related match was the existing URL-credential rejection logic.

## 16. Acquisition checkpoint

Final checkpoint:

- path: `artifacts/research_projects/v2_1/acquisition/checkpoints/acquisition_checkpoint:953b996bf4c8e4cddcd12a8b.json`;
- checkpoint ID: `acquisition_checkpoint:953b996bf4c8e4cddcd12a8b`;
- canonical hash: `953b996bf4c8e4cddcd12a8b94f2edaa8fa849908857b66424303691dd9f9477`;
- successful attempts: 4;
- failed/blocked attempts: 3;
- status: `pending_assessment`.

The earlier checkpoint `5fd456a1429d87adb60a156e` remains as an immutable pre-classifier-fix checkpoint and is not the final handoff checkpoint.

## 17. Immutable research-version hash verification

The embedded canonical hashes remain unchanged:

- `v0.2.0`: `1fa8ec9026ae9fcb8d16824f058f1746c158316f49e18378551de460ade3667b`;
- `v0.2.1`: `ff0e2e152029df98254668f8a6fbb9ee7bd162fd85bfe8e4f49ed8dfe47e232b`.

No file under the AI PCB `versions/` directory was modified.

## 18. Tests and regressions

Pre-closure verification after the smoke implementation:

- acquisition and scope tests: `73 passed`;
- V2 / R1-R2 compatibility: `1303 passed`;
- V1 / Theme Research / Dashboard regression: `449 passed`.

The final handoff is subject to a fresh post-commit rerun under the verification-before-completion rule.

## 19. Scope attribution

The Phase C exact allowlist is:

`artifacts/research_projects/v2_1/acquisition/phase_c_exact_allowlist.json`

It permits only the candidate inputs, attempts, raw/metadata/normalized artifacts, checkpoints, minimal schema/code/test fixes and this report. It forbids V1, Industry Catalog, project version snapshots, Dashboard and production API paths.

## 20. Explicitly not executed

- No Evidence Assessment was created.
- No Evidence Requirement was marked satisfied or closed.
- No claim or bottleneck status changed.
- No value-migration conclusion was created.
- No `v0.2.2` or `v0.3.0` was created.
- No medical-device pilot was started.
- No company, stock, watchlist or strategy work was performed.
- Full AI PCB acquisition was not started.

## 21. Engineering issues discovered

1. Checkpoint 2.3 originally lacked smoke-level requirement/candidate/count/distribution fields. It was extended additively without changing 2.1/2.2 or existing research versions.
2. Failed acquisition CLI commands previously returned zero. Fetch/import now return exit code 8 when the structured attempt is not `acquired`.
3. `FETCH_PEER_UNAVAILABLE` previously fell through to `unknown_failure`; it now fails closed as `security_policy_blocked`.
4. Zero-length redirects can release the Requests connection before peer extraction. A future solution must preserve actual transport-peer validation; DNS-only substitution is not acceptable.
5. Broadcom HTML acquired successfully but did not normalize with the deterministic parser.

## 22. Evidence-access issues discovered

- The search provider remains unavailable, so official URL discovery is manual/known-directory based.
- Widen generates a signed CDN redirect and its initial zero-length response is incompatible with current strict peer extraction.
- Source publication dates were not reliably present in the acquired metadata and remain unknown.
- One official product page requires parser investigation despite successful raw acquisition.

## 23. Recommendation on full AI PCB Phase 2 acquisition

Recommendation: **conditionally proceed only after user confirmation**.

The direct HTML/PDF, immutable storage, normalization, provenance, structured failure and checkpoint chain is operational. Full acquisition should initially prefer direct public documents without zero-length redirect intermediaries, retain fail-closed behavior for unverifiable peers, and treat normalization failure as a coverage gap rather than an acquisition failure.

## 24. Decisions required before the next step

Before full AI PCB acquisition, confirm whether to:

1. proceed with the current fail-closed policy while excluding Widen-style redirect sources unless a direct official URL exists;
2. schedule a separate transport design task for verified peer capture across zero-length redirects;
3. investigate the Broadcom HTML normalization failure before expanding Stage A collection;
4. keep publication-date metadata as unknown unless explicitly available from the source.

Phase C stops here pending those decisions.

## Commands used

Each real public acquisition used the following form, with the corresponding candidate and requirement substituted:

```text
research-project-v2-1 acquisition fetch
  --project ai_compute_pcb_industry_bottleneck
  --version 0.2.1
  --requirement <explicit requirement ID>
  --candidate <explicit candidate JSON>
  --proxy-mode direct
  --timeout-seconds 20
  --max-retries 0
  --agent-run-id r2b-phase-c-ai-pcb-stage-a-smoke-20260721
```

The expected SSRF failure used the same command with a five-second timeout and returned exit code 8. No command contained proxy credentials, cookies, API keys or user credentials.
