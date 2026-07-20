import { accessSync, constants } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

import {
  buildProjects,
  buildWebServers,
  parsePlaywrightProfile,
  profileNeedsApi,
  profileTestMatch,
  resolveUvicornExecutable
} from './playwright.projects';

const profile = parsePlaywrightProfile(process.env.PLAYWRIGHT_PROFILE);
const checkoutRoot = fileURLToPath(new URL('..', import.meta.url));
const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const isExecutable = (candidate: string) => {
  try {
    accessSync(candidate, constants.X_OK);
    return true;
  } catch {
    return false;
  }
};
const uvicornCommand = profileNeedsApi(profile)
  ? resolveUvicornExecutable(checkoutRoot, {
      override: process.env.PLAYWRIGHT_UVICORN,
      isExecutable
    })
  : 'python -m uvicorn';
const webServer = buildWebServers({
  profile,
  dashboardPort,
  apiPort,
  usePreview: process.env.PLAYWRIGHT_USE_PREVIEW === 'true',
  reuseExisting: process.env.PLAYWRIGHT_REUSE_EXISTING,
  ci: Boolean(process.env.CI),
  checkoutRoot,
  uvicornCommand
});

export default defineConfig({
  testDir: './tests',
  testMatch: profileTestMatch(profile),
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
