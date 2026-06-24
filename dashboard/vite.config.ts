import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const runtime = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};
const apiTarget = runtime.process?.env?.DASHBOARD_API_TARGET ?? 'http://127.0.0.1:8765';
const publicSnapshotOnly =
  String(runtime.process?.env?.VITE_PUBLIC_SNAPSHOT_ONLY ?? '').toLowerCase() === 'true';
const buildInput = new URL(publicSnapshotOnly ? './public.html' : './index.html', import.meta.url)
  .pathname;

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: buildInput
    }
  },
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
