import type { Page, Route } from '@playwright/test';

export const OFFICIAL_EOD_STRATEGY_IDS = [
  'lhb_shortline',
  'mid_trend',
  'tech_bottleneck'
] as const;

export const REQUIRED_EOD_GATE_IDS = [
  'candidate-consistency',
  'publication-consistency',
  'runtime-deep-links'
] as const;

export type RequiredEodGateId = (typeof REQUIRED_EOD_GATE_IDS)[number];

export function eodGateTag(gateId: RequiredEodGateId): string {
  return `@eod-gate-${gateId}`;
}

export type OfficialEodStrategyId = (typeof OFFICIAL_EOD_STRATEGY_IDS)[number];

export type CandidatePublication = {
  strategyId: OfficialEodStrategyId;
  tradeDate: string;
  totalReturnPct: number;
  contractId: string;
  publishId: string;
  publishStartedAt: string;
  artifactVersion: string;
};

export type CandidateSnapshot = {
  schemaVersion: 'playwright-eod-candidate-snapshot/v1';
  tradeDate: string;
  publications: CandidatePublication[];
};

export type CandidatePayloads = {
  catalog: unknown;
  reviewQueue: unknown;
  readiness: unknown;
  summary: unknown;
};

export type CandidateJsonFetcher = (path: string) => Promise<unknown>;

export type CandidateDisplayEvidence = {
  overriddenEndpoints: string[];
  effectiveQueries: Array<{ endpoint: string; query: string }>;
  rejectedWrites: Array<{ method: string; endpoint: string }>;
};

export type CriticalResponseRequirement = {
  id: string;
  method: string;
  pathname: string;
};

export type CriticalResponseExchange = {
  requirementId: string;
  method: string;
  pathname: string;
  status: number;
};

export type CriticalResponseLedger = {
  record(method: string, pathname: string, status: number): void;
  assertComplete(): void;
  evidence(): { journey: string; requirements: CriticalResponseRequirement[]; exchanges: CriticalResponseExchange[] };
};

type JsonObject = Record<string, unknown>;

type PreviousPublications = {
  schemaVersion: 'playwright-eod-previous-publications/v1';
  publications: CandidatePublication[];
};

type CandidateDisplayDecision =
  | { action: 'continue' }
  | { action: 'reject-write'; endpoint: string; method: string }
  | { action: 'override'; endpoint: string; effectiveUrl: string };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_TIMESTAMP_WITH_ZONE = /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/;
const ALLOWED_API_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const OVERRIDDEN_EXACT_ENDPOINTS = new Set([
  '/api/platform/readiness',
  '/api/platform/summary',
  '/api/platform/display-date',
  '/api/review-queue'
]);
const ROOT_SELECTOR_FIELDS: Record<string, ReadonlySet<string>> = {
  '/api/platform/display-date': new Set([
    'display_trade_date',
    'candidate_trade_date',
    'latest_market_date',
    'latest_trade_date'
  ]),
  '/api/platform/readiness': new Set([
    'display_trade_date',
    'candidate_trade_date',
    'latest_market_date',
    'latest_trade_date'
  ]),
  '/api/platform/summary': new Set([
    'display_trade_date',
    'candidate_trade_date',
    'latest_market_date',
    'latest_trade_date'
  ]),
  '/api/review-queue': new Set([
    'trade_date',
    'display_trade_date',
    'candidate_trade_date',
    'selected_trade_date',
    'generated_trade_date'
  ])
};
const MARKET_MONITOR_ROOT_SELECTOR_FIELDS = new Set([
  'trade_date',
  'display_trade_date',
  'candidate_trade_date',
  'selected_trade_date'
]);
const PREVIOUS_ROOT_KEYS = ['publications', 'schemaVersion'];
const PUBLICATION_KEYS = [
  'artifactVersion',
  'contractId',
  'publishId',
  'publishStartedAt',
  'strategyId',
  'totalReturnPct',
  'tradeDate'
];

