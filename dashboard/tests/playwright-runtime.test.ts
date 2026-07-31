import { describe, expect, it } from 'vitest';

import {
  buildThemeReportServerCommand,
  ensureThemeReportFixtureToken,
  resolvePlaywrightPython
} from '../playwright.runtime';

describe('Playwright runtime command', () => {
  it('inherits the fixture token without placing it in the shell command', () => {
    const token = "special token ' $(echo leaked)";
    const env: Record<string, string | undefined> = { PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN: token };
    expect(ensureThemeReportFixtureToken(env, () => 'unused')).toBe(token);
    const command = buildThemeReportServerCommand({
      python: '/safe/python',
      apiPort: 8766
    });

    expect(command).not.toContain(token);
    expect(command).not.toContain('PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN=');
  });

  it('prefers an explicit interpreter and shell-quotes it', () => {
    const python = "/tmp/python path/'quoted'";
    const resolved = resolvePlaywrightPython(
      { PLAYWRIGHT_PYTHON: python },
      '/repo',
      () => false
    );

    expect(resolved).toBe(python);
    expect(buildThemeReportServerCommand({ python: resolved, apiPort: 8766 }))
      .toContain("'/tmp/python path/'\"'\"'quoted'\"'\"''");
  });

  it('uses the active virtualenv, then repo virtualenv, then python3', () => {
    expect(resolvePlaywrightPython({ VIRTUAL_ENV: '/active/venv' }, '/repo', () => false))
      .toBe('/active/venv/bin/python');
    expect(resolvePlaywrightPython({}, '/repo', (path) => path === '/repo/.venv/bin/python'))
      .toBe('/repo/.venv/bin/python');
    expect(resolvePlaywrightPython({}, '/worktree', (path) => path === '/repo/.venv/bin/python', '/repo'))
      .toBe('/repo/.venv/bin/python');
    expect(resolvePlaywrightPython({}, '/repo', () => false)).toBe('python3');
  });
});
