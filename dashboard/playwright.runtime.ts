type RuntimeEnvironment = Record<string, string | undefined>;

export function ensureThemeReportFixtureToken(env: RuntimeEnvironment, createToken: () => string) {
  const token = env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN ?? createToken();
  env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN = token;
  return token;
}

export function buildPlaywrightApiServerCommand(apiPort: number) {
  return `node scripts/run-playwright-api-server.mjs --port ${apiPort}`;
}

export function buildPlaywrightDashboardServerCommand(options: {
  port: number;
  apiPort: number;
  preview: boolean;
}) {
  const command =
    `node scripts/run-playwright-dashboard-server.mjs --port ${options.port} --api-port ${options.apiPort}`;
  return options.preview ? `${command} --preview` : command;
}
