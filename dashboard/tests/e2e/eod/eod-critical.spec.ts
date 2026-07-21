import {
  test as contractTest,
  expect as contractExpect,
  type APIRequestContext,
  type Page,
  type TestInfo
} from '@playwright/test';

import { expectPublicationConsistency, expectRouteContext } from '../assertions/consistency';
import { expect, test } from '../fixtures/test';
import {
  candidateDisplayDecision,
  installCandidateDisplayOverride,
  loadCandidateSnapshot,
  loadCandidateSnapshotWithPrevious,
  parseCandidateSnapshot,
  parsePreviousPublicationsJson,
  rewriteCandidateDisplayPayload,
  type CandidatePayloads
} from './candidateDisplay';
import { buildEodAcceptanceReport, sanitizeEodText } from './eodReporter';

const TARGET_DATE = '2026-07-20';
const STRATEGY_IDS = ['lhb_shortline', 'mid_trend', 'tech_bottleneck'] as const;

function publication(strategyId: (typeof STRATEGY_IDS)[number], index: number) {
  return {
    strategyId,
    tradeDate: TARGET_DATE,
    totalReturnPct: 40 + index,
    contractId: `${strategyId}:contract:v1`,
    publishId: `${strategyId}:publish:20260720`,
    publishStartedAt: `2026-07-20T0${index + 1}:00:00Z`,
    artifactVersion: `${strategyId}:artifact:v1`
  };
}

function candidatePayloads(): CandidatePayloads {
  const publications = STRATEGY_IDS.map(publication);
  return {
    catalog: {
      items: publications.map((item) => ({
        strategy_id: item.strategyId,
        latest_metrics: {
          performance_as_of_date: item.tradeDate,
          total_return_pct: item.totalReturnPct,
          contract_id: item.contractId,
          publish_id: item.publishId,
          publish_started_at: item.publishStartedAt,
          artifact_version: item.artifactVersion,
          contract_status: 'success'
        }
      }))
    },
    reviewQueue: {
      trade_date: TARGET_DATE,
      groups: publications.map((item) => ({
        items: [
          {
            strategy_id: item.strategyId,
            performance_as_of_date: item.tradeDate,
            total_return_pct: item.totalReturnPct,
            contract_id: item.contractId,
            publish_id: item.publishId,
            artifact_version: item.artifactVersion,
            contract_status: 'success'
          }
        ]
      }))
    },
    readiness: {
      candidate_trade_date: TARGET_DATE,
      latest_market_date: TARGET_DATE,
      display_trade_date: '2026-07-19'
    },
    summary: {
      latest_market_date: TARGET_DATE,
      latest_score_date: TARGET_DATE
    }
  };
}

function clonePayloads(): CandidatePayloads {
  return structuredClone(candidatePayloads());
}

function catalogMetrics(payloads: CandidatePayloads, strategyIndex = 0) {
  return (
    (payloads.catalog as { items: Array<{ latest_metrics: Record<string, unknown> }> }).items[
      strategyIndex
    ].latest_metrics
  );
}

function queueItem(payloads: CandidatePayloads, strategyIndex = 0) {
  return (
    (payloads.reviewQueue as { groups: Array<{ items: Array<Record<string, unknown>> }> }).groups[
      strategyIndex
    ].items[0]
  );
}

function previousJson(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    schemaVersion: 'playwright-eod-previous-publications/v1',
    publications: STRATEGY_IDS.map((strategyId, index) => ({
      ...publication(strategyId, index),
      tradeDate: '2026-07-19',
      publishStartedAt: `2026-07-19T0${index + 1}:00:00Z`
    })),
    ...overrides
  });
}

