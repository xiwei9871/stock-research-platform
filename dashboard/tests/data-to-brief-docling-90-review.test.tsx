import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

const payload = vi.hoisted(() => ({
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
  per_stock: [
    {
      stock_code: '002371',
      stock_name: '北方华创',
      asset_id: '002371.SZ',
      report_status: 'page_level_docling_enriched',
      parser_artifact_status: 'reused_page_level',
      citation_status: 'page_level_ready',
      citation_claim_count: 12,
      page_level_citation_count: 12,
      source_level_citation_count: 0,
      table_row_count: 120,
      table_provenance_status: 'full',
      report_md_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_md/002371_北方华创.md',
      report_html_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_html/002371_北方华创.html',
      report_pdf_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_pdf/002371_北方华创.pdf',
      evidence_matrix_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/evidence_matrix.csv',
      claim_citation_map_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/claim_citation_map.csv',
      sources_jsonl_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/002371/sources.jsonl',
      warnings: [],
      allowed_for_signal: false,
      allowed_for_admission: false
    },
    {
      stock_code: '688012',
      stock_name: '中微公司',
      asset_id: '688012.SH',
      report_status: 'page_level_docling_enriched',
      parser_artifact_status: 'cold_parse_page_level',
      citation_status: 'page_level_ready',
      citation_claim_count: 12,
      page_level_citation_count: 12,
      source_level_citation_count: 0,
      table_row_count: 110,
      table_provenance_status: 'full',
      report_md_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_md/688012_中微公司.md',
      report_html_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_html/688012_中微公司.html',
      report_pdf_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/reports_pdf/688012_中微公司.pdf',
      evidence_matrix_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/688012/evidence_matrix.csv',
      claim_citation_map_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/688012/claim_citation_map.csv',
      sources_jsonl_path: 'outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/evidence/688012/sources.jsonl',
      warnings: ['table title normalized'],
      allowed_for_signal: false,
      allowed_for_admission: false
    }
  ]
}));

vi.mock('../src/api/client', () => ({
  fetchDataToBriefDocling90Review: vi.fn().mockResolvedValue(payload),
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-06' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-06' })
}));

vi.mock('../src/components/FactorLabWorkspace', () => ({ FactorLabWorkspace: () => <div>Factor Lab</div> }));
vi.mock('../src/components/DailyReviewLiteWorkspace', () => ({
  DailyReviewLiteWorkspace: () => <div>Daily Review Lite</div>
}));
vi.mock('../src/components/GeneratedReportsWorkspace', () => ({ GeneratedReportsWorkspace: () => <div>Generated Reports</div> }));
vi.mock('../src/components/GlobalSearchBox', () => ({ GlobalSearchBox: () => <div>Search</div> }));
vi.mock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>Home</div> }));
vi.mock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>Market</div> }));
vi.mock('../src/components/NewsWorkspace', () => ({ NewsWorkspace: () => <div>News</div> }));
vi.mock('../src/components/ResearchReportsWorkspace', () => ({ ResearchReportsWorkspace: () => <div>Reports</div> }));
vi.mock('../src/components/ReviewQueueWorkspace', () => ({ ReviewQueueWorkspace: () => <div>Review Queue</div> }));
vi.mock('../src/components/StockWorkspace', () => ({ StockWorkspace: () => <div>Stock Workspace</div> }));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));

describe('Data-to-Brief Docling 90-stock review route', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/research/data-to-brief/docling-90');
  });

  afterEach(() => cleanup());

  it('renders a read-only 90-stock review payload without signal or admission controls', async () => {
    render(<AppShell />);

    expect(await screen.findByText('Read-only page-level evidence report audit')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Data-to-Brief Docling 90-Stock Review' })).toBeVisible();
    expect(screen.getByText('Read-only page-level evidence report audit')).toBeVisible();
    expect(screen.getByText('Stocks 90')).toBeVisible();
    expect(screen.getByText('Reports 90')).toBeVisible();
    expect(screen.getByText('Citation claims 1061')).toBeVisible();
    expect(screen.getByText('Page-level 1061')).toBeVisible();
    expect(screen.getByText('Source-level 0')).toBeVisible();
    expect(screen.getByText('Signal disabled')).toBeVisible();
    expect(screen.getByText('Admission disabled')).toBeVisible();

    const table = within(screen.getByRole('table', { name: 'Docling 90-stock review table' }));
    expect(table.getByText('北方华创')).toBeVisible();
    expect(table.getByText('中微公司')).toBeVisible();
    expect(screen.queryByRole('button', { name: /生成信号|加入准入|入选策略/ })).not.toBeInTheDocument();
  });

  it('filters warnings and expands stock details', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: 'Data-to-Brief Docling 90-Stock Review' });

    fireEvent.change(screen.getByLabelText('Filter stocks'), { target: { value: 'warnings' } });
    expect(screen.getByRole('table', { name: 'Docling 90-stock review table' })).toHaveTextContent('中微公司');
    expect(screen.getByRole('table', { name: 'Docling 90-stock review table' })).not.toHaveTextContent('北方华创');

    fireEvent.click(screen.getByRole('button', { name: 'Expand 688012' }));
    expect(screen.getByRole('region', { name: '688012 citation detail' })).toHaveTextContent('page locator coverage');
    expect(screen.getByRole('region', { name: '688012 citation detail' })).toHaveTextContent('claim_citation_map.csv');
  });
});
