import { describe, expect, it } from 'vitest';

// @ts-expect-error The cross-platform launcher is intentionally native ESM JavaScript.
import { buildViteInvocation, forwardSignal, resolveViteCliPath } from '../scripts/run-playwright-dashboard-server.mjs';

describe('Playwright dashboard server launcher', () => {
  it.each(['win32', 'linux'])('builds a shell-free Vite invocation on %s', (platform) => {
    const invocation = buildViteInvocation({
      env: { SENTINEL: 'kept' },
      nodeExecutable: '/node',
      viteCli: '/repo/node_modules/vite/bin/vite.js',
      dashboardRoot: '/repo/dashboard',
      port: 5174,
      apiPort: 8766,
      preview: false,
      platform
    });

    expect(invocation.executable).toBe('/node');
    expect(invocation.args).toEqual(['/repo/node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5174']);
    expect(invocation.env.VITE_API_PROXY_TARGET).toBe('http://127.0.0.1:8766');
    expect(invocation.env.SENTINEL).toBe('kept');
  });

  it.each([
    ['linux', '/repo/node_modules/vite/dist/node/index.js', '/repo/node_modules/vite/bin/vite.js'],
    ['win32', 'C:\\repo\\node_modules\\vite\\dist\\node\\index.js', 'C:\\repo\\node_modules\\vite\\bin\\vite.js'],
  ])('resolves the Vite CLI with %s path semantics', (platform, viteEntry, expected) => {
    expect(resolveViteCliPath(viteEntry, platform)).toBe(expected);
  });

  it('adds preview as a Vite subcommand and forwards the original signal', () => {
    const invocation = buildViteInvocation({
      env: {},
      nodeExecutable: '/node',
      viteCli: '/vite.js',
      dashboardRoot: '/dashboard',
      port: 5174,
      apiPort: 8766,
      preview: true,
      platform: 'win32'
    });
    const received: string[] = [];
    forwardSignal({ killed: false, kill: (signal: string) => received.push(signal) }, 'SIGTERM');

    expect(invocation.args).toEqual(['/vite.js', 'preview', '--host', '127.0.0.1', '--port', '5174']);
    expect(received).toEqual(['SIGTERM']);
  });
});