async function withPreviousPublicationsEnvironment(
  value: string | undefined,
  action: () => Promise<void>
): Promise<void> {
  const environment = (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env;
  if (!environment) throw new Error('playwright_eod_process_environment_missing');
  const name = 'PLAYWRIGHT_EOD_PREVIOUS_PUBLICATIONS_JSON';
  const previous = environment[name];
  if (value === undefined) delete environment[name];
  else environment[name] = value;
  try {
    await action();
  } finally {
    if (previous === undefined) delete environment[name];
    else environment[name] = previous;
  }
}

contractTest.describe('EOD candidate snapshot contracts', () => {
  contractTest('rejects a missing target trade date', () => {
    contractExpect(() => parseCandidateSnapshot('', clonePayloads(), previousJson())).toThrow(
      'eod_candidate_target_trade_date_missing'
    );
  });

  contractTest('rejects a missing official strategy', () => {
    const payloads = clonePayloads();
    (payloads.catalog as { items: unknown[] }).items.pop();
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_strategy_count:tech_bottleneck:0'
    );
  });

  contractTest('rejects a nonfinite return', () => {
    const payloads = clonePayloads();
    catalogMetrics(payloads).total_return_pct = Number.NaN;
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_total_return_invalid:lhb_shortline'
    );
  });

  contractTest('rejects a failed publication contract', () => {
    const payloads = clonePayloads();
    catalogMetrics(payloads).contract_status = 'contract_mismatch';
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_contract_mismatch:lhb_shortline'
    );
  });

  contractTest('rejects a missing publish ID', () => {
    const payloads = clonePayloads();
    delete catalogMetrics(payloads).publish_id;
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_publish_id_missing:lhb_shortline'
    );
  });

  contractTest('rejects a missing publish start timestamp', () => {
    const payloads = clonePayloads();
    delete catalogMetrics(payloads).publish_started_at;
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_publish_started_at_missing:lhb_shortline'
    );
  });

  contractTest('rejects a missing artifact version', () => {
    const payloads = clonePayloads();
    delete catalogMetrics(payloads).artifact_version;
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_catalog_artifact_version_missing:lhb_shortline'
    );
  });

  contractTest('rejects a performance date different from the target', () => {
    const payloads = clonePayloads();
    catalogMetrics(payloads).performance_as_of_date = '2026-07-19';
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_performance_date_mismatch:lhb_shortline:2026-07-19:2026-07-20'
    );
  });

  contractTest('rejects a review queue publication identity mismatch', () => {
    const payloads = clonePayloads();
    queueItem(payloads).publish_id = 'different-publish';
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, previousJson())).toThrow(
      'eod_candidate_review_queue_identity_mismatch:lhb_shortline'
    );
  });

  contractTest('rejects publication rollback against the strict previous snapshot', () => {
    const laterPrevious = previousJson({
      publications: STRATEGY_IDS.map((strategyId, index) => ({
        ...publication(strategyId, index),
        tradeDate: '2026-07-21',
        publishStartedAt: `2026-07-21T0${index + 1}:00:00Z`
      }))
    });
    contractExpect(() =>
      parseCandidateSnapshot(TARGET_DATE, clonePayloads(), laterPrevious)
    ).toThrow('eod_candidate_publication_rollback:lhb_shortline:2026-07-20:2026-07-21');
  });

  contractTest('requires a strictly newer publish start time for a same-day rerun', () => {
    const payloads = clonePayloads();
    const sameDayPrevious = previousJson({
      publications: STRATEGY_IDS.map((strategyId, index) => ({
        ...publication(strategyId, index),
        publishStartedAt: index === 0 ? '2026-07-20T01:00:00Z' : `2026-07-20T0${index}:00:00Z`
      }))
    });
    contractExpect(() => parseCandidateSnapshot(TARGET_DATE, payloads, sameDayPrevious)).toThrow(
      'eod_candidate_publish_started_at_not_newer:lhb_shortline'
    );
  });

  contractTest('accepts a newer publish start time for a same-day rerun', () => {
    const sameDayPrevious = previousJson({
      publications: STRATEGY_IDS.map((strategyId, index) => ({
        ...publication(strategyId, index),
        publishStartedAt: `2026-07-20T0${index}:00:00Z`
      }))
    });
    contractExpect(
      parseCandidateSnapshot(TARGET_DATE, clonePayloads(), sameDayPrevious).tradeDate
    ).toBe(TARGET_DATE);
  });

  contractTest('accepts a later trade date even when the clock time is earlier', () => {
    contractExpect(
      parseCandidateSnapshot(TARGET_DATE, clonePayloads(), previousJson()).tradeDate
    ).toBe(TARGET_DATE);
  });

  contractTest('rejects extra keys in the previous-publication JSON schema', () => {
    contractExpect(() =>
      parsePreviousPublicationsJson(previousJson({ unexpected: true }))
    ).toThrow('eod_previous_publications_schema_invalid:root_keys');
  });

  contractTest('loads all four candidate endpoints through the injected fetch contract', async () => {
    const payloads = clonePayloads();
    const calls: string[] = [];
    const byPath = new Map<string, unknown>([
      ['/api/strategies/catalog', payloads.catalog],
      [`/api/review-queue?trade_date=${TARGET_DATE}`, payloads.reviewQueue],
      ['/api/platform/readiness', payloads.readiness],
      ['/api/platform/summary', payloads.summary]
    ]);

    const snapshot = await loadCandidateSnapshotWithPrevious(TARGET_DATE, async (path) => {
      calls.push(path);
      return byPath.get(path);
    }, previousJson());

    contractExpect(snapshot.publications).toHaveLength(3);
    contractExpect(calls).toEqual([
      '/api/strategies/catalog',
      `/api/review-queue?trade_date=${TARGET_DATE}`,
      '/api/platform/readiness',
      '/api/platform/summary'
    ]);
  });

  for (const [label, previous] of [
    ['missing', undefined],
    ['empty', ''],
    ['blank', '   ']
  ] as const) {
    contractTest(`production loading rejects ${label} previous publications`, async () => {
      const payloads = clonePayloads();
      const byPath = new Map<string, unknown>([
        ['/api/strategies/catalog', payloads.catalog],
        [`/api/review-queue?trade_date=${TARGET_DATE}`, payloads.reviewQueue],
        ['/api/platform/readiness', payloads.readiness],
        ['/api/platform/summary', payloads.summary]
      ]);
      await withPreviousPublicationsEnvironment(previous, async () => {
        await contractExpect(
          loadCandidateSnapshot(TARGET_DATE, async (path) => byPath.get(path))
        ).rejects.toThrow('eod_previous_publications_required');
      });
    });
  }

  contractTest('production loading rejects an empty previous publication set', async () => {
    const payloads = clonePayloads();
    const byPath = new Map<string, unknown>([
      ['/api/strategies/catalog', payloads.catalog],
      [`/api/review-queue?trade_date=${TARGET_DATE}`, payloads.reviewQueue],
      ['/api/platform/readiness', payloads.readiness],
      ['/api/platform/summary', payloads.summary]
    ]);
    await withPreviousPublicationsEnvironment(
      JSON.stringify({
          schemaVersion: 'playwright-eod-previous-publications/v1',
          publications: []
      }),
      async () => {
        await contractExpect(
          loadCandidateSnapshot(TARGET_DATE, async (path) => byPath.get(path))
        ).rejects.toThrow('eod_previous_publications_schema_invalid:publication_count');
      }
    );
  });
});

