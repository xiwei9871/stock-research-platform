import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);

export function buildThemeReportE2EInvocation(extraArgs = [], inheritedEnv = process.env) {
  const forwardedArgs = [...extraArgs];
  while (forwardedArgs[0] === '--') forwardedArgs.shift();
  return {
    executable: process.execPath,
    args: [
      require.resolve('@playwright/test/cli'),
      'test',
      'tests/theme-research-full-flow.spec.ts',
      ...forwardedArgs
    ],
    env: {
      ...inheritedEnv,
      PLAYWRIGHT_THEME_REPORT_REAL_E2E: 'true'
    }
  };
}

function main() {
  const invocation = buildThemeReportE2EInvocation(process.argv.slice(2));
  const result = spawnSync(invocation.executable, invocation.args, {
    cwd: resolve(fileURLToPath(new URL('..', import.meta.url))),
    env: invocation.env,
    stdio: 'inherit'
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
