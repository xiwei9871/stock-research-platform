# Anti-drift evidence — stock-research-platform (2026-10-31)

- `sr_gates.py all`: state-head PASS (baseline 23ad1d4), workspace PASS-with-note,
  protected-inputs PASS (5/5 dirs on disk), assets-decisions PASS.
- `sr_gates.py self-test`: T01–T03 PASS (deploy structurally BLOCKED; report
  defaults to NOT_VERIFIED without evidence — evidence-first rule).
- Deliberate false-positive fix during rollout: historical logs/ and registered
  .worktrees/ checkouts excluded from source scan; test fixtures asserting the
  D03 constraint are not violations.
- Deploy authorization is always BLOCKED by the gate; human approval is
  external and separate (D07).