contractTest.describe('EOD candidate display rewrite contracts', () => {
  contractTest('rejects API writes locally and forces the review queue target query', () => {
    contractExpect(
      candidateDisplayDecision('POST', 'http://127.0.0.1:5176/api/review-queue', TARGET_DATE)
    ).toMatchObject({ action: 'reject-write' });
    contractExpect(
      candidateDisplayDecision(
        'GET',
        'http://127.0.0.1:5176/api/review-queue?trade_date=2026-07-19&limit=10',
        TARGET_DATE
      )
    ).toEqual({
      action: 'override',
      endpoint: '/api/review-queue',
      effectiveUrl:
        'http://127.0.0.1:5176/api/review-queue?trade_date=2026-07-20&limit=10'
    });
  });

  contractTest('passes publication, stock, theme, and auth reads through untouched', () => {
    for (const path of [
      '/api/strategies/catalog',
      '/api/stocks/000001.SZ',
      '/api/research/theme-decomposition/themes',
      '/api/auth/me'
    ]) {
      contractExpect(
        candidateDisplayDecision('GET', `http://127.0.0.1:5176${path}`, TARGET_DATE)
      ).toEqual({ action: 'continue' });
    }
  });

  contractTest('recognizes encoded, double-encoded, exact, and malformed possible API writes', () => {
    for (const path of [
      '/api',
      '/api/?q=1',
      '/%61pi/review-queue',
      '/api%2Freview-queue',
      '/api%252Freview-queue',
      '/%2561pi%252Freview-queue',
      '/api%ZZ'
    ]) {
      contractExpect(
        candidateDisplayDecision('POST', `http://127.0.0.1:5176${path}`, TARGET_DATE)
      ).toMatchObject({ action: 'reject-write' });
    }
    for (const path of ['/apiculture', '/v1/api/review-queue', '/assets/api-client.js']) {
      contractExpect(
        candidateDisplayDecision('POST', `http://127.0.0.1:5176${path}`, TARGET_DATE)
      ).toEqual({ action: 'continue' });
    }
  });

  contractTest('preserves fields while replacing only supported display date fields', () => {
    const source = {
      status: 'blocked',
      display_trade_date: '2026-07-19',
      candidate_trade_date: '2026-07-19',
      latest_market_date: '2026-07-19',
      nested: { trade_date: '2026-07-19', performance_as_of_date: '2026-07-19' }
    };
    contractExpect(
      rewriteCandidateDisplayPayload('/api/platform/readiness', source, TARGET_DATE)
    ).toEqual({
      status: 'blocked',
      display_trade_date: TARGET_DATE,
      candidate_trade_date: TARGET_DATE,
      latest_market_date: TARGET_DATE,
      nested: { trade_date: '2026-07-19', performance_as_of_date: '2026-07-19' }
    });
    contractExpect(source.display_trade_date).toBe('2026-07-19');
  });

  contractTest('keeps nested facts immutable for every overridden endpoint', () => {
    const cases = [
      {
        path: '/api/platform/display-date',
        source: {
          display_trade_date: '2026-07-19',
          candidate_trade_date: '2026-07-19',
          latest_market_date: '2026-07-19',
          display_gate: { trade_date: '2026-07-18', latest_trade_date: '2026-07-18' }
        },
        expectedRoot: { display_trade_date: TARGET_DATE, latest_market_date: TARGET_DATE }
      },
      {
        path: '/api/platform/readiness',
        source: {
          display_trade_date: '2026-07-19',
          candidate_trade_date: '2026-07-19',
          latest_market_date: '2026-07-19',
          modules: [{ trade_date: '2026-07-18', latest_trade_date: '2026-07-18' }]
        },
        expectedRoot: { display_trade_date: TARGET_DATE, latest_market_date: TARGET_DATE }
      },
      {
        path: '/api/platform/summary',
        source: {
          latest_market_date: '2026-07-19',
          items: [{ trade_date: '2026-07-18', latest_market_date: '2026-07-18' }]
        },
        expectedRoot: { latest_market_date: TARGET_DATE }
      },
      {
        path: '/api/market-monitor/eod',
        source: {
          trade_date: '2026-07-19',
          strategy_signals: [{ trade_date: '2026-07-18' }],
          stocks: [{ latest_trade_date: '2026-07-18' }]
        },
        expectedRoot: { trade_date: TARGET_DATE }
      },
      {
        path: '/api/review-queue',
        source: {
          trade_date: '2026-07-19',
          latest_trade_date: '2026-07-19',
          groups: [
            {
              trade_date: '2026-07-18',
              items: [
                {
                  trade_date: '2026-07-18',
                  latest_trade_date: '2026-07-18',
                  performance_as_of_date: '2026-07-18'
                }
              ]
            }
          ]
        },
        expectedRoot: { trade_date: TARGET_DATE, latest_trade_date: '2026-07-19' }
      }
    ];

    for (const candidate of cases) {
      const rewritten = rewriteCandidateDisplayPayload(
        candidate.path,
        candidate.source,
        TARGET_DATE
      ) as Record<string, unknown>;
      contractExpect(rewritten).toMatchObject(candidate.expectedRoot);
      for (const nestedKey of ['display_gate', 'modules', 'items', 'strategy_signals', 'stocks', 'groups']) {
        if (nestedKey in candidate.source) {
          contractExpect(rewritten[nestedKey]).toEqual(
            (candidate.source as Record<string, unknown>)[nestedKey]
          );
        }
      }
    }
  });

  contractTest('does not rewrite publication, stock, or theme payloads', () => {
    const source = { trade_date: '2026-07-19', publish_id: 'stable' };
    for (const path of [
      '/api/strategies/catalog',
      '/api/stocks/000001.SZ',
      '/api/research/theme-decomposition/themes'
    ]) {
      contractExpect(rewriteCandidateDisplayPayload(path, source, TARGET_DATE)).toBe(source);
    }
  });
});

