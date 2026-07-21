// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { createHash } from 'node:crypto';
// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { closeSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { relative, resolve } from 'node:path';

import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestError,
  TestResult
} from '@playwright/test/reporter';

import { sanitizeRuntimeEvidenceText } from '../assertions/runtime';
import {
  REQUIRED_EOD_GATE_IDS,
  eodGateTag,
  type CandidateSnapshot,
  type RequiredEodGateId
} from './candidateDisplay';

export type EodCollectedTest = {
  testId?: string;
  title: string;
  projectName: string;
  retry?: number;
  status: string;
  durationMs: number;
  failures: string[];
  attachments: Array<{ name: string; contentType: string; path?: string }>;
};

export type EodAcceptanceReportInput = {
  runId: string;
  tradeDate: string;
  revision: string;
  startedAt: string;
  endedAt: string;
  tests: EodCollectedTest[];
  candidateSnapshots: CandidateSnapshot[];
  contractOnly?: boolean;
  candidateSnapshotErrors?: string[];
  globalFailures?: string[];
};

export type EodAcceptanceReport = {
  schemaVersion: 'playwright-eod-browser-acceptance/v1';
  runId: string;
  tradeDate: string;
  revision: string;
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  contractOnly: boolean;
  status: 'success' | 'degraded' | 'failed';
  tests: EodReportedTest[];
  failures: string[];
  attachments: Array<{
    test: string;
    retry: number;
    name: string;
    contentType: string;
    path?: string;
  }>;
  candidateSnapshot: CandidateSnapshot | null;
  candidateSnapshotSha256: string | null;
};

export type EodTestAttempt = {
  retry: number;
  status: string;
  durationMs: number;
  failures: string[];
  attachments: EodCollectedTest['attachments'];
};

export type EodReportedTest = {
  testId: string;
  title: string;
  projectName: string;
  retry: number;
  status: string;
  durationMs: number;
  failures: string[];
  attachments: EodCollectedTest['attachments'];
  severity: string;
  attemptHistory: EodTestAttempt[];
};

type EodReporterOptions = {
  outputDir?: string;
};

const CANDIDATE_ATTACHMENT = 'eod-candidate-snapshot.json';
declare const process: {
  env: Record<string, string | undefined>;
  pid: number;
  cwd(): string;
  kill(pid: number, signal: number): void;
};

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (typeof value !== 'object' || value === null) return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, nested]) => [key, stableValue(nested)])
  );
}

function stableJson(value: unknown): string {
  return JSON.stringify(stableValue(value));
}

function sanitizeDeep<T>(value: T): T {
  if (typeof value === 'string') return sanitizeEodText(value) as T;
  if (Array.isArray(value)) return value.map((item) => sanitizeDeep(item)) as T;
  if (typeof value !== 'object' || value === null) return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, nested]) => [
      key,
      sanitizeDeep(nested)
    ])
  ) as T;
}

export function sanitizeEodText(value: string): string {
  return sanitizeRuntimeEvidenceText(value.replace(/\u001B\[[0-?]*[ -/]*[@-~]/g, ''))
    .replace(/\bfile:\/\/[^\s"'<>()[\]{}]+/gi, 'file://<path>')
    .replace(/\\\\[^\\\s]+\\[^\s)\]}]+/g, '<path>')
    .replace(/(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s)\]}]+/g, '<path>')
    .replace(
      /(?<![:/\w])\/(?!\/)(?!(?:api|stock|theme-research|strategy-lab|review-queue|research)(?:\/|$))[^\s"'<>(){}]+/g,
      '<path>'
    );
}

function portableBasename(pathname: string): string {
  return pathname.split(/[\\/]/).filter(Boolean).at(-1) ?? 'attachment';
}

function safeRelativePath(pathname: string, root: string): string | null {
  if (/^[A-Za-z]:[\\/]|^\\\\/.test(pathname)) return null;
  const candidate = relative(root, pathname).replace(/\\/g, '/');
  if (candidate === '' || candidate === '..' || candidate.startsWith('../')) return null;
  return candidate;
}

export function safeAttachmentReference(
  pathname: string,
  workspaceRoot: string,
  outputDir: string
): string {
  const workspaceRelative = safeRelativePath(pathname, workspaceRoot);
  if (workspaceRelative) return workspaceRelative;
  const outputRelative = safeRelativePath(pathname, outputDir);
  if (outputRelative) return `output/${outputRelative}`;
  const safeName = portableBasename(pathname).replace(/[^A-Za-z0-9._-]+/g, '_');
  const digest = createHash('sha256').update(pathname).digest('hex').slice(0, 16);
  return `external-${digest}-${safeName || 'attachment'}`;
}

