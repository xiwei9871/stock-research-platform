# Evidence Acquisition Capability Hardening v1 Design

## Architecture

Build one integrated, read-only capability module over frozen Wave 1 and Wave 1b artifacts. It classifies candidate content, resolves document identity, audits attempt root causes, creates ER-aware discovery plans, matches evidence shape, generates safe alternative-entry plans, runs ten deterministic benchmark cases, and validates a capability checkpoint.

No capability artifact is research evidence. The implementation must not create or modify formal candidates, attempts, raw artifacts, normalized documents, ER coverage, assessments, cognition, or downstream research state.

## Components

1. `acquisition_capability.py`: pure classification, identity, planning, recovery, benchmark, hashing, and validation functions.
2. A controlled builder script: reads immutable upstream artifacts and writes only the capability-hardening directory.
3. Four read-only CLI commands: diagnose, benchmark, inspect-candidate, and plan-discovery.
4. One focused test file covering classification, recovery safety, duplicate collapse, upstream drift, CLI read-only behavior, and research-coverage immutability.

## Benchmark

The fixed benchmark uses the existing NIST PDF, IEEE 370 landing page, PCI-SIG overview, IEEE 802.3ck index, 404 attempts, security-blocked attempts, Panasonic timeout, unresolved B02 publication identity, encrypted Isola PDF, and duplicate NIST raw hash. Controlled network smoke remains optional and separate; the baseline uses zero network cases because existing immutable artifacts fully cover the required capability behaviors.

## Fail-closed rules

- landing, index, overview, abstract, and metadata pages cannot be full text;
- blocked/403/paywall recovery cannot propose bypass;
- publication dates require explicit evidence;
- duplicate raw hashes collapse to one identity;
- alternative-entry plans never authorize acquisition;
- all downstream authorization and formal coverage change remain false/zero.
