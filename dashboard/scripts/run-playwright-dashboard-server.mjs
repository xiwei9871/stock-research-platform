import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path, { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);

export function buildViteInvocation({ env, nodeExecutable, viteCli, dashboardRoot, port, apiPort, preview }) {
  return {
    executable: nodeExecutable,
    args: [viteCli, ...(preview ? ['preview'] : []), '--host', '127.0.0.1', '--port', String(port)],
    cwd: dashboardRoot,
    env: {
      ...env,
      VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`
    }
  };
}

export function forwardSignal(child, signal) {
  if (!child.killed) child.kill(signal);
}

function parsePort(args, name, fallback) {
  const index = args.indexOf(name);
  const value = Number(index >= 0 ? args[index + 1] : fallback);
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error(`invalid ${name} value: ${value}`);
  }
  return value;
}

export function resolveViteCliPath(viteEntry, platform) {
  const paths = platform === 'win32' ? path.win32 : path.posix;
  return paths.resolve(paths.dirname(viteEntry), '../../bin/vite.js');
}

function main() {
  const args = process.argv.slice(2);
  const invocation = buildViteInvocation({
    env: process.env,
    nodeExecutable: process.execPath,
    viteCli: resolveViteCliPath(require.resolve('vite'), process.platform),
    dashboardRoot: fileURLToPath(new URL('..', import.meta.url)),
    port: parsePort(args, '--port', '5174'),
    apiPort: parsePort(args, '--api-port', '8766'),
    preview: args.includes('--preview')
  });
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