function severityFor(title: string): string {
  const blocker = title.match(/@blocker-([a-z0-9_-]+)/i);
  if (blocker) return `blocker-${blocker[1].toLowerCase()}`;
  if (/@warning\b/i.test(title)) return 'warning';
  return 'error';
}

function gateIdsForTitle(title: string): RequiredEodGateId[] {
  return REQUIRED_EOD_GATE_IDS.filter((gateId) => title.includes(eodGateTag(gateId)));
}

function isFailureStatus(status: string): boolean {
  return ['failed', 'timedOut', 'interrupted'].includes(status);
}

function normalizeTests(
  collected: EodCollectedTest[],
  failures: string[]
): EodReportedTest[] {
  const byTestId = new Map<string, Array<EodCollectedTest & { testId: string; retry: number }>>();
  for (const test of collected) {
    const normalized = {
      ...sanitizeDeep(test),
      testId: test.testId ?? `${test.projectName}:${test.title}`,
      retry: test.retry ?? 0
    };
    const attempts = byTestId.get(normalized.testId) ?? [];
    attempts.push(normalized);
    byTestId.set(normalized.testId, attempts);
  }

  return [...byTestId.values()].map((attempts) => {
    const ordered = [...attempts].sort((left, right) => left.retry - right.retry);
    const finalRetry = ordered[ordered.length - 1].retry;
    const finalAttempts = ordered.filter((attempt) => attempt.retry === finalRetry);
    if (finalAttempts.length !== 1) {
      failures.push(
        `eod_report_test_attempt_duplicate:${finalAttempts[0].testId}:${finalRetry}`
      );
    }
    const final = finalAttempts[finalAttempts.length - 1];
    return {
      testId: final.testId,
      title: final.title,
      projectName: final.projectName,
      retry: final.retry,
      status: final.status,
      durationMs: final.durationMs,
      failures: final.failures,
      attachments: final.attachments,
      severity: severityFor(final.title),
      attemptHistory: ordered.map((attempt) => ({
        retry: attempt.retry,
        status: attempt.status,
        durationMs: attempt.durationMs,
        failures: attempt.failures,
        attachments: attempt.attachments
      }))
    };
  });
}

function validateRequiredGates(
  collected: EodCollectedTest[],
  finalTests: EodReportedTest[],
  failures: string[]
): void {
  const claimsByTestId = new Map<string, Set<RequiredEodGateId>>();
  for (const test of collected) {
    const testId = test.testId ?? `${test.projectName}:${test.title}`;
    const claims = claimsByTestId.get(testId) ?? new Set<RequiredEodGateId>();
    for (const gateId of gateIdsForTitle(test.title)) claims.add(gateId);
    claimsByTestId.set(testId, claims);
  }
  for (const [testId, claims] of claimsByTestId) {
    if (claims.size > 1) {
      failures.push(
        `eod_report_gate_test_claims_multiple:${testId}:${[...claims].join(',')}`
      );
    }
  }
  const distinctFinalTestIds = new Set<string>();
  for (const gateId of REQUIRED_EOD_GATE_IDS) {
    const claimedTestIds = new Set(
      collected
        .filter((test) => gateIdsForTitle(test.title).includes(gateId))
        .map((test) => test.testId ?? `${test.projectName}:${test.title}`)
    );
    if (claimedTestIds.size === 0) {
      failures.push(`eod_report_gate_missing:${gateId}`);
      continue;
    }
    if (claimedTestIds.size !== 1) {
      failures.push(`eod_report_gate_duplicate:${gateId}`);
      continue;
    }
    const [testId] = claimedTestIds;
    distinctFinalTestIds.add(testId);
    const final = finalTests.find((test) => test.testId === testId);
    if (!final) {
      failures.push(`eod_report_gate_missing_final:${gateId}`);
      continue;
    }
    if (final.status !== 'passed') {
      failures.push(`eod_report_gate_final_status:${gateId}:${final.status}`);
    }
  }
  if (distinctFinalTestIds.size !== REQUIRED_EOD_GATE_IDS.length) {
    failures.push('eod_report_gate_test_ids_not_distinct');
  }
}

