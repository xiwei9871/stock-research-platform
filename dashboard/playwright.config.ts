import { defineConfig, devices } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildThemeReportServerCommand,
  buildStandardDashboardServerCommand,
  ensureThemeReportFixtureToken,
  resolvePlaywrightPython
} from './playwright.runtime';

const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const themeReportRealE2E = process.env.PLAYWRIGHT_THEME_REPORT_REAL_E2E === 'true';
if (themeReportRealE2E) {
  ensureThemeReportFixtureToken(process.env, () => `theme-report-${randomBytes(32).toString('hex')}`);
}
const repoRoot = fileURLToPath(new URL('..', import.meta.url));
let sharedRepoRoot: string | undefined;
try {
  const commonGitDir = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], {
    cwd: repoRoot,
    encoding: 'utf8'
  }).trim();
  sharedRepoRoot = dirname(commonGitDir);
} catch {
  sharedRepoRoot = undefined;
}
const playwrightPython = resolvePlaywrightPython(process.env, repoRoot, existsSync, sharedRepoRoot);
const reuseExistingServer =
  themeReportRealE2E || process.env.PLAYWRIGHT_REUSE_EXISTING === 'false' ? false : !process.env.CI;
const dashboardCommand =
  process.env.PLAYWRIGHT_USE_PREVIEW === 'true'
    ? `pnpm exec vite preview --host 127.0.0.1 --port ${dashboardPort}`
    : `VITE_API_PROXY_TARGET=http://127.0.0.1:${apiPort} pnpm exec vite --host 127.0.0.1 --port ${dashboardPort}`;

export default defineConfig({
  testDir: './tests',
  testIgnore: themeReportRealE2E ? [] : ['**/theme-research-full-flow.spec.ts'],
  workers: themeReportRealE2E ? 1 : undefined,
  use: {
    baseURL: `http://127.0.0.1:${dashboardPort}`,
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: [
    {
      command: dashboardCommand,
      url: `http://127.0.0.1:${dashboardPort}`,
      reuseExistingServer,
      timeout: 120000
    },
    {
      command: themeReportRealE2E
        ? buildThemeReportServerCommand({ python: playwrightPython, apiPort })
        : buildStandardDashboardServerCommand({ python: playwrightPython, apiPort }),
      cwd: '..',
      url: `http://127.0.0.1:${apiPort}/openapi.json`,
      reuseExistingServer,
      gracefulShutdown: themeReportRealE2E ? { signal: 'SIGTERM', timeout: 10_000 } : undefined,
      timeout: 120000
    }
  ]
});
