import { defineConfig, devices } from '@playwright/test';
import { randomBytes } from 'node:crypto';

import {
  buildPlaywrightApiServerCommand,
  buildPlaywrightDashboardServerCommand,
  ensureThemeReportFixtureToken
} from './playwright.runtime';

const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const themeReportRealE2E = process.env.PLAYWRIGHT_THEME_REPORT_REAL_E2E === 'true';
if (themeReportRealE2E) {
  ensureThemeReportFixtureToken(process.env, () => `theme-report-${randomBytes(32).toString('hex')}`);
}
const reuseExistingServer =
  themeReportRealE2E || process.env.PLAYWRIGHT_REUSE_EXISTING === 'false' ? false : !process.env.CI;
const dashboardCommand = buildPlaywrightDashboardServerCommand({
  port: dashboardPort,
  apiPort,
  preview: process.env.PLAYWRIGHT_USE_PREVIEW === 'true'
});

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
      command: buildPlaywrightApiServerCommand(apiPort),
      cwd: '.',
      url: `http://127.0.0.1:${apiPort}/openapi.json`,
      reuseExistingServer,
      gracefulShutdown: themeReportRealE2E ? { signal: 'SIGTERM', timeout: 10_000 } : undefined,
      timeout: 120000
    }
  ]
});
