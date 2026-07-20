import type { Page } from '@playwright/test';

const OFFICIAL_STRATEGY_IDS = ['lhb_shortline', 'mid_trend', 'tech_bottleneck'] as const;

export type AuthoritativeSnapshot = {
  displayTradeDate: string;
  candidateTradeDate: string;
  strategies: Array<{
    strategyId: string;
    tradeDate: string;
    totalReturnPct: number;
    contractId: string;
    publishId: string;
    artifactVersion: string;
  }>;
};

type JsonObject = Record<string, unknown>;

type PublicationIdentity = {
  strategyId: string;
  tradeDate: string;
  totalReturnPct: number;
  contractId: string;
  publishId: string;
  artifactVersion: string;
};

function fail(code: string, detail?: string): never {
  throw new Error(detail ? `${code}:${detail}` : code);
}

function objectValue(value: unknown, code: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(code);
  return value as JsonObject;
}

function arrayValue(value: unknown, code: string): unknown[] {
  if (!Array.isArray(value)) fail(code);
  return value;
}

function requiredString(container: JsonObject, field: string, code: string): string {
  const value = container[field];
  if (typeof value !== 'string' || value.trim() === '' || value.trim() !== value) fail(code, field);
  return value;
}

function requiredFiniteNumber(container: JsonObject, field: string, code: string): number {
  const value = container[field];
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(code, field);
  return value;
}

function requiredIsoDate(container: JsonObject, field: string, code: string): string {
  const value = requiredString(container, field, code);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) fail(code, field);
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    fail(code, field);
  }
  return value;
}

function strategyId(container: JsonObject, code: string): string {
  return requiredString(container, 'strategy_id', code);
}

function catalogPublication(item: JsonObject, expectedStrategyId: string): PublicationIdentity {
  const actualStrategyId = strategyId(item, 'authoritative_snapshot_catalog_missing_strategy_id');
  if (actualStrategyId !== expectedStrategyId) {
    fail('authoritative_snapshot_catalog_strategy_mismatch', expectedStrategyId);
  }
  const metrics = objectValue(
    item.latest_metrics,
    `authoritative_snapshot_catalog_missing_latest_metrics:${expectedStrategyId}`
  );
  return {
    strategyId: expectedStrategyId,
    tradeDate: requiredIsoDate(
      metrics,
      'performance_as_of_date',
      `authoritative_snapshot_catalog_missing_performance_date:${expectedStrategyId}`
    ),
    totalReturnPct: requiredFiniteNumber(
      metrics,
      'total_return_pct',
      `authoritative_snapshot_catalog_missing_total_return:${expectedStrategyId}`
    ),
    contractId: requiredString(
      metrics,
      'contract_id',
      `authoritative_snapshot_catalog_missing_contract_id:${expectedStrategyId}`
    ),
    publishId: requiredString(
      metrics,
      'publish_id',
      `authoritative_snapshot_catalog_missing_publish_id:${expectedStrategyId}`
    ),
    artifactVersion: requiredString(
      metrics,
      'artifact_version',
      `authoritative_snapshot_catalog_missing_artifact_version:${expectedStrategyId}`
    )
  };
}

function queuePublication(item: JsonObject, expectedStrategyId: string): PublicationIdentity {
  const actualStrategyId = strategyId(item, 'authoritative_snapshot_queue_missing_strategy_id');
  if (actualStrategyId !== expectedStrategyId) {
    fail('authoritative_snapshot_queue_strategy_mismatch', expectedStrategyId);
  }
  return {
    strategyId: expectedStrategyId,
    tradeDate: requiredIsoDate(
      item,
      'performance_as_of_date',
      `authoritative_snapshot_queue_missing_performance_date:${expectedStrategyId}`
    ),
    totalReturnPct: requiredFiniteNumber(
      item,
      'total_return_pct',
      `authoritative_snapshot_queue_missing_total_return:${expectedStrategyId}`
    ),
    contractId: requiredString(
      item,
      'contract_id',
      `authoritative_snapshot_queue_missing_contract_id:${expectedStrategyId}`
    ),
    publishId: requiredString(
      item,
      'publish_id',
      `authoritative_snapshot_queue_missing_publish_id:${expectedStrategyId}`
    ),
    artifactVersion: requiredString(
      item,
      'artifact_version',
      `authoritative_snapshot_queue_missing_artifact_version:${expectedStrategyId}`
    )
  };
}

