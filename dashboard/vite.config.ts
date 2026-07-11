import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const runtimeEnv =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
const apiProxyTarget = runtimeEnv.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': apiProxyTarget
    }
  },
  test: {
    environment: 'jsdom',
    exclude: ['**/node_modules/**', '**/dist/**', '**/*.spec.ts']
  }
});
