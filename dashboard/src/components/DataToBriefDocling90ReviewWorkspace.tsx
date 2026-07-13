import { Fragment, useEffect, useMemo, useState } from 'react';
import { fetchDataToBriefDocling90Review } from '../api/client';
import type { DataToBriefDocling90ReviewPayload, DataToBriefDocling90StockRow } from '../api/types';

type FilterMode = 'all' | 'warnings' | 'parser_ready' | 'citation_ready' | 'table_full';

function hasWarnings(row: DataToBriefDocling90StockRow) {
  return (row.warnings ?? []).filter(Boolean).length > 0;
}

function filterRows(rows: DataToBriefDocling90StockRow[], filter: FilterMode) {
  if (filter === 'warnings') return rows.filter(hasWarnings);
  if (filter === 'parser_ready') return rows.filter((row) => row.parser_artifact_status.includes('page_level'));
  if (filter === 'citation_ready') return rows.filter((row) => row.citation_status === 'page_level_ready');
  if (filter === 'table_full') return rows.filter((row) => row.table_provenance_status === 'full');
  return rows;
}

function statusText(payload: DataToBriefDocling90ReviewPayload) {
  return payload.acceptance_decision === 'ready_for_read_only_dashboard_review' ? 'Ready for read-only dashboard review' : payload.acceptance_decision;
}

export function DataToBriefDocling90ReviewWorkspace() {
  const [payload, setPayload] = useState<DataToBriefDocling90ReviewPayload | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [expandedStockCode, setExpandedStockCode] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchDataToBriefDocling90Review()
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(() => filterRows(payload?.per_stock ?? [], filter), [filter, payload]);

  if (error) {
    return (
      <section className="workspace-band" role="alert">
        <h1>Data-to-Brief Docling 90-Stock Review</h1>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!payload) {
    return (
      <section className="workspace-band">
        <h1>Data-to-Brief Docling 90-Stock Review</h1>
        <p className="muted">Loading read-only Docling review payload...</p>
      </section>
    );
  }

  return (
    <section className="docling-review workspace-page" aria-label="Data-to-Brief Docling 90-stock review">
      <header className="workspace-header">
        <div>
          <h1>Data-to-Brief Docling 90-Stock Review</h1>
          <p className="muted">Read-only page-level evidence report audit</p>
        </div>
        <span className="status-pill">{statusText(payload)}</span>
      </header>

      <section className="stock-summary-strip compact" aria-label="Docling 90-stock review metrics">
        <span className="metric-chip">Stocks {payload.stock_count}</span>
        <span className="metric-chip">Reports {payload.report_success_count}</span>
        <span className="metric-chip">Citation claims {payload.citation_claim_count}</span>
        <span className="metric-chip">Page-level {payload.page_level_citation_count}</span>
        <span className="metric-chip">Source-level {payload.source_level_citation_count}</span>
        <span className="metric-chip">Tables {payload.table_row_count}</span>
        <span className="metric-chip">Parser ready {payload.parser_artifact_ready_count}</span>
        <span className="metric-chip">Signal disabled</span>
        <span className="metric-chip">Admission disabled</span>
      </section>

      <section className="workspace-band docling-review-controls" aria-label="Docling review filters">
        <label>
          Filter stocks
          <select value={filter} onChange={(event) => setFilter(event.target.value as FilterMode)}>
            <option value="all">all stocks</option>
            <option value="warnings">stocks with warnings</option>
            <option value="parser_ready">parser artifact status ready</option>
            <option value="citation_ready">citation status ready</option>
            <option value="table_full">table provenance full</option>
          </select>
        </label>
        <span className="muted">Showing {rows.length} rows · research-only · no signal/admission controls</span>
      </section>

      <section className="workspace-band" aria-label="Docling stock list">
        <div className="table-scroll">
          <table aria-label="Docling 90-stock review table">
            <thead>
              <tr>
                <th>stock</th>
                <th>report_status</th>
                <th>parser_artifact_status</th>
                <th>citations</th>
                <th>page-level</th>
                <th>source-level</th>
                <th>tables</th>
                <th>table provenance</th>
                <th>links</th>
                <th>detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.stock_code}>
                  <tr>
                    <td>
                      <strong>{row.stock_code}</strong> {row.stock_name}
                    </td>
                    <td>{row.report_status}</td>
                    <td>{row.parser_artifact_status}</td>
                    <td>{row.citation_claim_count}</td>
                    <td>{row.page_level_citation_count}</td>
                    <td>{row.source_level_citation_count}</td>
                    <td>{row.table_row_count}</td>
                    <td>{row.table_provenance_status}</td>
                    <td>
                      <div className="inline-link-list">
                        <a href={row.report_html_path}>HTML</a>
                        <a href={row.report_pdf_path}>PDF</a>
                        <a href={row.evidence_matrix_path}>Evidence</a>
                      </div>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setExpandedStockCode((current) => (current === row.stock_code ? '' : row.stock_code))}
                      >
                        {expandedStockCode === row.stock_code ? 'Collapse' : 'Expand'} {row.stock_code}
                      </button>
                    </td>
                  </tr>
                  {expandedStockCode === row.stock_code ? (
                    <tr>
                      <td colSpan={10}>
                        <section className="docling-row-detail" role="region" aria-label={`${row.stock_code} citation detail`}>
                          <p>
                            page locator coverage: {row.page_level_citation_count}/{row.citation_claim_count}; source-level:{' '}
                            {row.source_level_citation_count}
                          </p>
                          <p>report: {row.report_md_path}</p>
                          <p>evidence matrix: {row.evidence_matrix_path}</p>
                          <p>claim map: {row.claim_citation_map_path}</p>
                          <p>references: {row.sources_jsonl_path}</p>
                          {hasWarnings(row) ? <p>warnings: {row.warnings.join('; ')}</p> : <p>warnings: none</p>}
                        </section>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
