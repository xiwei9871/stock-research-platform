import { describe, expect, it } from 'vitest';

// @ts-expect-error The cross-platform launcher is intentionally native ESM JavaScript.
import { buildPythonInvocation, forwardSignal, pythonCandidates } from '../scripts/run-playwright-api-server.mjs';

describe('Playwright API server launcher', () => {
  it('selects platform-specific virtualenv interpreters without shell interpolation', () => {
    expect(pythonCandidates({ env: { VIRTUAL_ENV: 'C:\\venv' }, repoRoot: 'C:\\repo', platform: 'win32' }))
      .toEqual(['C:\\venv\\Scripts\\python.exe', 'C:\\repo\\.venv\\Scripts\\python.exe', 'python']);
    expect(pythonCandidates({ env: { VIRTUAL_ENV: '/venv' }, repoRoot: '/repo', platform: 'darwin' }))
      .toEqual(['/venv/bin/python', '/repo/.venv/bin/python', 'python3']);
  });

  it('injects the current checkout src and selects the requested support server', () => {
    const invocation = buildPythonInvocation({
      env: { PLAYWRIGHT_THEME_REPORT_REAL_E2E: 'true', PYTHONPATH: '/old/src' },
      repoRoot: '/current/worktree',
      python: '/python',
      port: 8766,
      platform: 'linux'
    });

    expect(invocation.executable).toBe('/python');
    expect(invocation.args[0]).toBe('tests/support/theme_research_report_e2e_server.py');
    expect(invocation.env.PYTHONPATH).toBe('/current/worktree/src:/old/src');
  });

  it('forwards the original termination signal to Python', () => {
    const received: string[] = [];
    forwardSignal({ killed: false, kill: (signal: string) => received.push(signal) }, 'SIGINT');
    forwardSignal({ killed: false, kill: (signal: string) => received.push(signal) }, 'SIGTERM');

    expect(received).toEqual(['SIGINT', 'SIGTERM']);
  });
});