function identityKey(identity: PublicationIdentity): string {
  return JSON.stringify([
    identity.strategyId,
    identity.tradeDate,
    identity.totalReturnPct,
    identity.contractId,
    identity.publishId,
    identity.artifactVersion
  ]);
}

function matchingItem(
  items: unknown[],
  expectedStrategyId: string,
  source: 'catalog' | 'queue'
): JsonObject[] {
  return items
    .filter((value) => {
      if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
      return (value as JsonObject).strategy_id === expectedStrategyId;
    })
    .map((value) => objectValue(value, `authoritative_snapshot_${source}_invalid_item`));
}

function reviewQueueItems(payload: JsonObject): unknown[] {
  const groups = arrayValue(payload.groups, 'authoritative_snapshot_invalid_queue_groups');
  return groups.flatMap((value, index) => {
    const group = objectValue(value, `authoritative_snapshot_invalid_queue_group:${index}`);
    return arrayValue(group.items, `authoritative_snapshot_invalid_queue_group_items:${index}`);
  });
}

function verifyStrategy(
  expectedStrategyId: string,
  catalogItems: unknown[],
  queueItems: unknown[]
): AuthoritativeSnapshot['strategies'][number] {
  const catalogMatches = matchingItem(catalogItems, expectedStrategyId, 'catalog');
  if (catalogMatches.length !== 1) {
    fail(
      'authoritative_snapshot_catalog_strategy_count',
      `${expectedStrategyId}:${catalogMatches.length}`
    );
  }
  const catalog = catalogPublication(catalogMatches[0], expectedStrategyId);
  const queueMatches = matchingItem(queueItems, expectedStrategyId, 'queue');
  if (queueMatches.length === 0) {
    fail('authoritative_snapshot_queue_strategy_missing', expectedStrategyId);
  }
  const queuePublications = queueMatches.map((item) => queuePublication(item, expectedStrategyId));
  const catalogKey = identityKey(catalog);
  const conflict = queuePublications.find((publication) => identityKey(publication) !== catalogKey);
  if (conflict) {
    fail(
      'authoritative_snapshot_publication_identity_conflict',
      `${expectedStrategyId}:catalog=${catalogKey}:queue=${identityKey(conflict)}`
    );
  }
  return catalog;
}

async function getJson(page: Page, path: string, requestId: string): Promise<unknown> {
  return page.evaluate(
    async ({ apiPath, traceId }) => {
      const response = await fetch(apiPath, { headers: { 'x-request-id': traceId } });
      if (!response.ok) {
        throw new Error(`authoritative_snapshot_http_error:${apiPath}:${response.status}`);
      }
      return response.json() as Promise<unknown>;
    },
    { apiPath: path, traceId: requestId }
  );
}

export async function loadAuthoritativeSnapshot(page: Page): Promise<AuthoritativeSnapshot> {
  const displayPayload = objectValue(
    await getJson(page, '/api/platform/display-date', 'playwright-real-snapshot-display-date'),
    'authoritative_snapshot_invalid_display_date_payload'
  );
  const displayTradeDate = requiredIsoDate(
    displayPayload,
    'display_trade_date',
    'authoritative_snapshot_missing_display_trade_date'
  );
  const candidateTradeDate = requiredIsoDate(
    displayPayload,
    'candidate_trade_date',
    'authoritative_snapshot_missing_candidate_trade_date'
  );
  const [catalogPayload, queuePayload] = await Promise.all([
    getJson(page, '/api/strategies/catalog', 'playwright-real-snapshot-strategy-catalog'),
    getJson(
      page,
      `/api/review-queue?trade_date=${encodeURIComponent(displayTradeDate)}`,
      'playwright-real-snapshot-review-queue'
    )
  ]);
  const catalogItems = arrayValue(
    objectValue(catalogPayload, 'authoritative_snapshot_invalid_catalog_payload').items,
    'authoritative_snapshot_invalid_catalog_items'
  );
  const queueItems = reviewQueueItems(
    objectValue(queuePayload, 'authoritative_snapshot_invalid_queue_payload')
  );

  return {
    displayTradeDate,
    candidateTradeDate,
    strategies: OFFICIAL_STRATEGY_IDS.map((expectedStrategyId) =>
      verifyStrategy(expectedStrategyId, catalogItems, queueItems)
    )
  };
}
