# Evidence Acquisition Capability Hardening v1

This phase validates acquisition capability only. It does not change formal research candidates, attempts, evidence artifacts, ER coverage, assessments, cognition, or downstream authorization.

The implementation adds six bounded capabilities over the existing acquisition pipeline:

1. ER-aware discovery plans that include evidence shape, identifiers, denominator terms, exclusions, qualification rules, and stop rules.
2. Candidate qualification that separates full text from landing pages, overviews, working-group indexes, metadata, purchase pages, broken URLs, and unknown content.
3. Conservative local document identity extraction from immutable normalized content, including standard/document numbers, DOI, authors, and explicit dates. URL or download metadata never supplies a publication date.
4. Safe alternative-entry plans for 404, 403, timeout, security-blocked, encrypted, landing, index, metadata, denominator, and common-origin cases. Plans never authorize acquisition or bypass a security control.
5. Failure-aware recommendations that distinguish entry failure, access failure, parsing failure, source-shape mismatch, denominator insufficiency, and identity uncertainty.
6. ER evidence-shape matching that prevents authoritative but irrelevant content from becoming direct evidence merely because of source reputation.

The fixed benchmark contains ten frozen Wave 1/Wave 1b cases. It is deterministic and offline; no benchmark output is eligible for research evidence or ER coverage. Metrics describe only this fixed benchmark and do not estimate open-web recall.

Public read-only CLI commands are:

```text
research-project-v2-1 acquisition-capability diagnose
research-project-v2-1 acquisition-capability benchmark
research-project-v2-1 acquisition-capability inspect-candidate --candidate-id <id>
research-project-v2-1 acquisition-capability plan-discovery --er <authorized benchmark ER>
```

The CLI reads persisted capability artifacts and cannot create candidates, attempts, raw artifacts, assessments, or research-state transitions.