function canonicalCandidate(
  snapshots: CandidateSnapshot[],
  failures: string[],
  required: boolean,
  tradeDate: string
): CandidateSnapshot | null {
  if (snapshots.length === 0) {
    if (required) failures.push('eod_report_candidate_snapshot_missing');
    return null;
  }
  const unique = new Map(snapshots.map((snapshot) => [stableJson(snapshot), snapshot]));
  if (unique.size !== 1) {
    failures.push('eod_report_candidate_snapshot_conflict');
    return null;
  }
  const candidate = [...unique.values()][0] as unknown;
  if (
    typeof candidate !== 'object' ||
    candidate === null ||
    Array.isArray(candidate) ||
    (candidate as { schemaVersion?: unknown }).schemaVersion !==
      'playwright-eod-candidate-snapshot/v1' ||
    typeof (candidate as { tradeDate?: unknown }).tradeDate !== 'string' ||
    !Array.isArray((candidate as { publications?: unknown }).publications)
  ) {
    failures.push('eod_report_candidate_snapshot_schema_invalid');
    return null;
  }
  const validatedCandidate = candidate as CandidateSnapshot;
  if (validatedCandidate.tradeDate !== tradeDate) {
    failures.push(
      `eod_report_candidate_snapshot_trade_date_mismatch:${validatedCandidate.tradeDate}:${tradeDate}`
    );
    return null;
  }
  const publicationsValid = validatedCandidate.publications.every(
    (publication) =>
      typeof publication === 'object' &&
      publication !== null &&
      typeof publication.strategyId === 'string' &&
      typeof publication.tradeDate === 'string' &&
      typeof publication.totalReturnPct === 'number' &&
      Number.isFinite(publication.totalReturnPct) &&
      typeof publication.contractId === 'string' &&
      publication.contractId.length > 0 &&
      typeof publication.publishId === 'string' &&
      publication.publishId.length > 0 &&
      typeof publication.publishStartedAt === 'string' &&
      publication.publishStartedAt.length > 0 &&
      typeof publication.artifactVersion === 'string' &&
      publication.artifactVersion.length > 0
  );
  const strategyIds = validatedCandidate.publications
    .map((publication) => publication.strategyId)
    .sort();
  if (
    !publicationsValid ||
    JSON.stringify(strategyIds) !==
    JSON.stringify(['lhb_shortline', 'mid_trend', 'tech_bottleneck']) ||
    validatedCandidate.publications.some((publication) => publication.tradeDate !== tradeDate)
  ) {
    failures.push('eod_report_candidate_snapshot_publications_invalid');
    return null;
  }
  return validatedCandidate;
}

export function buildEodAcceptanceReport(
  input: EodAcceptanceReportInput
): EodAcceptanceReport {
  const failures = [
    ...(input.globalFailures ?? []).map(sanitizeEodText),
    ...(input.candidateSnapshotErrors ?? []).map(sanitizeEodText)
  ];
  const tests = normalizeTests(input.tests, failures);
  const contractOnly = input.contractOnly === true;
  if (contractOnly) {
    const mixedGateIds = new Set(input.tests.flatMap((test) => gateIdsForTitle(test.title)));
    for (const gateId of mixedGateIds) {
      failures.push(`eod_report_contract_only_contains_gate:${gateId}`);
    }
  } else {
    validateRequiredGates(input.tests, tests, failures);
  }
  const candidateSnapshot = canonicalCandidate(
    input.candidateSnapshots,
    failures,
    !contractOnly,
    input.tradeDate
  );
  let hasWarningFailure = false;
  let hasBlockingFailure = failures.length > 0;
  for (const test of tests) {
    if (!isFailureStatus(test.status)) continue;
    const details = test.failures.length > 0 ? test.failures : [`${test.title}: ${test.status}`];
    failures.push(...details.map((detail) => `${test.title}: ${detail}`));
    if (test.severity === 'warning') hasWarningFailure = true;
    else hasBlockingFailure = true;
  }
  const sanitizedCandidate = candidateSnapshot ? sanitizeDeep(candidateSnapshot) : null;
  const started = Date.parse(input.startedAt);
  const ended = Date.parse(input.endedAt);
  const durationSeconds =
    Number.isFinite(started) && Number.isFinite(ended) ? Math.max(0, (ended - started) / 1000) : 0;
  const status = hasBlockingFailure ? 'failed' : hasWarningFailure ? 'degraded' : 'success';
  return {
    schemaVersion: 'playwright-eod-browser-acceptance/v1',
    runId: sanitizeEodText(input.runId),
    tradeDate: sanitizeEodText(input.tradeDate),
    revision: sanitizeEodText(input.revision),
    startedAt: input.startedAt,
    endedAt: input.endedAt,
    durationSeconds,
    contractOnly,
    status,
    tests,
    failures,
    attachments: tests.flatMap((test) =>
      test.attemptHistory.flatMap((attempt) =>
        attempt.attachments.map((attachment) => ({
          test: test.title,
          retry: attempt.retry,
          ...attachment
        }))
      )
    ),
    candidateSnapshot: sanitizedCandidate,
    candidateSnapshotSha256: sanitizedCandidate
      ? createHash('sha256').update(stableJson(sanitizedCandidate)).digest('hex')
      : null
  };
}