function environmentValue(name: string): string | undefined {
  return (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.[name];
}

function fail(code: string, detail?: string): never {
  throw new Error(detail ? `${code}:${detail}` : code);
}

export function createCriticalResponseLedger(
  journey: string,
  requirements: readonly CriticalResponseRequirement[]
): CriticalResponseLedger {
  const stableRequirements = requirements.map((requirement) => ({
    ...requirement,
    method: requirement.method.toUpperCase()
  }));
  const exchanges: CriticalResponseExchange[] = [];
  return {
    record(method, pathname, status) {
      const normalizedMethod = method.toUpperCase();
      for (const requirement of stableRequirements) {
        if (requirement.method === normalizedMethod && requirement.pathname === pathname) {
          exchanges.push({
            requirementId: requirement.id,
            method: normalizedMethod,
            pathname,
            status
          });
        }
      }
    },
    assertComplete() {
      for (const requirement of stableRequirements) {
        const matches = exchanges.filter(
          (exchange) => exchange.requirementId === requirement.id
        );
        const failed = matches.find((exchange) => exchange.status >= 400);
        if (failed) {
          fail(
            'critical_request_http_status',
            `${journey}:${requirement.id}:${requirement.method}:${requirement.pathname}:${failed.status}`
          );
        }
        if (!matches.some((exchange) => exchange.status >= 200 && exchange.status < 400)) {
          fail(
            'critical_request_missing_success',
            `${journey}:${requirement.id}:${requirement.method}:${requirement.pathname}`
          );
        }
      }
    },
    evidence() {
      return {
        journey,
        requirements: stableRequirements.map((requirement) => ({ ...requirement })),
        exchanges: exchanges.map((exchange) => ({ ...exchange }))
      };
    }
  };
}

function objectValue(value: unknown, code: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(code);
  return value as JsonObject;
}

function arrayValue(value: unknown, code: string): unknown[] {
  if (!Array.isArray(value)) fail(code);
  return value;
}

function exactKeys(value: JsonObject, expected: readonly string[], code: string): void {
  const actual = Object.keys(value).sort();
  const stableExpected = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(stableExpected)) fail(code);
}

function requiredString(value: unknown, code: string): string {
  if (typeof value !== 'string' || value.trim() === '' || value.trim() !== value) fail(code);
  return value;
}

function requiredDate(value: unknown, code: string): string {
  const date = requiredString(value, code);
  if (!ISO_DATE.test(date)) fail(code);
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== date) fail(code);
  return date;
}

function requiredTimestamp(value: unknown, code: string): string {
  const timestamp = requiredString(value, code);
  if (!ISO_TIMESTAMP_WITH_ZONE.test(timestamp) || Number.isNaN(Date.parse(timestamp))) fail(code);
  return timestamp;
}

function requiredFiniteNumber(value: unknown, code: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(code);
  return value;
}

function isOfficialStrategyId(value: string): value is OfficialEodStrategyId {
  return (OFFICIAL_EOD_STRATEGY_IDS as readonly string[]).includes(value);
}

function parseStrictPublication(value: unknown, codePrefix: string): CandidatePublication {
  const publication = objectValue(value, `${codePrefix}_invalid`);
  exactKeys(publication, PUBLICATION_KEYS, `${codePrefix}_schema_invalid`);
  const strategyId = requiredString(publication.strategyId, `${codePrefix}_strategy_id_missing`);
  if (!isOfficialStrategyId(strategyId)) fail(`${codePrefix}_strategy_id_invalid`, strategyId);
  return {
    strategyId,
    tradeDate: requiredDate(publication.tradeDate, `${codePrefix}_trade_date_invalid`),
    totalReturnPct: requiredFiniteNumber(
      publication.totalReturnPct,
      `${codePrefix}_total_return_invalid`
    ),
    contractId: requiredString(publication.contractId, `${codePrefix}_contract_id_missing`),
    publishId: requiredString(publication.publishId, `${codePrefix}_publish_id_missing`),
    publishStartedAt: requiredTimestamp(
      publication.publishStartedAt,
      `${codePrefix}_publish_started_at_invalid`
    ),
    artifactVersion: requiredString(
      publication.artifactVersion,
      `${codePrefix}_artifact_version_missing`
    )
  };
}

