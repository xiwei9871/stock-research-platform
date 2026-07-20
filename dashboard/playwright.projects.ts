import { devices, type Project } from '@playwright/test';

export type PlaywrightProfile = 'legacy' | 'mock' | 'real' | 'sandbox' | 'audit' | 'eod';

const PLAYWRIGHT_PROFILES: PlaywrightProfile[] = ['legacy', 'mock', 'real', 'sandbox', 'audit', 'eod'];

export function parsePlaywrightProfile(raw?: string): PlaywrightProfile {
  const profile = raw?.trim();
  if (!profile) return 'legacy';
  if (PLAYWRIGHT_PROFILES.includes(profile as PlaywrightProfile)) return profile as PlaywrightProfile;

  throw new Error(
    `Unknown Playwright profile "${profile}". Expected one of: ${PLAYWRIGHT_PROFILES.join(', ')}.`
  );
}

function chromiumDesktop(): Project {
  return {
    name: 'chromium-desktop',
    use: { ...devices['Desktop Chrome'] }
  };
}

function chromiumMobile(grep?: RegExp): Project {
  return {
    name: 'chromium-mobile',
    grep,
    use: { ...devices['Pixel 5'] }
  };
}

export function buildProjects(profile: PlaywrightProfile): Project[] {
  if (profile === 'mock') {
    return [chromiumDesktop(), chromiumMobile(/@mobile/)];
  }

  if (profile === 'audit') {
    return [
      chromiumDesktop(),
      chromiumMobile(),
      {
        name: 'firefox-desktop',
        use: { ...devices['Desktop Firefox'] }
      },
      {
        name: 'webkit-critical',
        grep: /@webkit-critical/,
        use: { ...devices['Desktop Safari'] }
      }
    ];
  }

  return [chromiumDesktop()];
}

export function profileNeedsApi(profile: PlaywrightProfile): boolean {
  return profile !== 'mock';
}

type UvicornResolutionOptions = {
  override?: string;
  exists?: (candidate: string) => boolean;
};

function uvicornCandidates(checkoutRoot: string): string[] {
  const normalizedRoot = checkoutRoot.replace(/\/+$/, '');
  const candidates = [`${normalizedRoot}/.venv/bin/uvicorn`];
  const worktreeMatch = normalizedRoot.match(/^(.*)\/\.worktrees\/[^/]+$/);

  if (worktreeMatch) {
    candidates.push(`${worktreeMatch[1]}/.venv/bin/uvicorn`);
  }

  return candidates;
}

export function resolveUvicornExecutable(
  checkoutRoot: string,
  options: UvicornResolutionOptions = {}
): string {
  if (options.override) return options.override;

  const candidates = uvicornCandidates(checkoutRoot);
  return candidates.find(options.exists ?? (() => false)) ?? candidates[0];
}
