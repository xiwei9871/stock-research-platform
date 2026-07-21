// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { createHash } from 'node:crypto';
// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
// @ts-expect-error Playwright runs this reporter in Node; the browser application tsconfig omits Node typings.
import { basename, resolve } from 'node:path';

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
import type { CandidateSnapshot } from './candidateDisplay';

export type EodCollectedTest = {
  title: string;
  projectName: string;
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
  candidateSnapshotRequired?: boolean;
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
  status: 'success' | 'degraded' | 'failed';
  tests: Array<EodCollectedTest & { severity: string }>;
  failures: string[];
  attachments: Array<{ test: string; name: string; contentType: string; path?: string }>;
  candidateSnapshot: CandidateSnapshot | null;
  candidateSnapshotSha256: string | null;
};

type EodReporterOptions = {
  outputDir?: string;
};

const CANDIDATE_ATTACHMENT = 'eod-candidate-snapshot.json';
declare const process: {
  env: Record<string, string | undefined>;
  pid: number;
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
    .replace(
      /(?:\/Users\/[^/\s]+|\/home\/[^/\s]+)\/[^\s]*?\/dashboard(?=\/|\s|$)/g,
      '<path>'
    )
    .replace(/(?:[A-Za-z]:\\|\/(?:private\/)?tmp\/)[^\s)\]}]+/g, '<path>');
}

function severityFor(title: string): string {
  const blocker = title.match(/@blocker-([a-z0-9_-]+)/i);
  if (blocker) return `blocker-${blocker[1].toLowerCase()}`;
  if (/@warning\b/i.test(title)) return 'warning';
  return 'error';
}

function isFailureStatus(status: string): boolean {
  return ['failed', 'timedOut', 'interrupted'].includes(status);
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
  const tests = input.tests.map((test) => ({
    ...sanitizeDeep(test),
    severity: severityFor(test.title)
  }));
  const failures = [
    ...(input.globalFailures ?? []).map(sanitizeEodText),
    ...(input.candidateSnapshotErrors ?? []).map(sanitizeEodText)
  ];
  const candidateSnapshot = canonicalCandidate(
    input.candidateSnapshots,
    failures,
    input.candidateSnapshotRequired ?? true,
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
    status,
    tests,
    failures,
    attachments: tests.flatMap((test) =>
      test.attachments.map((attachment) => ({ test: test.title, ...attachment }))
    ),
    candidateSnapshot: sanitizedCandidate,
    candidateSnapshotSha256: sanitizedCandidate
      ? createHash('sha256').update(stableJson(sanitizedCandidate)).digest('hex')
      : null
  };
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

function collectAttachments(result: TestResult): EodCollectedTest['attachments'] {
  return result.attachments.map((attachment) => ({
    name: sanitizeEodText(attachment.name),
    contentType: sanitizeEodText(attachment.contentType),
    ...(attachment.path ? { path: sanitizeEodText(basename(attachment.path)) } : {})
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

export default class EodReporter implements Reporter {
  private readonly outputDir: string;
  private readonly tests: EodCollectedTest[] = [];
  private readonly candidateSnapshots: CandidateSnapshot[] = [];
  private readonly candidateSnapshotErrors: string[] = [];
  private readonly globalFailures: string[] = [];
  private startedAt = new Date().toISOString();

  constructor(options: EodReporterOptions = {}) {
    this.outputDir = resolve(
      options.outputDir ?? process.env.PLAYWRIGHT_EOD_OUTPUT_DIR ?? 'test-results/eod'
    );
  }

  onBegin(_config: FullConfig, _suite: Suite): void {
    this.startedAt = new Date().toISOString();
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const projectName = test.parent.project()?.name ?? 'unknown';
    const titleParts = test.titlePath().filter(Boolean);
    if (titleParts[0] === projectName) titleParts.shift();
    const title = titleParts.join(' › ');
    this.tests.push({
      title,
      projectName,
      status: result.status,
      durationMs: result.duration,
      failures: collectFailures(result),
      attachments: collectAttachments(result)
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
      runId:
        process.env.PLAYWRIGHT_EOD_RUN_ID ??
        `playwright-eod-${process.env.PLAYWRIGHT_EOD_TRADE_DATE ?? 'unknown'}-${this.startedAt}`,
      tradeDate: process.env.PLAYWRIGHT_EOD_TRADE_DATE ?? '',
      revision:
        process.env.PLAYWRIGHT_EOD_REVISION ?? process.env.GITHUB_SHA ?? 'unknown',
      startedAt: this.startedAt,
      endedAt,
      tests: this.tests,
      candidateSnapshots: this.candidateSnapshots,
      candidateSnapshotRequired: this.tests.some((test) => /@eod\b/.test(test.title)),
      candidateSnapshotErrors: this.candidateSnapshotErrors,
      globalFailures: this.globalFailures
    });
    writeAtomicJson(this.outputDir, report);
    return report.status === 'failed' ? { status: 'failed' } : undefined;
  }
}