export function parsePreviousPublicationsJson(raw: string): PreviousPublications {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    fail('eod_previous_publications_json_invalid');
  }
  const root = objectValue(value, 'eod_previous_publications_schema_invalid:root');
  exactKeys(root, PREVIOUS_ROOT_KEYS, 'eod_previous_publications_schema_invalid:root_keys');
  if (root.schemaVersion !== 'playwright-eod-previous-publications/v1') {
    fail('eod_previous_publications_schema_invalid:schema_version');
  }
  const rawPublications = arrayValue(
    root.publications,
    'eod_previous_publications_schema_invalid:publications'
  );
  if (rawPublications.length !== OFFICIAL_EOD_STRATEGY_IDS.length) {
    fail('eod_previous_publications_schema_invalid:publication_count');
  }
  const publications = rawPublications.map((publication, index) =>
    parseStrictPublication(publication, `eod_previous_publications:${index}`)
  );
  for (const strategyId of OFFICIAL_EOD_STRATEGY_IDS) {
    const count = publications.filter((publication) => publication.strategyId === strategyId).length;
    if (count !== 1) {
      fail('eod_previous_publications_schema_invalid:strategy_count', `${strategyId}:${count}`);
    }
  }
  return { schemaVersion: 'playwright-eod-previous-publications/v1', publications };
}

function matchingObjects(items: unknown[], strategyId: OfficialEodStrategyId): JsonObject[] {
  return items.flatMap((value) => {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return [];
    const object = value as JsonObject;
    return object.strategy_id === strategyId ? [object] : [];
  });
}

function queueItems(payload: JsonObject): unknown[] {
  const groups = arrayValue(payload.groups, 'eod_candidate_review_queue_groups_invalid');
  return groups.flatMap((group, index) =>
    arrayValue(
      objectValue(group, `eod_candidate_review_queue_group_invalid:${index}`).items,
      `eod_candidate_review_queue_items_invalid:${index}`
    )
  );
}

function parseCatalogPublication(
  strategyId: OfficialEodStrategyId,
  catalogItems: unknown[],
  targetTradeDate: string
): CandidatePublication {
  const matches = matchingObjects(catalogItems, strategyId);
  if (matches.length !== 1) {
    fail('eod_candidate_catalog_strategy_count', `${strategyId}:${matches.length}`);
  }
  const metrics = objectValue(
    matches[0].latest_metrics,
    `eod_candidate_catalog_metrics_missing:${strategyId}`
  );
  if (metrics.contract_status !== 'success') {
    fail('eod_candidate_catalog_contract_mismatch', strategyId);
  }
  const tradeDate = requiredDate(
    metrics.performance_as_of_date,
    `eod_candidate_catalog_performance_date_missing:${strategyId}`
  );
  if (tradeDate !== targetTradeDate) {
    fail('eod_candidate_performance_date_mismatch', `${strategyId}:${tradeDate}:${targetTradeDate}`);
  }
  return {
    strategyId,
    tradeDate,
    totalReturnPct: requiredFiniteNumber(
      metrics.total_return_pct,
      `eod_candidate_catalog_total_return_invalid:${strategyId}`
    ),
    contractId: requiredString(
      metrics.contract_id,
      `eod_candidate_catalog_contract_id_missing:${strategyId}`
    ),
    publishId: requiredString(
      metrics.publish_id,
      `eod_candidate_catalog_publish_id_missing:${strategyId}`
    ),
    publishStartedAt: requiredTimestamp(
      metrics.publish_started_at,
      `eod_candidate_catalog_publish_started_at_missing:${strategyId}`
    ),
    artifactVersion: requiredString(
      metrics.artifact_version,
      `eod_candidate_catalog_artifact_version_missing:${strategyId}`
    )
  };
}

