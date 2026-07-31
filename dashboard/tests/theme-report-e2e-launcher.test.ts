import { describe, expect, it } from 'vitest';

// @ts-expect-error The cross-platform launcher is intentionally native ESM JavaScript.
import { buildThemeReportE2EInvocation } from '../scripts/run-theme-report-e2e.mjs';

describe('theme report E2E standard entry point', () => {
  it('enables the isolated backend and targets only the real theme report spec', () => {
    const invocation = buildThemeReportE2EInvocation(['--', '--repeat-each=2'], {
      PLAYWRIGHT_THEME_REPORT_REAL_E2E: 'false',
      SENTINEL: 'kept'
    });

    expect(invocation.env.PLAYWRIGHT_THEME_REPORT_REAL_E2E).toBe('true');
    expect(invocation.env.SENTINEL).toBe('kept');
    expect(invocation.args).toContain('tests/theme-research-full-flow.spec.ts');
    expect(invocation.args).toContain('--repeat-each=2');
    expect(invocation.args).not.toContain('--');
  });
});
