import { expect, test, type Page } from '@playwright/test';

async function mockApi(page: Page) {
  const baseRow = {
    asset_id: '002371.SZ',
    report_status: 'page_level_docling_enriched',
    parser_artifact_status: 'reused_page_level',
    citation_status: 'page_level_ready',
    citation_claim_count: 12,
    page_level_citation_count: 12,
    source_level_citation_count: 0,
    table_row_count: 120,
    table_provenance_status: 'full',
    report_md_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_md/report.md',
    report_html_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_html/report.html',
    report_pdf_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_pdf/report.pdf',
    evidence_matrix_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/evidence_matrix.csv',
    claim_citation_map_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/claim_citation_map.csv',
    sources_jsonl_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/sources.jsonl',
    warnings: [],
    allowed_for_signal: false,
    allowed_for_admission: false
  };
  const perStock = [
    { ...baseRow, stock_code: '002371', stock_name: '北方华创' },
    { ...baseRow, stock_code: '688012', stock_name: '中微公司', parser_artifact_status: 'cold_parse_page_level' },
    ...Array.from({ length: 88 }, (_, index) => ({
      ...baseRow,
      stock_code: String(index + 1).padStart(6, '0'),
      stock_name: `样本${index + 1}`
    }))
  ];
  const payload = {
    batch_id: 'data_to_brief_docling_90_stock_full_cold_parse_batch_v1',
    source_output_dir: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1',
    stock_count: 90,
    report_success_count: 90,
    evidence_required_count: 0,
    citation_claim_count: 1061,
    page_level_citation_count: 1061,
    source_level_citation_count: 0,
    table_row_count: 10083,
    table_provenance_full_count: 10083,
    parser_artifact_ready_count: 90,
    cold_parse_runtime_seconds: 7538.448,
    cached_postprocess_runtime_seconds: 3.976,
    allowed_for_signal: false,
    allowed_for_admission: false,
    production_update: false,
    acceptance_decision: 'ready_for_read_only_dashboard_review',
    per_stock: perStock
  };
  await page.route('/api/research/data-to-brief/docling-90', async (route) => {
    await route.fulfill({ json: payload });
  });
  await page.route('/api/platform/readiness**', async (route) => {
    await route.fulfill({ json: { display_trade_date: '2026-07-06', latest_market_date: '2026-07-06' } });
  });
  await page.route('/api/platform/summary**', async (route) => {
    await route.fulfill({ json: { latest_market_date: '2026-07-06' } });
  });
}

test('Data-to-Brief Docling 90-stock route renders read-only audit surface', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(error.message));

  await mockApi(page);
  await page.goto('/research/data-to-brief/docling-90');

  await expect(page.getByRole('heading', { name: 'Data-to-Brief Docling 90-Stock Review' })).toBeVisible();
  await expect(page.getByText('Stocks 90')).toBeVisible();
  await expect(page.getByText('Citation claims 1061')).toBeVisible();
  await expect(page.getByText('Page-level 1061')).toBeVisible();
  await expect(page.getByText('Source-level 0')).toBeVisible();
  await expect(page.getByRole('table', { name: 'Docling 90-stock review table' })).toBeVisible();

  await page.getByLabel('Filter stocks').selectOption('citation_ready');
  await expect(page.getByRole('table', { name: 'Docling 90-stock review table' })).toContainText('page_level_docling_enriched');
  await page.getByLabel('Filter stocks').selectOption('table_full');
  await expect(page.getByRole('table', { name: 'Docling 90-stock review table' })).toContainText('full');
  await page.getByLabel('Filter stocks').selectOption('parser_ready');
  await expect(page.getByRole('table', { name: 'Docling 90-stock review table' })).toContainText('page_level');

  const firstExpand = page.getByRole('button', { name: /Expand \d{6}/ }).first();
  const expandName = await firstExpand.textContent();
  await firstExpand.click();
  await expect(page.getByText('page locator coverage')).toBeVisible();
  await expect(page.getByText('claim_citation_map.csv')).toBeVisible();

  await expect(page.getByRole('button', { name: /生成信号|加入准入|入选策略|Apply to production|Enable admission/ })).toHaveCount(0);
  await expect(page.getByText(/buy recommendation|sell recommendation|target price/i)).toHaveCount(0);

  await page.screenshot({
    path: '/Users/xiwei/stock_research/outputs/research/data_to_brief_docling_90_dashboard_e2e_smoke_and_release_checkpoint_v1/docling_90_dashboard_smoke.png',
    fullPage: true
  });
  expect(expandName).toContain('Expand');
  expect(consoleErrors).toEqual([]);
});
