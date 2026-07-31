type RuntimeEnvironment = Record<string, string | undefined>;

function join(root: string, suffix: string) {
  return `${root.replace(/\/$/, '')}/${suffix}`;
}

export function ensureThemeReportFixtureToken(env: RuntimeEnvironment, createToken: () => string) {
  const token = env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN ?? createToken();
  env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN = token;
  return token;
}

export function resolvePlaywrightPython(
  env: RuntimeEnvironment,
  repoRoot: string,
  exists: (path: string) => boolean,
  sharedRepoRoot?: string
) {
  if (env.PLAYWRIGHT_PYTHON) return env.PLAYWRIGHT_PYTHON;
  if (env.VIRTUAL_ENV) return join(env.VIRTUAL_ENV, 'bin/python');
  const candidates = [join(repoRoot, '.venv/bin/python')];
  if (sharedRepoRoot && sharedRepoRoot !== repoRoot) candidates.push(join(sharedRepoRoot, '.venv/bin/python'));
  return candidates.find(exists) ?? 'python3';
}

function shellQuote(value: string) {
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

export function buildThemeReportServerCommand(options: {
  python: string;
  apiPort: number;
}) {
  return [
    'env PYTHONPATH=src',
    shellQuote(options.python),
    'tests/support/theme_research_report_e2e_server.py',
    '--host 127.0.0.1',
    `--port ${options.apiPort}`
  ].join(' ');
}

export function buildStandardDashboardServerCommand(options: { python: string; apiPort: number }) {
  return [
    'env STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED=false',
    shellQuote(options.python),
    '-m uvicorn stock_research.dashboard.app:app',
    '--host 127.0.0.1',
    `--port ${options.apiPort}`
  ].join(' ');
}