function queueIdentity(item: JsonObject, strategyId: OfficialEodStrategyId) {
  if (item.contract_status !== 'success') {
    fail('eod_candidate_review_queue_contract_mismatch', strategyId);
  }
  return {
    strategyId,
    tradeDate: requiredDate(
      item.performance_as_of_date,
      `eod_candidate_review_queue_performance_date_missing:${strategyId}`
    ),
    totalReturnPct: requiredFiniteNumber(
      item.total_return_pct,
      `eod_candidate_review_queue_total_return_invalid:${strategyId}`
    ),
    contractId: requiredString(
      item.contract_id,
      `eod_candidate_review_queue_contract_id_missing:${strategyId}`
    ),
    publishId: requiredString(
      item.publish_id,
      `eod_candidate_review_queue_publish_id_missing:${strategyId}`
    ),
    artifactVersion: requiredString(
      item.artifact_version,
      `eod_candidate_review_queue_artifact_version_missing:${strategyId}`
    )
  };
}

function comparableIdentity(publication: CandidatePublication) {
  return {
    strategyId: publication.strategyId,
    tradeDate: publication.tradeDate,
    totalReturnPct: publication.totalReturnPct,
    contractId: publication.contractId,
    publishId: publication.publishId,
    artifactVersion: publication.artifactVersion
  };
}

function assertReviewQueueIdentity(
  candidate: CandidatePublication,
  allQueueItems: unknown[]
): void {
  const matches = matchingObjects(allQueueItems, candidate.strategyId);
  if (matches.length === 0) {
    fail('eod_candidate_review_queue_strategy_missing', candidate.strategyId);
  }
  const expected = JSON.stringify(comparableIdentity(candidate));
  if (
    matches.some(
      (item) => JSON.stringify(queueIdentity(item, candidate.strategyId)) !== expected
    )
  ) {
    fail('eod_candidate_review_queue_identity_mismatch', candidate.strategyId);
  }
}

function assertPayloadDate(
  payload: JsonObject,
  field: string,
  targetTradeDate: string,
  code: string
): void {
  const actual = requiredDate(payload[field], `${code}_missing`);
  if (actual !== targetTradeDate) fail(`${code}_mismatch`, `${actual}:${targetTradeDate}`);
}

function assertNoRollback(
  candidate: CandidatePublication,
  previous: CandidatePublication
): void {
  if (candidate.tradeDate < previous.tradeDate) {
    fail(
      'eod_candidate_publication_rollback',
      `${candidate.strategyId}:${candidate.tradeDate}:${previous.tradeDate}`
    );
  }
  if (
    candidate.tradeDate === previous.tradeDate &&
    Date.parse(candidate.publishStartedAt) <= Date.parse(previous.publishStartedAt)
  ) {
    fail('eod_candidate_publish_started_at_not_newer', candidate.strategyId);
  }
}

export function parseCandidateSnapshot(
  targetTradeDate: string,
  payloads: CandidatePayloads,
  previousPublicationsJson: string | undefined
): CandidateSnapshot {
  const target = requiredDate(targetTradeDate, 'eod_candidate_target_trade_date_missing');
  if (
    typeof previousPublicationsJson !== 'string' ||
    previousPublicationsJson.trim() === ''
  ) {
    fail('eod_previous_publications_required');
  }
  const catalog = objectValue(payloads.catalog, 'eod_candidate_catalog_invalid');
  const reviewQueue = objectValue(payloads.reviewQueue, 'eod_candidate_review_queue_invalid');
  const readiness = objectValue(payloads.readiness, 'eod_candidate_readiness_invalid');
  const summary = objectValue(payloads.summary, 'eod_candidate_summary_invalid');
  assertPayloadDate(reviewQueue, 'trade_date', target, 'eod_candidate_review_queue_trade_date');
  assertPayloadDate(readiness, 'candidate_trade_date', target, 'eod_candidate_readiness_candidate_date');
  assertPayloadDate(readiness, 'latest_market_date', target, 'eod_candidate_readiness_latest_date');
  assertPayloadDate(summary, 'latest_market_date', target, 'eod_candidate_summary_latest_date');

  const catalogItems = arrayValue(catalog.items, 'eod_candidate_catalog_items_invalid');
  const allQueueItems = queueItems(reviewQueue);
  const publications = OFFICIAL_EOD_STRATEGY_IDS.map((strategyId) =>
    parseCatalogPublication(strategyId, catalogItems, target)
  );
  for (const publication of publications) {
    assertReviewQueueIdentity(publication, allQueueItems);
  }

  const previous = parsePreviousPublicationsJson(previousPublicationsJson);
  for (const candidate of publications) {
    const prior = previous.publications.find(
      (publication) => publication.strategyId === candidate.strategyId
    );
    if (!prior) fail('eod_previous_publications_strategy_missing', candidate.strategyId);
    assertNoRollback(candidate, prior);
  }

  return {
    schemaVersion: 'playwright-eod-candidate-snapshot/v1',
    tradeDate: target,
    publications
  };
}

