import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

import {
  buildProjects,
  parsePlaywrightProfile,
  profileNeedsApi,
  resolveUvicornExecutable
} from './playwright.projects';

const profile = parsePlaywrightProfile(process.env.PLAYWRIGHT_PROFILE);
const checkoutRoot = fileURLToPath(new URL('..', import.meta.url));
const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const reuseExistingServer =
  process.env.PLAYWRIGHT_REUSE_EXISTING === 'false' ? false : !process.env.CI;
const dashboardCommand =
  process.env.PLAYWRIGHT_USE_PREVIEW === 'true'
    ? `pnpm exec vite preview --host 127.0.0.1 --port ${dashboardPort}`
    : `VITE_API_PROXY_TARGET=http://127.0.0.1:${apiPort} pnpm exec vite --host 127.0.0.1 --port ${dashboardPort}`;
const dashboardServer = {
  command: dashboardCommand,
  url: `http://127.0.0.1:${dashboardPort}`,
  reuseExistingServer,
  timeout: 120000
};
const webServer = profileNeedsApi(profile)
  ? [
      dashboardServer,
      {
        command:
          `env PYTHONPATH=src STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED=false ${resolveUvicornExecutable(checkoutRoot, { override: process.env.PLAYWRIGHT_UVICORN, exists: existsSync })} stock_research.dashboard.app:app --host 127.0.0.1 --port ${apiPort}`,
        cwd: checkoutRoot,
        url: `http://127.0.0.1:${apiPort}/openapi.json`,
        reuseExistingServer,
        timeout: 120000
      }
    ]
  : [dashboardServer];

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.ts',
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  outputDir: `test-results/${profile}`,
  reporter: [
    ['html', { outputFolder: `playwright-report/${profile}`, open: 'never' }],
    [
      'json',
      {
        outputFile:
          process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? `test-results/${profile}/results.json`
      }
    ]
  ],
  use: {
    baseURL: `http://127.0.0.1:${dashboardPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  projects: buildProjects(profile),
  webServer
});
