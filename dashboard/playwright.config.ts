import { defineConfig, devices } from '@playwright/test';

const playwrightPort = process.env.PLAYWRIGHT_PORT ?? '4175';
const baseURL = `http://127.0.0.1:${playwrightPort}`;

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL,
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: `PLAYWRIGHT_PORT=${playwrightPort} pnpm dev`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120000
  }
});
