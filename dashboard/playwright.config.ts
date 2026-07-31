import { defineConfig, devices } from '@playwright/test';

const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const themeReportRealE2E = process.env.PLAYWRIGHT_THEME_REPORT_REAL_E2E === 'true';
const themeReportFixtureToken =
  process.env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN ??
  `theme-report-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
if (themeReportRealE2E) process.env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN = themeReportFixtureToken;
const reuseExistingServer =
  themeReportRealE2E || process.env.PLAYWRIGHT_REUSE_EXISTING === 'false' ? false : !process.env.CI;
const dashboardCommand =
  process.env.PLAYWRIGHT_USE_PREVIEW === 'true'
    ? `pnpm exec vite preview --host 127.0.0.1 --port ${dashboardPort}`
    : `VITE_API_PROXY_TARGET=http://127.0.0.1:${apiPort} pnpm exec vite --host 127.0.0.1 --port ${dashboardPort}`;

export default defineConfig({
  testDir: './tests',
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
        ? `env PYTHONPATH=src PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN=${themeReportFixtureToken} ../../.venv/bin/python tests/support/theme_research_report_e2e_server.py --host 127.0.0.1 --port ${apiPort}`
        : `env STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED=false .venv/bin/uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: '..',
      url: `http://127.0.0.1:${apiPort}/openapi.json`,
      reuseExistingServer,
      gracefulShutdown: themeReportRealE2E ? { signal: 'SIGTERM', timeout: 10_000 } : undefined,
      timeout: 120000
    }
  ]
});
