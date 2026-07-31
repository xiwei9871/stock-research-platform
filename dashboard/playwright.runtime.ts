type RuntimeEnvironment = Record<string, string | undefined>;

export function ensureThemeReportFixtureToken(env: RuntimeEnvironment, createToken: () => string) {
  const token = env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN ?? createToken();
  env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN = token;
  return token;
}

export function buildPlaywrightApiServerCommand(apiPort: number) {
  return `node scripts/run-playwright-api-server.mjs --port ${apiPort}`;
}