contractTest.describe('EOD reporter contracts', () => {
  const snapshot = {
    schemaVersion: 'playwright-eod-candidate-snapshot/v1' as const,
    tradeDate: TARGET_DATE,
    publications: STRATEGY_IDS.map(publication)
  };

  contractTest('classifies warning-only failures as degraded', () => {
    const report = buildEodAcceptanceReport({
      runId: 'run-1',
      tradeDate: TARGET_DATE,
      revision: 'abc123',
      startedAt: '2026-07-20T01:00:00.000Z',
      endedAt: '2026-07-20T01:00:02.000Z',
      tests: [
        {
          title: 'visual drift @warning',
          projectName: 'chromium-desktop',
          status: 'failed',
          durationMs: 10,
          failures: ['minor drift'],
          attachments: []
        }
      ],
      candidateSnapshots: [snapshot]
    });
    contractExpect(report.status).toBe('degraded');
    contractExpect(report.tests[0].severity).toBe('warning');
  });

  contractTest('classifies blocker failures as failed', () => {
    const report = buildEodAcceptanceReport({
      runId: 'run-2',
      tradeDate: TARGET_DATE,
      revision: 'abc123',
      startedAt: '2026-07-20T01:00:00.000Z',
      endedAt: '2026-07-20T01:00:02.000Z',
      tests: [
        {
          title: 'identity mismatch @blocker-consistency',
          projectName: 'chromium-desktop',
          status: 'failed',
          durationMs: 10,
          failures: ['mismatch'],
          attachments: []
        }
      ],
      candidateSnapshots: [snapshot]
    });
    contractExpect(report.status).toBe('failed');
    contractExpect(report.tests[0].severity).toBe('blocker-consistency');
  });

  contractTest('fails the report when the candidate snapshot is missing or conflicting', () => {
    const base = {
      runId: 'run-3',
      tradeDate: TARGET_DATE,
      revision: 'abc123',
      startedAt: '2026-07-20T01:00:00.000Z',
      endedAt: '2026-07-20T01:00:02.000Z',
      tests: [],
      candidateSnapshots: []
    };
    contractExpect(buildEodAcceptanceReport(base).failures).toContain(
      'eod_report_candidate_snapshot_missing'
    );
    const conflicting = structuredClone(snapshot);
    conflicting.publications[0].publishId = 'different';
    contractExpect(
      buildEodAcceptanceReport({ ...base, candidateSnapshots: [snapshot, conflicting] }).failures
    ).toContain('eod_report_candidate_snapshot_conflict');
  });

  contractTest('sanitizes secrets and absolute workspace paths', () => {
    contractExpect(
      sanitizeEodText(
        'authorization=Bearer abc123 /Users/xiwei/stock_research/dashboard/token/private-value'
      )
    ).toBe('authorization=[REDACTED] <path>/token/[REDACTED]');
    contractExpect(sanitizeEodText('\u001b[31mError\u001b[0m')).toBe('Error');
  });

  contractTest('rejects a candidate snapshot for a different trade date', () => {
    const report = buildEodAcceptanceReport({
      runId: 'run-4',
      tradeDate: TARGET_DATE,
      revision: 'abc123',
      startedAt: '2026-07-20T01:00:00.000Z',
      endedAt: '2026-07-20T01:00:02.000Z',
      tests: [],
      candidateSnapshots: [{ ...snapshot, tradeDate: '2026-07-19' }]
    });
    contractExpect(report.status).toBe('failed');
    contractExpect(report.failures).toContain(
      'eod_report_candidate_snapshot_trade_date_mismatch:2026-07-19:2026-07-20'
    );
  });

  contractTest('fails closed for a malformed candidate attachment without throwing', () => {
    const report = buildEodAcceptanceReport({
      runId: 'run-5',
      tradeDate: TARGET_DATE,
      revision: 'abc123',
      startedAt: '2026-07-20T01:00:00.000Z',
      endedAt: '2026-07-20T01:00:02.000Z',
      tests: [],
      candidateSnapshots: [
        { schemaVersion: 'playwright-eod-candidate-snapshot/v1', tradeDate: TARGET_DATE } as never
      ]
    });
    contractExpect(report.status).toBe('failed');
    contractExpect(report.failures).toContain('eod_report_candidate_snapshot_schema_invalid');
    contractExpect(report.candidateSnapshot).toBeNull();
  });
});

