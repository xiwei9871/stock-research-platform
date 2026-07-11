import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: 'http://127.0.0.1:5174',
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
      command: 'pnpm dev',
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: !process.env.CI,
      timeout: 120000
    },
    {
      command:
        'env STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED=false .venv/bin/uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8766',
      cwd: '..',
      url: 'http://127.0.0.1:8766/openapi.json',
      reuseExistingServer: !process.env.CI,
      timeout: 120000
    }
  ]
});
