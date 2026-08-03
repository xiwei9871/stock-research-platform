import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path, { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

function platformPath(platform) {
  return platform === 'win32' ? path.win32 : path.posix;
}

export function pythonCandidates({ env, repoRoot, sharedRepoRoot, platform }) {
  const paths = platformPath(platform);
  const virtualenvPython = platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
  const candidates = [];
  if (env.PLAYWRIGHT_PYTHON) candidates.push(env.PLAYWRIGHT_PYTHON);
  if (env.VIRTUAL_ENV) candidates.push(paths.join(env.VIRTUAL_ENV, ...virtualenvPython));
  candidates.push(paths.join(repoRoot, '.venv', ...virtualenvPython));
  if (sharedRepoRoot && sharedRepoRoot !== repoRoot) {
    candidates.push(paths.join(sharedRepoRoot, '.venv', ...virtualenvPython));
  }
  candidates.push(platform === 'win32' ? 'python' : 'python3');
  return candidates;
}

export function selectPython(options, exists = existsSync) {
  const candidates = pythonCandidates(options);
  if (options.env.PLAYWRIGHT_PYTHON) return candidates[0];
  return candidates.find((candidate, index) => index === candidates.length - 1 || exists(candidate));
}

export function buildPythonInvocation({ env, repoRoot, python, port, platform }) {
  const realMode = env.PLAYWRIGHT_THEME_REPORT_REAL_E2E === 'true';
  const separator = platform === 'win32' ? ';' : ':';
  const currentSrc = platformPath(platform).join(repoRoot, 'src');
  const childEnv = {
    ...env,
    PYTHONPATH: env.PYTHONPATH ? `${currentSrc}${separator}${env.PYTHONPATH}` : currentSrc,
    PLAYWRIGHT_CURRENT_CHECKOUT: repoRoot
  };
  if (!realMode) {
    childEnv.STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED = 'false';
    childEnv.STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED = 'false';
  }
  return {
    executable: python,
    args: realMode
      ? ['tests/support/theme_research_report_e2e_server.py', '--host', '127.0.0.1', '--port', String(port)]
      : ['-m', 'uvicorn', 'stock_research.dashboard.app:app', '--host', '127.0.0.1', '--port', String(port)],
    cwd: repoRoot,
    env: childEnv
  };
}

export function forwardSignal(child, signal) {
  if (!child.killed) child.kill(signal);
}

function sharedRepositoryRoot(repoRoot) {
  try {
    const commonGitDir = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], {
      cwd: repoRoot,
      encoding: 'utf8'
    }).trim();
    return dirname(commonGitDir);
  } catch {
    return undefined;
  }
}

function parsePort(args) {
  const index = args.indexOf('--port');
  const port = Number(index >= 0 ? args[index + 1] : '8766');
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`invalid Playwright API port: ${port}`);
  return port;
}

function main() {
  const repoRoot = fileURLToPath(new URL('../..', import.meta.url));
  const platform = process.platform;
  const python = selectPython({
    env: process.env,
    repoRoot,
    sharedRepoRoot: sharedRepositoryRoot(repoRoot),
    platform
  });
  const invocation = buildPythonInvocation({
    env: process.env,
    repoRoot,
    python,
    port: parsePort(process.argv.slice(2)),
    platform
  });

  if (process.argv.includes('--print-import-root')) {
    const result = spawnSync(
      invocation.executable,
      ['-c', 'import pathlib, stock_research; print(pathlib.Path(stock_research.__file__).resolve())'],
      { cwd: invocation.cwd, env: invocation.env, stdio: 'inherit' }
    );
    if (result.error) throw result.error;
    process.exitCode = result.status ?? 1;
    return;
  }

  const child = spawn(invocation.executable, invocation.args, {
    cwd: invocation.cwd,
    env: invocation.env,
    stdio: 'inherit'
  });
  const forwardTerm = () => forwardSignal(child, 'SIGTERM');
  const forwardInterrupt = () => forwardSignal(child, 'SIGINT');
  process.on('SIGTERM', forwardTerm);
  process.on('SIGINT', forwardInterrupt);
  child.on('error', (error) => {
    throw error;
  });
  child.on('exit', (code) => {
    process.removeListener('SIGTERM', forwardTerm);
    process.removeListener('SIGINT', forwardInterrupt);
    process.exitCode = code ?? 1;
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