type JsonObject = Record<string, unknown>;

function objectValue(value: unknown, code: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error(code);
  return value as JsonObject;
}

function arrayValue(value: unknown, code: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(code);
  return value;
}

function nonEmptyString(value: unknown, code: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(code);
  return value.trim();
}

function finiteNumber(value: unknown, code: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(code);
  return value;
}

function targetTradeDate(): string {
  const environment = (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env;
  return nonEmptyString(
    environment?.PLAYWRIGHT_EOD_TRADE_DATE,
    'playwright_eod_trade_date_required'
  );
}

async function apiJson(
  request: APIRequestContext,
  path: string,
  requestId: string
): Promise<unknown> {
  const response = await request.get(path, { headers: { 'x-request-id': requestId } });
  if (!response.ok()) throw new Error(`playwright_eod_api_error:${path}:${response.status()}`);
  return response.json() as Promise<unknown>;
}

async function candidateSnapshot(request: APIRequestContext) {
  const tradeDate = targetTradeDate();
  return loadCandidateSnapshot(tradeDate, (path) =>
    apiJson(request, path, `playwright-eod-candidate-${path.split(/[/?]/).filter(Boolean).join('-')}`)
  );
}

async function attachJson(testInfo: TestInfo, name: string, value: unknown): Promise<void> {
  await testInfo.attach(name, {
    body: `${JSON.stringify(value, null, 2)}\n`,
    contentType: 'application/json'
  });
}

function reviewQueueChoices(payload: unknown) {
  const root = objectValue(payload, 'playwright_eod_review_queue_invalid');
  const choices = new Map<string, { buttonName: string; count: number }>();
  for (const [groupIndex, rawGroup] of arrayValue(
    root.groups,
    'playwright_eod_review_queue_groups_invalid'
  ).entries()) {
    const group = objectValue(rawGroup, `playwright_eod_review_queue_group_invalid:${groupIndex}`);
    const label = nonEmptyString(group.label, `playwright_eod_review_queue_label_missing:${groupIndex}`);
    const count = finiteNumber(group.count, `playwright_eod_review_queue_count_missing:${groupIndex}`);
    const items = arrayValue(
      group.items,
      `playwright_eod_review_queue_items_invalid:${groupIndex}`
    );
    for (const rawItem of items) {
      const item = objectValue(rawItem, `playwright_eod_review_queue_item_invalid:${groupIndex}`);
      if (typeof item.strategy_id === 'string' && STRATEGY_IDS.includes(item.strategy_id as never)) {
        choices.set(item.strategy_id, { buttonName: `${label} ${count}`, count });
      }
    }
  }
  for (const strategyId of STRATEGY_IDS) {
    if (!choices.has(strategyId)) throw new Error(`playwright_eod_review_group_missing:${strategyId}`);
  }
  return choices;
}

async function expectFullPublication(
  container: ReturnType<Page['locator']>,
  publication: Awaited<ReturnType<typeof candidateSnapshot>>['publications'][number]
): Promise<void> {
  await expectPublicationConsistency(container, {
    contractId: publication.contractId,
    publishId: publication.publishId,
    tradeDate: publication.tradeDate,
    totalReturnPct: publication.totalReturnPct
  });
  await expect(container.getByText(publication.artifactVersion, { exact: true })).toBeVisible();
}

async function expectRenderedShell(page: Page): Promise<void> {
  await expect(page.locator('body')).not.toBeEmpty();
  await expect(page.locator('main')).toBeVisible();
  const visibleText = (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim();
  expect(visibleText.length).toBeGreaterThan(40);
}

async function loadDynamicDeepLinks(request: APIRequestContext, tradeDate: string) {
  const reviewPayload = objectValue(
    await apiJson(
      request,
      `/api/review-queue?trade_date=${encodeURIComponent(tradeDate)}`,
      'playwright-eod-deep-link-review-queue'
    ),
    'playwright_eod_deep_link_review_queue_invalid'
  );
  const reviewItems = arrayValue(
    reviewPayload.groups,
    'playwright_eod_deep_link_review_groups_invalid'
  ).flatMap((rawGroup, index) =>
    arrayValue(
      objectValue(rawGroup, `playwright_eod_deep_link_review_group_invalid:${index}`).items,
      `playwright_eod_deep_link_review_items_invalid:${index}`
    )
  );
  const stockItem = reviewItems
    .map((item, index) => objectValue(item, `playwright_eod_deep_link_review_item_invalid:${index}`))
    .find((item) => typeof item.canonical_asset_id === 'string' || typeof item.asset_id === 'string');
  if (!stockItem) throw new Error('playwright_eod_dynamic_stock_missing');
  const stockAssetId = nonEmptyString(
    stockItem.canonical_asset_id ?? stockItem.asset_id,
    'playwright_eod_dynamic_stock_id_missing'
  );

  const themes = objectValue(
    await apiJson(
      request,
      '/api/research/theme-decomposition/themes',
      'playwright-eod-deep-link-theme-list'
    ),
    'playwright_eod_dynamic_themes_invalid'
  );
  const theme = objectValue(
    arrayValue(themes.items, 'playwright_eod_dynamic_theme_items_invalid')[0],
    'playwright_eod_dynamic_theme_missing'
  );
  const themeId = nonEmptyString(theme.theme_id, 'playwright_eod_dynamic_theme_id_missing');

  const techStocks = objectValue(
    await apiJson(
      request,
      '/api/research/tech-bottleneck/review-universe/stocks?limit=500',
      'playwright-eod-deep-link-tech-stock'
    ),
    'playwright_eod_dynamic_tech_stocks_invalid'
  );
  const techStock = objectValue(
    arrayValue(techStocks.items, 'playwright_eod_dynamic_tech_stock_items_invalid')[0],
    'playwright_eod_dynamic_tech_stock_missing'
  );
  const techStockCode = nonEmptyString(
    techStock.stock_code,
    'playwright_eod_dynamic_tech_stock_code_missing'
  );

  return { stockAssetId, themeId, techStockCode };
}

test('home strategy cards exactly match the candidate snapshot @eod @blocker-consistency', async ({
  page,
  request
}, testInfo) => {
  const snapshot = await candidateSnapshot(request);
  await attachJson(testInfo, 'eod-candidate-snapshot.json', snapshot);
  const overrideEvidence = await installCandidateDisplayOverride(page, snapshot.tradeDate);
  try {
    await page.goto('/');
    await expect(page.getByRole('region', { name: '策略指挥中心' })).toBeVisible();
    for (const publication of snapshot.publications) {
      await expectFullPublication(
        page.locator(`article[data-strategy-id="${publication.strategyId}"]`),
        publication
      );
    }
    await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);
    await expect(page.getByText('175.29%', { exact: true })).toHaveCount(0);
  } finally {
    await attachJson(testInfo, 'eod-display-override.json', overrideEvidence);
  }
});

test('home strategy and review queue publication identities agree @eod @blocker-consistency', async ({
  page,
  request
}, testInfo) => {
  const snapshot = await candidateSnapshot(request);
  const queuePayload = await apiJson(
    request,
    `/api/review-queue?trade_date=${encodeURIComponent(snapshot.tradeDate)}`,
    'playwright-eod-publication-review-queue'
  );
  const reviewChoices = reviewQueueChoices(queuePayload);
  const overrideEvidence = await installCandidateDisplayOverride(page, snapshot.tradeDate);
  try {
    await page.goto('/');
    for (const publication of snapshot.publications) {
      const homeCard = page.locator(`article[data-strategy-id="${publication.strategyId}"]`);
      await expectFullPublication(homeCard, publication);
      await homeCard.getByRole('button', { name: /打开策略/ }).click();
      await expectRouteContext(page, { path: /^\/strategy-lab$/ });
      await expect(page).toHaveURL(new RegExp(`strategy_id=${publication.strategyId}$`));
      const strategyContract = page
        .locator(`[data-strategy-id="${publication.strategyId}"]`)
        .filter({ has: page.getByTestId('strategy-publish-id') })
        .first();
      await expectFullPublication(strategyContract, publication);
      await page.goto('/');
    }

    await page.goto('/review-queue');
    await expect(page.getByRole('region', { name: '策略复盘队列' })).toBeVisible();
    for (const publication of snapshot.publications) {
      const choice = reviewChoices.get(publication.strategyId);
      if (!choice) throw new Error(`playwright_eod_review_choice_missing:${publication.strategyId}`);
      await page.getByRole('button', { name: choice.buttonName, exact: true }).click();
      const reviewContract = page.locator(
        `[aria-label="选中标的证据"] [data-strategy-id="${publication.strategyId}"]`
      );
      await expectFullPublication(reviewContract, publication);
    }
    await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);
  } finally {
    await attachJson(testInfo, 'eod-display-override.json', overrideEvidence);
  }
});

