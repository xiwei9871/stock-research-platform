import { defineConfig, devices } from '@playwright/test';

const PLAYWRIGHT_PORT = 4175;
const PLAYWRIGHT_BASE_URL = `http://127.0.0.1:${PLAYWRIGHT_PORT}`;

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: PLAYWRIGHT_BASE_URL,
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: `pnpm exec vite --host 127.0.0.1 --port ${PLAYWRIGHT_PORT}`,
    url: PLAYWRIGHT_BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  }
});
