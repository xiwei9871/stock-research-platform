import { describe, expect, test } from 'vitest';

import {
  buildProjects,
  parsePlaywrightProfile,
  profileNeedsApi,
  resolveUvicornExecutable,
  type PlaywrightProfile
} from '../playwright.projects';

function projectBrowser(project: ReturnType<typeof buildProjects>[number]) {
  return (project.use as { defaultBrowserType?: string } | undefined)?.defaultBrowserType;
}

describe('parsePlaywrightProfile', () => {
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
});

test('only the mock profile runs without the API server', () => {
  const profiles: PlaywrightProfile[] = ['legacy', 'mock', 'real', 'sandbox', 'audit', 'eod'];

  expect(Object.fromEntries(profiles.map((profile) => [profile, profileNeedsApi(profile)]))).toEqual({
    legacy: true,
    mock: false,
    real: true,
    sandbox: true,
    audit: true,
    eod: true
  });
});

describe('resolveUvicornExecutable', () => {
  test('uses PLAYWRIGHT_UVICORN ahead of repository candidates', () => {
    expect(
      resolveUvicornExecutable('/repo/.worktrees/feature', {
        override: '/custom/uvicorn',
        exists: () => true
      })
    ).toBe('/custom/uvicorn');
  });

  test('falls back from a worktree without a local venv to the main repository venv', () => {
    const checkoutRoot = '/repo/.worktrees/feature';
    const sharedUvicorn = '/repo/.venv/bin/uvicorn';

    expect(
      resolveUvicornExecutable(checkoutRoot, {
        exists: (candidate) => candidate === sharedUvicorn
      })
    ).toBe(sharedUvicorn);
  });
});
