import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const runtimeEnv =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
const apiProxyTarget = runtimeEnv.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8765';
const releaseId = runtimeEnv.VITE_RELEASE_ID?.trim() ?? '';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'dashboard-release-metadata',
      generateBundle() {
        this.emitFile({
          type: 'asset',
          fileName: 'release.json',
          source: `${JSON.stringify({ release_id: releaseId })}\n`
        });
      }
    }
  ],
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