async function loadCandidatePayloads(
  targetTradeDate: string,
  fetchJson: CandidateJsonFetcher
): Promise<CandidatePayloads> {
  const encodedDate = encodeURIComponent(targetTradeDate);
  const [catalog, reviewQueue, readiness, summary] = await Promise.all([
    fetchJson('/api/strategies/catalog'),
    fetchJson(`/api/review-queue?trade_date=${encodedDate}`),
    fetchJson('/api/platform/readiness'),
    fetchJson('/api/platform/summary')
  ]);
  return { catalog, reviewQueue, readiness, summary };
}

export async function loadCandidateSnapshotWithPrevious(
  targetTradeDate: string,
  fetchJson: CandidateJsonFetcher,
  previousPublicationsJson: string | undefined
): Promise<CandidateSnapshot> {
  const payloads = await loadCandidatePayloads(targetTradeDate, fetchJson);
  return parseCandidateSnapshot(
    targetTradeDate,
    payloads,
    previousPublicationsJson
  );
}

export async function loadCandidateSnapshot(
  targetTradeDate: string,
  fetchJson: CandidateJsonFetcher
): Promise<CandidateSnapshot> {
  return loadCandidateSnapshotWithPrevious(
    targetTradeDate,
    fetchJson,
    environmentValue('PLAYWRIGHT_EOD_PREVIOUS_PUBLICATIONS_JSON')
  );
}

function isOverriddenEndpoint(pathname: string): boolean {
  return OVERRIDDEN_EXACT_ENDPOINTS.has(pathname) || pathname.startsWith('/api/market-monitor/');
}

function safeUrl(rawUrl: string): URL | null {
  try {
    return new URL(rawUrl);
  } catch {
    return null;
  }
}

function isApiPath(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

function decodePathLayer(pathname: string): string {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return pathname.replace(/%([0-9a-f]{2})/gi, (_match, encoded: string) => {
      const value = Number.parseInt(encoded, 16);
      return value <= 0x7f ? String.fromCharCode(value) : `%${encoded.toUpperCase()}`;
    });
  }
}

function hasMalformedPercent(value: string): boolean {
  return /%(?![0-9a-f]{2})/i.test(value);
}

function isApiUrl(rawUrl: string): boolean {
  const url = safeUrl(rawUrl);
  if (!url) return false;
  let pathname = url.pathname;
  for (let layer = 0; layer < 8; layer += 1) {
    if (isApiPath(pathname)) return true;
    if (pathname.startsWith('/api%') && hasMalformedPercent(pathname.slice(4))) return true;
    const decoded = decodePathLayer(pathname);
    if (decoded === pathname) return false;
    pathname = decoded;
  }
  return (
    isApiPath(pathname) ||
    (pathname.startsWith('/api%') && hasMalformedPercent(pathname.slice(4)))
  );
}

