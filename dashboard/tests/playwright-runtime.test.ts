import { describe, expect, it } from 'vitest';

import {
  buildPlaywrightApiServerCommand,
  ensureThemeReportFixtureToken,
} from '../playwright.runtime';

describe('Playwright runtime command', () => {
  it('inherits the fixture token without placing it in the shell command', () => {
    const token = "special token ' $(echo leaked)";
    const env: Record<string, string | undefined> = { PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN: token };
    expect(ensureThemeReportFixtureToken(env, () => 'unused')).toBe(token);
    const command = buildPlaywrightApiServerCommand(8766);

    expect(command).not.toContain(token);
    expect(command).not.toContain('PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN=');
  });

  it('uses a fixed Node launcher without shell env assignment or quoting', () => {
    const command = buildPlaywrightApiServerCommand(8766);

    expect(command).toBe('node scripts/run-playwright-api-server.mjs --port 8766');
    expect(command).not.toContain('env ');
    expect(command).not.toContain("'");
  });
});
