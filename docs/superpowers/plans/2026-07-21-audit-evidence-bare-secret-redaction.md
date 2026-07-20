# Audit Evidence Bare-Secret Redaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent secret-shaped quoted literals in Playwright error-context source excerpts from entering archived platform-validation report evidence.

**Architecture:** Extend the existing text-evidence sanitizer after structured header/query/path/assignment redaction. Redact any remaining single- or double-quoted scalar containing a sensitive credential name, while retaining surrounding code-frame structure; raw Playwright evidence remains untouched and only the report archive is sanitized.

**Tech Stack:** Python standard library, pytest, deterministic HTML/JSON report generator.

---

## File Structure

- `src/stock_research/platform_validation_report.py`: adds the final quoted secret-shaped literal sanitizer.
- `tests/test_platform_validation_report.py`: proves Markdown/error-context and trace members cannot retain bare secret sentinels.

### Task 1: Add A Failing Evidence-Archive Security Test

**Files:**
- Modify: `tests/test_platform_validation_report.py`

- [ ] **Step 1: Create an error-context attachment fixture**

Add a failed Playwright result whose `.md` attachment contains:

```text
404 | expect(serialized).not.toContain('raw-url-secret')
405 | expect(serialized).not.toContain("raw-path-token")
406 | const harmless = 'ordinary-value'
```

- [ ] **Step 2: Build the report and scan every archived text file**

Assert:

```python
archived_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (output / "evidence").iterdir()
    if path.suffix in {".md", ".txt", ".json", ".log"}
)
assert "raw-url-secret" not in archived_text
assert "raw-path-token" not in archived_text
assert "ordinary-value" in archived_text
assert "'[REDACTED]'" in archived_text or '"[REDACTED]"' in archived_text
```

- [ ] **Step 3: Verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_platform_validation_report.py \
  -k "bare_secret or evidence_archive" -q
```

Expected: FAIL because `_sanitize_text` currently redacts keyed/assigned/query/path credentials but not isolated quoted literals in source excerpts.

### Task 2: Implement The Final Quoted-Literal Redaction

**Files:**
- Modify: `src/stock_research/platform_validation_report.py`

- [ ] **Step 1: Add a bounded pattern beside the existing secret patterns**

```python
_QUOTED_SECRET_LITERAL = re.compile(
    rf"(?i)(?P<quote>['\"])(?P<value>[^'\"\r\n]*{_SENSITIVE_NAME}[^'\"\r\n]*)(?P=quote)"
)
```

The pattern is line-bounded and cannot cross quotes or newlines.

- [ ] **Step 2: Apply it last in `_sanitize_text`**

```python
text = _QUOTED_SECRET_LITERAL.sub(
    lambda match: f"{match.group('quote')}[REDACTED]{match.group('quote')}",
    text,
)
```

Apply after existing header, bearer, structured JSON, query, path, and assignment rules so those more informative redactions keep their key names.

- [ ] **Step 3: Add false-positive controls**

Assert ordinary quoted values, words such as `secret-free` outside quoted scalars, issue titles, and filenames remain readable. Existing JSON payload sanitization and safe ZIP tests must stay unchanged.

- [ ] **Step 4: Run report tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_platform_validation_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the security fix**

```bash
git add src/stock_research/platform_validation_report.py tests/test_platform_validation_report.py
git commit -m "fix: redact bare secrets from audit evidence"
```

### Task 3: Regenerate And Security-Scan A New Audit

**Files:**
- No manual edits to generated report evidence.

- [ ] **Step 1: Build a new baseline-candidate report from raw Playwright inputs**

Do not pre-sanitize copied attachments. The generator itself must produce safe archives.

- [ ] **Step 2: Run the sentinel scan**

```bash
rtk rg -n "raw-url-secret|raw-path-secret|raw-query-secret|raw-path-token" \
  outputs/research/platform_validation/<new-audit-id>/report
```

Expected: no matches.

- [ ] **Step 3: Run the broader credential scan**

Scan report JSON, HTML, Markdown, text, and decompressed safe trace members for unredacted Authorization, Cookie, password, access token, refresh token, API key, and secret values. Expected: no credential values; `[REDACTED]` markers are allowed.

- [ ] **Step 4: Keep the original audit immutable**

Retain `pv-initial-20260720-372f4a5` and its P1 finding. Only a new audit can close this root and qualify for baseline promotion.