export function candidateDisplayDecision(
  method: string,
  rawUrl: string,
  targetTradeDate: string
): CandidateDisplayDecision {
  const normalizedMethod = method.toUpperCase();
  const url = safeUrl(rawUrl);
  if (!url) return { action: 'continue' };
  const endpoint = url.pathname;
  if (isApiUrl(rawUrl) && !ALLOWED_API_METHODS.has(normalizedMethod)) {
    return { action: 'reject-write', endpoint, method: normalizedMethod };
  }
  if (normalizedMethod !== 'GET' || !isOverriddenEndpoint(endpoint)) {
    return { action: 'continue' };
  }
  if (endpoint === '/api/review-queue') {
    url.searchParams.set('trade_date', targetTradeDate);
  }
  return { action: 'override', endpoint, effectiveUrl: url.toString() };
}

export function rewriteCandidateDisplayPayload(
  pathname: string,
  payload: unknown,
  targetTradeDate: string
): unknown {
  if (!isOverriddenEndpoint(pathname)) return payload;
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return payload;
  const selectorFields = pathname.startsWith('/api/market-monitor/')
    ? MARKET_MONITOR_ROOT_SELECTOR_FIELDS
    : ROOT_SELECTOR_FIELDS[pathname];
  if (!selectorFields) return payload;
  return Object.fromEntries(
    Object.entries(payload as JsonObject).map(([key, value]) => [
      key,
      selectorFields.has(key) ? targetTradeDate : value
    ])
  );
}

function stableQuery(rawUrl: string): string {
  const url = new URL(rawUrl);
  const entries = [...url.searchParams.entries()].sort(([leftKey, leftValue], [rightKey, rightValue]) =>
    leftKey === rightKey ? leftValue.localeCompare(rightValue) : leftKey.localeCompare(rightKey)
  );
  return new URLSearchParams(entries).toString();
}

export function isHandledRouteLifecycleError(error: unknown): boolean {
  return error instanceof Error && error.message.includes('route.fulfill: Route is already handled!');
}

async function fulfillCandidateRoute(route: Route, options: Parameters<Route['fulfill']>[0]): Promise<void> {
  try {
    await route.fulfill(options);
  } catch (error) {
    if (isHandledRouteLifecycleError(error)) return;
    throw error;
  }
}

async function handleCandidateRoute(
  route: Route,
  targetTradeDate: string,
  evidence: CandidateDisplayEvidence
): Promise<void> {
  const request = route.request();
  const decision = candidateDisplayDecision(request.method(), request.url(), targetTradeDate);
  if (decision.action === 'continue') {
    await route.continue();
    return;
  }
  if (decision.action === 'reject-write') {
    evidence.rejectedWrites.push({ method: decision.method, endpoint: decision.endpoint });
    await route.fulfill({
      status: 405,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'playwright_eod_read_only_api_guard' })
    });
    return;
  }

  evidence.overriddenEndpoints.push(decision.endpoint);
  evidence.effectiveQueries.push({
    endpoint: decision.endpoint,
    query: stableQuery(decision.effectiveUrl)
  });
  const response = await route.fetch({ url: decision.effectiveUrl });
  const contentType = response.headers()['content-type'] ?? '';
  if (!response.ok() || !contentType.includes('application/json')) {
    await fulfillCandidateRoute(route, { response });
    return;
  }
  const payload = await response.json();
  const rewritten = rewriteCandidateDisplayPayload(
    decision.endpoint,
    payload,
    targetTradeDate
  );
  await fulfillCandidateRoute(route, { response, body: JSON.stringify(rewritten) });
}

export async function installCandidateDisplayOverride(
  page: Page,
  targetTradeDate: string
): Promise<CandidateDisplayEvidence> {
  const target = requiredDate(targetTradeDate, 'eod_candidate_target_trade_date_missing');
  const evidence: CandidateDisplayEvidence = {
    overriddenEndpoints: [],
    effectiveQueries: [],
    rejectedWrites: []
  };
  await page.context().route('**/*', (route) => handleCandidateRoute(route, target, evidence));
  return evidence;
}
