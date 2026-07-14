import { defineConfig, devices } from '@playwright/test';

const dashboardPort = Number(process.env.PLAYWRIGHT_DASHBOARD_PORT ?? '5174');
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT ?? '8766');
const uvicornCommand = process.env.PLAYWRIGHT_UVICORN ?? '.venv/bin/uvicorn';
const reuseExistingServer =
  process.env.PLAYWRIGHT_REUSE_EXISTING === 'false' ? false : !process.env.CI;
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
      command:
        `env PYTHONPATH=src STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED=false ${uvicornCommand} stock_research.dashboard.app:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: '..',
      url: `http://127.0.0.1:${apiPort}/openapi.json`,
      reuseExistingServer,
      timeout: 120000
    }
  ]
});
