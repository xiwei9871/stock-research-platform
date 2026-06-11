import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const runtime = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};
const apiTarget = runtime.process?.env?.DASHBOARD_API_TARGET ?? 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': apiTarget
    }
  },
  test: {
    environment: 'jsdom'
  }
});