test('dynamic stock theme and technology deep links render safely @eod @blocker-runtime', async ({
  page,
  request
}, testInfo) => {
  const tradeDate = targetTradeDate();
  const links = await loadDynamicDeepLinks(request, tradeDate);
  const overrideEvidence = await installCandidateDisplayOverride(page, tradeDate);
  try {
    await page.goto(`/stock/${encodeURIComponent(links.stockAssetId)}?source=review_queue`);
    await expectRouteContext(page, {
      path: new RegExp(`/stock/${links.stockAssetId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
      assetId: links.stockAssetId,
      source: 'review_queue'
    });
    await expect(page.getByRole('region', { name: '个股复盘工作台' })).toBeVisible();
    await expectRenderedShell(page);

    await page.goto(`/theme-research/${encodeURIComponent(links.themeId)}`);
    await expectRouteContext(page, {
      path: new RegExp(
        `^/theme-research/${links.themeId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`
      )
    });
    await expect(page.getByRole('region', { name: '主题研究详情' })).toBeVisible();
    await expectRenderedShell(page);

    await page.goto(
      `/stock/${encodeURIComponent(links.techStockCode)}?source=tech_bottleneck_review_universe`
    );
    await expectRouteContext(page, {
      path: new RegExp(
        `/stock/${links.techStockCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\.(?:SZ|SH))?$`
      ),
      source: 'tech_bottleneck_review_universe'
    });
    await expect(page.getByRole('region', { name: '个股复盘工作台' })).toBeVisible();
    await expectRenderedShell(page);
  } finally {
    await attachJson(testInfo, 'eod-display-override.json', overrideEvidence);
  }
});
