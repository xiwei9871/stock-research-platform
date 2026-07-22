# Evidence Acquisition Capability Hardening v1

This checkpoint validates acquisition capability only. It is not research evidence and changes no ER coverage.

- Checkpoint: `acquisition_capability_checkpoint:1951ded60c95381391c13e82`
- Benchmark: 10/10 fixed cases passed
- Formal research coverage change: 0
- Recovery acquisition authorized: false

## Root causes

- denominator_insufficient: 1
- http_403: 1
- http_404: 4
- index_only: 1
- landing_page_only: 1
- overview_only: 1
- security_policy_blocked: 4
- source_type_mismatch: 2
- timeout_or_transient_network: 1
- unknown: 1

## Candidate content classes

- broken_url: 4
- full_text_pdf: 3
- overview: 1
- standard_landing_page: 1
- unknown: 7
- working_group_index: 1

## Interpretation

Wave 1b losses are mixed: stale or restricted entry points, content-shape mistakes, incomplete document identity, and denominator mismatch all contributed. The fixed benchmark now rejects landing, overview and index pages as full text; collapses duplicate content; preserves fail-closed security behavior; and produces non-authorizing alternative-entry plans. Public full-text availability remains partly structural and requires human review.
