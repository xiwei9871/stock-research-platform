import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const runtimeEnv =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
const apiProxyTarget = runtimeEnv.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8765';
const releaseId = runtimeEnv.VITE_RELEASE_ID?.trim() ?? '';
const apiBaseImage = runtimeEnv.VITE_API_BASE_IMAGE?.trim() ?? 'python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7';
const frontendBaseImage = runtimeEnv.VITE_FRONTEND_BASE_IMAGE?.trim() ?? 'nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'dashboard-release-metadata',
      generateBundle() {
        this.emitFile({
          type: 'asset',
          fileName: 'release.json',
          source: `${JSON.stringify({
            release_id: releaseId,
            api_base_image: apiBaseImage,
            frontend_base_image: frontendBaseImage
          })}\n`
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
