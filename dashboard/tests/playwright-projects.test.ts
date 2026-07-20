import { describe, expect, test } from 'vitest';

import {
  PLAYWRIGHT_PROFILES,
  buildProjects,
  buildWebServers,
  parsePlaywrightProfile,
  profileNeedsApi,
  profileServiceWorkers,
  profileTestMatch,
  resolveReuseExistingServer,
  resolveUvicornExecutable,
  type PlaywrightProfile
} from '../playwright.projects';

function projectBrowser(project: ReturnType<typeof buildProjects>[number]) {
  return (project.use as { defaultBrowserType?: string } | undefined)?.defaultBrowserType;
}

describe('parsePlaywrightProfile', () => {
  test('uses one stable readonly profile list', () => {
    expect(PLAYWRIGHT_PROFILES).toEqual(['legacy', 'mock', 'real', 'sandbox', 'audit', 'eod']);
  });

  test.each(PLAYWRIGHT_PROFILES)('accepts the %s profile', (profile) => {
    expect(parsePlaywrightProfile(profile)).toBe(profile);
  });

  test.each([undefined, '', '   '])('defaults %j to legacy', (raw) => {
    expect(parsePlaywrightProfile(raw)).toBe('legacy');
  });

  test('rejects unknown nonempty profiles with the accepted values', () => {
    expect(() => parsePlaywrightProfile('nightly')).toThrow(
      'Unknown Playwright profile "nightly". Expected one of: legacy, mock, real, sandbox, audit, eod.'
    );
  });
});

describe('buildProjects', () => {
  const expectedProjects: Record<PlaywrightProfile, Array<[string, string]>> = {
    legacy: [['chromium-desktop', 'chromium']],
    mock: [
      ['chromium-desktop', 'chromium'],
      ['chromium-mobile', 'chromium']
    ],
    real: [['chromium-desktop', 'chromium']],
    sandbox: [['chromium-desktop', 'chromium']],
    audit: [
      ['chromium-desktop', 'chromium'],
      ['chromium-mobile', 'chromium'],
      ['firefox-desktop', 'firefox'],
      ['webkit-critical', 'webkit']
    ],
    eod: [['chromium-desktop', 'chromium']]
  };

  test.each(
    Object.entries(expectedProjects) as Array<[PlaywrightProfile, Array<[string, string]>]>
  )(
    '%s has the expected stable project names and browsers',
    (profile, expected) => {
      expect(
        buildProjects(profile).map((project) => [project.name, projectBrowser(project)])
      ).toEqual(expected);
    }
  );

  test('restricts mock mobile coverage to @mobile tests', () => {
    const mobile = buildProjects('mock').find((project) => project.name === 'chromium-mobile');

    expect(mobile?.grep).toEqual(/@mobile/);
  });

  test('restricts audit WebKit coverage to @webkit-critical tests', () => {
    const webkit = buildProjects('audit').find((project) => project.name === 'webkit-critical');

    expect(webkit?.grep).toEqual(/@webkit-critical/);
  });

  test('keeps eod on Chromium desktop only', () => {
    expect(buildProjects('eod').map((project) => project.name)).toEqual(['chromium-desktop']);
  });

  test('returns fresh viewport objects for separate project builds', () => {
    const firstUse = buildProjects('legacy')[0].use as { viewport: { width: number } };
    const secondUse = buildProjects('legacy')[0].use as { viewport: { width: number } };
    const firstViewport = firstUse.viewport;
    const secondViewport = secondUse.viewport;

    expect(firstViewport).not.toBe(secondViewport);
    firstViewport.width = 1;
    expect(secondViewport.width).not.toBe(1);
  });
});

test('only the mock profile runs without the API server', () => {
  expect(
    Object.fromEntries(PLAYWRIGHT_PROFILES.map((profile) => [profile, profileNeedsApi(profile)]))
  ).toEqual({
    legacy: true,
    mock: false,
    real: true,
    sandbox: true,
    audit: true,
    eod: true
  });
});

test('blocks service workers only in read-only API profiles', () => {
  expect(
    Object.fromEntries(PLAYWRIGHT_PROFILES.map((profile) => [profile, profileServiceWorkers(profile)]))
  ).toEqual({
    legacy: 'allow',
    mock: 'allow',
    real: 'block',
    sandbox: 'allow',
    audit: 'block',
    eod: 'block'
  });
});