export type ExistingEodReportLockState = 'active' | 'stale' | 'invalid';
export type EodReportLockMetadata = { pid: number; run_id: string; startedAt: string };
export type EodReportLockOperations = {
  openExclusive(pathname: string): number;
  read(pathname: string): string;
  remove(pathname: string): void;
  write(fileDescriptor: number, value: string): void;
  close(fileDescriptor: number): void;
};

export function classifyExistingEodReportLock(
  raw: string,
  isPidAlive: (pid: number) => boolean
): ExistingEodReportLockState {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      Array.isArray(parsed) ||
      Object.keys(parsed).sort().join(',') !== 'pid,run_id,startedAt' ||
      typeof parsed.pid !== 'number' ||
      !Number.isInteger(parsed.pid) ||
      parsed.pid <= 0 ||
      typeof parsed.run_id !== 'string' ||
      parsed.run_id.trim() === '' ||
      typeof parsed.startedAt !== 'string' ||
      Number.isNaN(Date.parse(parsed.startedAt))
    ) {
      return 'invalid';
    }
    return isPidAlive(parsed.pid) ? 'active' : 'stale';
  } catch {
    return 'invalid';
  }
}

export function acquireEodReportLock(
  lockPath: string,
  metadata: EodReportLockMetadata,
  operations: EodReportLockOperations,
  isPidAlive: (pid: number) => boolean
): number {
  let fileDescriptor: number;
  try {
    fileDescriptor = operations.openExclusive(lockPath);
  } catch (error) {
    if ((error as { code?: string }).code !== 'EEXIST') {
      throw new Error('eod_report_output_lock_invalid');
    }
    let state: ExistingEodReportLockState;
    try {
      state = classifyExistingEodReportLock(operations.read(lockPath), isPidAlive);
    } catch {
      state = 'invalid';
    }
    if (state === 'active') throw new Error('eod_report_output_lock_held');
    if (state === 'invalid') throw new Error('eod_report_output_lock_invalid');
    try {
      operations.remove(lockPath);
      fileDescriptor = operations.openExclusive(lockPath);
    } catch {
      throw new Error('eod_report_output_lock_invalid');
    }
  }

  try {
    operations.write(fileDescriptor, `${JSON.stringify(metadata)}\n`);
  } catch {
    try {
      operations.close(fileDescriptor);
      operations.remove(lockPath);
    } catch {
      // The original write failure remains the authoritative fail-closed result.
    }
    throw new Error('eod_report_output_lock_invalid');
  }
  return fileDescriptor;
}

export function playwrightStatusForReportStatus(
  status: EodAcceptanceReport['status']
): FullResult['status'] {
  return status === 'failed' ? 'failed' : 'passed';
}

function attachmentBody(result: TestResult, name: string): string | null {
  const attachment = result.attachments.find((candidate) => candidate.name === name);
  if (!attachment) return null;
  try {
    if (attachment.body) return attachment.body.toString('utf8');
    if (attachment.path) return readFileSync(attachment.path, 'utf8');
  } catch (error) {
    return JSON.stringify({ attachmentReadError: error instanceof Error ? error.message : String(error) });
  }
  return '';
}

function collectAttachments(
  result: TestResult,
  workspaceRoot: string,
  outputDir: string
): EodCollectedTest['attachments'] {
  return result.attachments.map((attachment) => ({
    name: sanitizeEodText(attachment.name),
    contentType: sanitizeEodText(attachment.contentType),
    ...(attachment.path
      ? { path: safeAttachmentReference(attachment.path, workspaceRoot, outputDir) }
      : {})
  }));
}

function collectFailures(result: TestResult): string[] {
  return result.errors.map((error) =>
    sanitizeEodText(error.message || error.value || 'playwright_test_failure')
  );
}

function writeAtomicJson(outputDir: string, report: EodAcceptanceReport): void {
  mkdirSync(outputDir, { recursive: true });
  const outputPath = resolve(outputDir, 'eod-browser-acceptance.json');
  const temporaryPath = `${outputPath}.tmp-${process.pid}`;
  writeFileSync(temporaryPath, `${JSON.stringify(report, null, 2)}\n`, {
    encoding: 'utf8',
    mode: 0o600
  });
  renameSync(temporaryPath, outputPath);
}

function processIdAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if ((error as { code?: string }).code === 'ESRCH') return false;
    throw error;
  }
}

function reportRunId(startedAt: string): string {
  return (
    process.env.PLAYWRIGHT_EOD_RUN_ID ??
    `playwright-eod-${process.env.PLAYWRIGHT_EOD_TRADE_DATE ?? 'unknown'}-${startedAt}`
  );
}

export default class EodReporter implements Reporter {
  private readonly outputDir: string;
  private readonly tests: EodCollectedTest[] = [];
  private readonly candidateSnapshots: CandidateSnapshot[] = [];
  private readonly candidateSnapshotErrors: string[] = [];
  private readonly globalFailures: string[] = [];
  private lockFileDescriptor: number | null = null;
  private readonly lockPath: string;
  private startedAt = new Date().toISOString();

  constructor(options: EodReporterOptions = {}) {
    this.outputDir = resolve(
      options.outputDir ?? process.env.PLAYWRIGHT_EOD_OUTPUT_DIR ?? 'test-results/eod'
    );
    this.lockPath = resolve(this.outputDir, 'eod-browser-acceptance.json.lock');
  }

  private releaseLock(): void {
    if (this.lockFileDescriptor === null) return;
    closeSync(this.lockFileDescriptor);
    this.lockFileDescriptor = null;
    try {
      unlinkSync(this.lockPath);
    } catch {
      // A missing lock is already released; other cleanup failures remain fail-closed on next run.
    }
  }

  private acquireLock(runId: string): void {
    mkdirSync(this.outputDir, { recursive: true });
    this.lockFileDescriptor = acquireEodReportLock(
      this.lockPath,
      { pid: process.pid, run_id: runId, startedAt: this.startedAt },
      {
        openExclusive: (pathname) => openSync(pathname, 'wx', 0o600),
        read: (pathname) => readFileSync(pathname, 'utf8'),
        remove: (pathname) => unlinkSync(pathname),
        write: (fileDescriptor, value) => writeFileSync(fileDescriptor, value),
        close: (fileDescriptor) => closeSync(fileDescriptor)
      },
      processIdAlive
    );
  }

  onBegin(_config: FullConfig, _suite: Suite): void {
    this.startedAt = new Date().toISOString();
    this.acquireLock(reportRunId(this.startedAt));
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const projectName = test.parent.project()?.name ?? 'unknown';
    const titleParts = test.titlePath().filter(Boolean);
    if (titleParts[0] === projectName) titleParts.shift();
    const title = titleParts.join(' › ');
    this.tests.push({
      testId: test.id,
      title,
      projectName,
      retry: result.retry,
      status: result.status,
      durationMs: result.duration,
      failures: collectFailures(result),
      attachments: collectAttachments(result, process.cwd(), this.outputDir)
    });
    const candidateBody = attachmentBody(result, CANDIDATE_ATTACHMENT);
    if (candidateBody === null) return;
    try {
      this.candidateSnapshots.push(JSON.parse(candidateBody) as CandidateSnapshot);
    } catch (error) {
      this.candidateSnapshotErrors.push(
        `eod_report_candidate_snapshot_invalid:${
          error instanceof Error ? error.message : String(error)
        }`
      );
    }
  }

  onError(error: TestError): void {
    this.globalFailures.push(
      `playwright_global_error:${sanitizeEodText(error.message || error.value || 'unknown')}`
    );
  }

  async onEnd(result: FullResult): Promise<void | { status?: FullResult['status'] }> {
    const endedAt = new Date().toISOString();
    if (result.status !== 'passed' && this.tests.every((test) => !isFailureStatus(test.status))) {
      this.globalFailures.push(`playwright_run_status:${result.status}`);
    }
    const report = buildEodAcceptanceReport({
      runId: reportRunId(this.startedAt),
      tradeDate: process.env.PLAYWRIGHT_EOD_TRADE_DATE ?? '',
      revision:
        process.env.PLAYWRIGHT_EOD_REVISION ?? process.env.GITHUB_SHA ?? 'unknown',
      startedAt: this.startedAt,
      endedAt,
      tests: this.tests,
      candidateSnapshots: this.candidateSnapshots,
      contractOnly: process.env.PLAYWRIGHT_EOD_CONTRACT_ONLY === 'true',
      candidateSnapshotErrors: this.candidateSnapshotErrors,
      globalFailures: this.globalFailures
    });
    try {
      writeAtomicJson(this.outputDir, report);
      return { status: playwrightStatusForReportStatus(report.status) };
    } finally {
      this.releaseLock();
    }
  }

  async onExit(): Promise<void> {
    this.releaseLock();
  }
}
