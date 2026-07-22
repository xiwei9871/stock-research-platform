# Research Operating Layer V2 R2B — AI PCB Targeted Acquisition Wave 1b

## Scope

Wave 1b executed only `PCB-ER-A04`, `PCB-ER-B01`, `PCB-ER-B02`, and `PCB-ER-A02`, in the frozen order A04/B01/B02 then A02. A01, A03, every unlisted ER, Evidence Assessment, cognition update, company mapping, Stage A2, Stage B, and future waves remained unauthorized.

## Acquisition result

- candidates / formal attempts / preflight: 17 / 17 / 0;
- acquired / blocked / failed: 6 / 4 / 7;
- HTML / PDF / other: 3 / 3 / 0;
- raw artifacts / unique hashes: 6 / 4;
- normalized / normalization failures: 6 / 0;
- confirmed publication dates / unknown dates: 0 / 6;
- exact duplicate group: the same NIST Technical Note content acquired under A04, B01, and B02 associations;
- security-policy-blocked attempts: 4;
- security violations / scope violations: 0 / 0.

## Per-ER result

- A04: NIST metrology PDF and IEEE 370 official landing page acquired; instrument-method URLs returned 404. Denominator triage remains incomplete for reference plane, de-embedding, coupon/actual-channel relationship, channel length, and Nyquist frequency.
- B01: NIST metrology PDF acquired. IPC and Rogers candidates were blocked fail-closed, and Panasonic timed out. No second-supplier data sheet or formal IPC method was acquired.
- B02: NIST metrology PDF acquired. Crossref registry lookup failed, the university source returned 403, and the professional engineering source was blocked. Original publication provenance and an independent roughness experiment remain absent.
- A02: PCI-SIG overview and IEEE 802.3ck public index acquired. The 800G ETC and specific IEEE presentation URLs returned 404. No independent measured channel with a complete rate/reach/de-embedding denominator was acquired.

All four ERs are therefore recorded as `acquisition_partial_with_gaps`. This is an acquisition checkpoint only and does not make any sufficiency or technical-cognition determination.

## Governance

- direct HTTP, direct proxy mode, provider-local `trust_env=False`;
- SSRF and redirect checks unchanged;
- blocked and failed attempts did not create evidence coverage;
- raw artifacts remain immutable and normalized documents trace to raw hashes;
- publication dates were not inferred;
- `assessment_started = false`;
- `cognition_update_started = false`;
- `wave_2_authorized = false`;
- company mapping, Stage A2, and Stage B remain unauthorized.