describe('resolveUvicornExecutable', () => {
  test('uses PLAYWRIGHT_UVICORN ahead of repository candidates', () => {
    expect(
      resolveUvicornExecutable('/repo/.worktrees/feature', {
        override: 'python -m custom_uvicorn',
        isExecutable: () => true
      })
    ).toBe('python -m custom_uvicorn');
  });

  test('falls back from a worktree without a local venv to the main repository venv', () => {
    const checkoutRoot = '/repo/.worktrees/feature';
    const sharedUvicorn = '/repo/.venv/bin/uvicorn';

    expect(
      resolveUvicornExecutable(checkoutRoot, {
        isExecutable: (candidate) => candidate === sharedUvicorn
      })
    ).toBe(sharedUvicorn);
  });

  test('uses the local venv in a main checkout', () => {
    const localUvicorn = '/repo/.venv/bin/uvicorn';

    expect(
      resolveUvicornExecutable('/repo', {
        isExecutable: (candidate) => candidate === localUvicorn
      })
    ).toBe(localUvicorn);
  });

  test('uses the worktree-local venv before the shared repository venv', () => {
    expect(
      resolveUvicornExecutable('/repo/.worktrees/feature', {
        isExecutable: () => true
      })
    ).toBe('/repo/.worktrees/feature/.venv/bin/uvicorn');
  });

  test('falls back to global Python when no repository candidate exists', () => {
    expect(
      resolveUvicornExecutable('/arbitrary/checkout', {
        isExecutable: () => false
      })
    ).toBe('python -m uvicorn');
  });

  test('shell-quotes a resolved executable path containing spaces', () => {
    expect(
      resolveUvicornExecutable('/repo with spaces', {
        isExecutable: () => true
      })
    ).toBe('"/repo with spaces/.venv/bin/uvicorn"');
  });
});

describe('profileTestMatch', () => {
  test('keeps legacy selection at the top level without a shell glob', () => {
    const match = profileTestMatch('legacy');

    expect(match).toBeInstanceOf(RegExp);
    expect((match as RegExp).test('/repo/dashboard/tests/app-smoke.spec.ts')).toBe(true);
    expect((match as RegExp).test('/repo/dashboard/tests/e2e/p0/auth.spec.ts')).toBe(false);
  });

  test.each(PLAYWRIGHT_PROFILES.filter((profile) => profile !== 'legacy'))(
    'lets %s select nested spec files',
    (profile) => {
      expect(profileTestMatch(profile)).toBe('**/*.spec.ts');
    }
  );
});

describe('resolveReuseExistingServer', () => {
  test('does not reuse dashboard or API servers by default for API-backed profiles', () => {
    expect(resolveReuseExistingServer('real', undefined, false)).toBe(false);
  });

  test('keeps local mock server reuse as the default', () => {
    expect(resolveReuseExistingServer('mock', undefined, false)).toBe(true);
  });

  test('honors explicit true and false locally', () => {
    expect(resolveReuseExistingServer('real', 'true', false)).toBe(true);
    expect(resolveReuseExistingServer('mock', 'false', false)).toBe(false);
  });

  test('never reuses an existing server in CI', () => {
    expect(resolveReuseExistingServer('mock', 'true', true)).toBe(false);
    expect(resolveReuseExistingServer('real', 'true', true)).toBe(false);
  });
});

describe('buildWebServers', () => {
  test.each([
    [false, 'pnpm exec vite --host 127.0.0.1 --port 5174'],
    [true, 'pnpm exec vite preview --host 127.0.0.1 --port 5174']
  ] as const)('passes the API proxy through structured env when preview=%s', (usePreview, command) => {
    const [dashboardServer] = buildWebServers({
      profile: 'real',
      dashboardPort: 5174,
      apiPort: 8766,
      usePreview,
      reuseExisting: undefined,
      ci: false,
      checkoutRoot: '/repo',
      uvicornCommand: 'python -m uvicorn'
    });

    expect(dashboardServer.command).toBe(command);
    expect(dashboardServer.env).toEqual({
      VITE_API_PROXY_TARGET: 'http://127.0.0.1:8766'
    });
  });

  test('uses structured API env and the resolved uvicorn command', () => {
    const servers = buildWebServers({
      profile: 'real',
      dashboardPort: 5174,
      apiPort: 8766,
      usePreview: false,
      reuseExisting: undefined,
      ci: false,
      checkoutRoot: '/repo',
      uvicornCommand: 'python -m uvicorn'
    });

    expect(servers).toHaveLength(2);
    expect(servers[1]).toMatchObject({
      command:
        'python -m uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8766',
      cwd: '/repo',
      env: {
        PYTHONPATH: 'src',
        STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED: 'false',
        STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED: 'false'
      },
      reuseExistingServer: false
    });
    expect(servers[1].command).not.toMatch(/^env /);
  });

  test('starts only Vite for the mock profile', () => {
    const servers = buildWebServers({
      profile: 'mock',
      dashboardPort: 5174,
      apiPort: 8766,
      usePreview: false,
      reuseExisting: undefined,
      ci: false,
      checkoutRoot: '/repo',
      uvicornCommand: 'python -m uvicorn'
    });

    expect(servers).toHaveLength(1);
    expect(servers[0].reuseExistingServer).toBe(true);
  });
});
