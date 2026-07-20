import { devices, type Project } from '@playwright/test';

export const PLAYWRIGHT_PROFILES = ['legacy', 'mock', 'real', 'sandbox', 'audit', 'eod'] as const;
export type PlaywrightProfile = (typeof PLAYWRIGHT_PROFILES)[number];

export function parsePlaywrightProfile(raw?: string): PlaywrightProfile {
  const profile = raw?.trim();
  if (!profile) return 'legacy';
  if ((PLAYWRIGHT_PROFILES as readonly string[]).includes(profile)) return profile as PlaywrightProfile;

  throw new Error(
    `Unknown Playwright profile "${profile}". Expected one of: ${PLAYWRIGHT_PROFILES.join(', ')}.`
  );
}

function cloneDevice(deviceName: keyof typeof devices) {
  const device = devices[deviceName];
  return {
    ...device,
    viewport: { ...device.viewport }
  };
}

function chromiumDesktop(): Project {
  return {
    name: 'chromium-desktop',
    use: cloneDevice('Desktop Chrome')
  };
}

function chromiumMobile(grep?: RegExp, grepInvert?: RegExp): Project {
  return {
    name: 'chromium-mobile',
    grep,
    grepInvert,
    use: cloneDevice('Pixel 5')
  };
}

export function buildProjects(profile: PlaywrightProfile): Project[] {
  if (profile === 'mock') {
    return [chromiumDesktop(), chromiumMobile(/@mobile/)];
  }

  if (profile === 'audit') {
    return [
      chromiumDesktop(),
      chromiumMobile(undefined, /@visual/),
      {
        name: 'firefox-desktop',
        grepInvert: /@visual/,
        use: {
          ...cloneDevice('Desktop Firefox'),
          launchOptions: {
            firefoxUserPrefs: {
              'accessibility.tabfocus': 7,
              'network.proxy.type': 0
            }
          }
        }
      },
      {
        name: 'webkit-critical',
        grep: /@webkit-critical/,
        use: cloneDevice('Desktop Safari')
      }
    ];
  }

  return [chromiumDesktop()];
}

export function profileNeedsApi(profile: PlaywrightProfile): boolean {
  return profile !== 'mock';
}

export function profileServiceWorkers(profile: PlaywrightProfile): 'allow' | 'block' {
  return profile === 'real' || profile === 'audit' || profile === 'eod' ? 'block' : 'allow';
}

export function profileTestMatch(profile: PlaywrightProfile): string | RegExp {
  return profile === 'legacy'
    ? /(?:^|[\\/]tests[\\/])[^\\/]+\.spec\.ts$/
    : '**/*.spec.ts';
}

export function resolveReuseExistingServer(
  profile: PlaywrightProfile,
  raw: string | undefined,
  ci: boolean
): boolean {
  if (ci) return false;
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  return !profileNeedsApi(profile);
}

export function resolveExternalServers(raw: string | undefined): boolean {
  return raw === 'true';
}

type UvicornResolutionOptions = {
  override?: string;
  isExecutable?: (candidate: string) => boolean;
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

function quoteExecutablePath(candidate: string): string {
  if (/^[A-Za-z0-9_./:-]+$/.test(candidate)) return candidate;
  return `"${candidate.replace(/(["\\$`])/g, '\\$1')}"`;
}

export function resolveUvicornExecutable(
  checkoutRoot: string,
  options: UvicornResolutionOptions = {}
): string {
  if (options.override) return options.override;

  const candidates = uvicornCandidates(checkoutRoot);
  const executable = candidates.find(options.isExecutable ?? (() => false));
  return executable ? quoteExecutablePath(executable) : 'python -m uvicorn';
}

export type WebServerConfig = {
  command: string;
  cwd?: string;
  env: Record<string, string>;
  url: string;
  reuseExistingServer: boolean;
  timeout: number;
};

export type WebServerOptions = {
  profile: PlaywrightProfile;
  dashboardPort: number;
  apiPort: number;
  usePreview: boolean;
  reuseExisting: string | undefined;
  ci: boolean;
  checkoutRoot: string;
  uvicornCommand: string;
};

export function buildWebServers(options: WebServerOptions): WebServerConfig[] {
  const reuseExistingServer = resolveReuseExistingServer(
    options.profile,
    options.reuseExisting,
    options.ci
  );
  const dashboardCommand = options.usePreview
    ? `pnpm exec vite preview --host 127.0.0.1 --port ${options.dashboardPort}`
    : `pnpm exec vite --host 127.0.0.1 --port ${options.dashboardPort}`;
  const servers: WebServerConfig[] = [
    {
      command: dashboardCommand,
      env: {
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${options.apiPort}`
      },
      url: `http://127.0.0.1:${options.dashboardPort}`,
      reuseExistingServer,
      timeout: 120000
    }
  ];

  if (profileNeedsApi(options.profile)) {
    servers.push({
      command:
        `${options.uvicornCommand} stock_research.dashboard.app:app --host 127.0.0.1 --port ${options.apiPort}`,
      cwd: options.checkoutRoot,
      env: {
        PYTHONPATH: 'src',
        STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED: 'false',
        STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED: 'false'
      },
      url: `http://127.0.0.1:${options.apiPort}/openapi.json`,
      reuseExistingServer,
      timeout: 120000
    });
  }

  return servers;
}

export function buildConfiguredWebServers(
  options: WebServerOptions,
  externalServersRaw: string | undefined
): WebServerConfig[] | undefined {
  return resolveExternalServers(externalServersRaw) ? undefined : buildWebServers(options);
}
