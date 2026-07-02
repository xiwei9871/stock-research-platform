import { useMemo, useState } from 'react';
import {
  techBottleneckFinancialStatementRows,
  techBottleneckFinancialStatementSummary,
  techBottleneckManualTemplateStatus,
  techBottleneckPrioritySummary,
  techBottleneckReportLinks,
  techBottleneckRiskRows,
  techBottleneckSections,
  techBottleneckSummary,
  techBottleneckWatchlistRows,
  techBottleneckWarnings
} from './techBottleneckReadonlyData';

const pageReadOnlyControls = {
  writebackAllowed: false,
  usedForSignal: false
};

function BooleanLabel({ value }: { value: boolean }) {
  return <span>{value ? 'true' : 'false'}</span>;
}

export function TechBottleneckWatchlistReviewPage() {
  const [watchlistQuery, setWatchlistQuery] = useState('');
  const [sortMode, setSortMode] = useState<'symbol' | 'priority'>('symbol');
  const financialStatementByAsset = useMemo(
    () => new Map(techBottleneckFinancialStatementRows.map((row) => [row.assetId, row])),
    []
  );
  const filteredWatchlistRows = useMemo(() => {
    const query = watchlistQuery.trim().toLowerCase();
    const rows = query
      ? techBottleneckWatchlistRows.filter((row) =>
          [row.symbol, row.name, row.reviewPriority, row.reviewPriorityReason].some((value) =>
            value.toLowerCase().includes(query)
          )
        )
      : techBottleneckWatchlistRows;
    return [...rows].sort((left, right) => {
      if (sortMode === 'priority') {
        return left.reviewPriority.localeCompare(right.reviewPriority) || left.symbol.localeCompare(right.symbol);
      }
      return left.symbol.localeCompare(right.symbol);
    });
  }, [sortMode, watchlistQuery]);

  return (
    <section aria-label="Tech Bottleneck Watchlist Review">
      <header>
        <p>Tech Bottleneck Watchlist Review</p>
        <h1>Read-only research review</h1>
        <p>
          This page is a display-only shell for the v2 research selection layer. Data serving from research outputs is
          deferred to the dashboard data integration step.
        </p>
      </header>

      <section aria-label="Snapshot Summary">
        <h2>Snapshot Summary</h2>
        <dl>
          <dt>Watchlist count</dt>
          <dd>{techBottleneckSummary.watchlistCount}</dd>
          <dt>V2 candidates</dt>
          <dd>{techBottleneckSummary.v2CandidatesCount}</dd>
          <dt>Review priority rows</dt>
          <dd>{techBottleneckSummary.reviewPriorityRows}</dd>
          <dt>Risk queue rows</dt>
          <dd>{techBottleneckSummary.riskQueueRows}</dd>
          <dt>Report links</dt>
          <dd>{techBottleneckSummary.consolidatedReportLinks}</dd>
          <dt>Writeback allowed</dt>
          <dd>
            <BooleanLabel value={pageReadOnlyControls.writebackAllowed} />
          </dd>
          <dt>Used for automated execution</dt>
          <dd>
            <BooleanLabel value={pageReadOnlyControls.usedForSignal} />
          </dd>
        </dl>
      </section>

      <section aria-label="Global Warnings">
        <h2>Global Warning Banner</h2>
        <ul>
          {techBottleneckWarnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </section>

      <section aria-label="V2 Review Priority Summary">
        <h2>V2 Review Priority Summary</h2>
        <table>
          <thead>
            <tr>
              <th>Priority</th>
              <th>Count</th>
              <th>Review use</th>
            </tr>
          </thead>
          <tbody>
            {techBottleneckPrioritySummary.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.count}</td>
                <td>{row.reviewUse}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-label="Page Sections">
        <h2>Page Sections</h2>
        {techBottleneckSections.map((section) => (
          <article key={section.title}>
            <h3>{section.title}</h3>
            <p>{section.purpose}</p>
            <p>Fields: {section.displayFields.join(', ')}</p>
            <p>Allowed interactions: {section.interactionsAllowed.join(', ')}</p>
            <p>
              Writeback allowed: <BooleanLabel value={section.writebackAllowed} />
            </p>
            <p>
              Used for automated execution: <BooleanLabel value={section.usedForSignal} />
            </p>
          </article>
        ))}
      </section>

      <section aria-label="Watchlist Table">
        <h2>Watchlist Table</h2>
        <p>
          Showing {filteredWatchlistRows.length} sample rows from {techBottleneckSummary.v2CandidatesCount} v2
          candidates. The complete data product remains the research CSV.
        </p>
        <label>
          Search watchlist
          <input
            type="search"
            value={watchlistQuery}
            onChange={(event) => setWatchlistQuery(event.target.value)}
            placeholder="symbol, name, priority"
          />
        </label>
        <button
          type="button"
          aria-label="Sort watchlist rows"
          onClick={() => setSortMode((current) => (current === 'symbol' ? 'priority' : 'symbol'))}
        >
          Sort by {sortMode === 'symbol' ? 'priority' : 'symbol'}
        </button>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Review priority</th>
              <th>Reason</th>
              <th>Quality</th>
              <th>Recovery</th>
              <th>Risk badge</th>
              <th>Valuation</th>
              <th>Baidu validation</th>
              <th>Data gap</th>
              <th>Financial statement support</th>
              <th>Statement quality</th>
              <th>PIT status</th>
              <th>Report period</th>
              <th>Source warning</th>
              <th>Report path</th>
            </tr>
          </thead>
          <tbody>
            {filteredWatchlistRows.map((row) => {
              const financialStatement = financialStatementByAsset.get(row.assetId);
              return (
                <tr key={row.assetId}>
                  <td>{row.symbol}</td>
                  <td>{row.name}</td>
                  <td>{row.reviewPriority}</td>
                  <td>{row.reviewPriorityReason}</td>
                  <td>{row.fundamentalQualityBadge}</td>
                  <td>{row.recoveryBadge}</td>
                  <td>{row.riskReviewBadge}</td>
                  <td>{row.valuationContextBadge}</td>
                  <td>{row.baiduValidationBadge}</td>
                  <td>{row.dataGapBadge}</td>
                  <td>{financialStatement?.support ?? 'not_loaded'}</td>
                  <td>{financialStatement?.quality ?? 'not_loaded'}</td>
                  <td>{financialStatement?.pitStatus ?? 'not_loaded'}</td>
                  <td>{financialStatement?.reportPeriod || 'missing'}</td>
                  <td>{row.sourceQualityWarning}</td>
                  <td>{row.consolidatedReportPath}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section aria-label="Full Financial Statement Review Context">
        <h2>Full Financial Statement Review Context</h2>
        <p>Financial Statement Support: {techBottleneckFinancialStatementSummary.supportedCount} / {techBottleneckFinancialStatementSummary.watchlistCount}</p>
        <p>Missing Financial Statement: {techBottleneckFinancialStatementSummary.missingCount}</p>
        <p>PIT Strong: {techBottleneckFinancialStatementSummary.pitStrongCount}</p>
        <p>PIT Degraded: {techBottleneckFinancialStatementSummary.pitDegradedCount}</p>
        <p>Lookahead Violations: {techBottleneckFinancialStatementSummary.lookaheadViolationRows}</p>
        <p>Financial statement data unavailable before first admission date</p>
        <p>research_only = {String(techBottleneckFinancialStatementSummary.researchOnly)}</p>
        <p>writeback_enabled = {String(techBottleneckFinancialStatementSummary.writebackEnabled)}</p>
        <p>manual_review_writeback_enabled = {String(techBottleneckFinancialStatementSummary.manualReviewWritebackEnabled)}</p>
        <p>used_for_signal = {String(techBottleneckFinancialStatementSummary.usedForSignal)}</p>
        <p>used_for_admission = {String(techBottleneckFinancialStatementSummary.usedForAdmission)}</p>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Support</th>
              <th>Quality</th>
              <th>Report period</th>
              <th>Announce date</th>
              <th>PIT status</th>
              <th>Source quality</th>
              <th>Gross margin</th>
              <th>Asset liability ratio</th>
              <th>Cashflow context</th>
              <th>Balance sheet context</th>
              <th>R&D context</th>
              <th>Data gap note</th>
            </tr>
          </thead>
          <tbody>
            {techBottleneckFinancialStatementRows.map((row) => (
              <tr key={row.assetId}>
                <td>{row.symbol}</td>
                <td>{row.name}</td>
                <td>{row.support}</td>
                <td>{row.quality}</td>
                <td>{row.reportPeriod || 'missing'}</td>
                <td>{row.announceDate || 'missing'}</td>
                <td>{row.pitStatus}</td>
                <td>{row.sourceQuality}</td>
                <td>{row.grossMargin || 'missing'}</td>
                <td>{row.assetLiabilityRatio || 'missing'}</td>
                <td>{row.cashflowQualityContext}</td>
                <td>{row.balanceSheetPressureContext}</td>
                <td>{row.rdIntensityContext}</td>
                <td>{row.dataGapNote}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-label="Risk Review Queue">
        <h2>Risk Review Queue</h2>
        <p>
          Showing {techBottleneckRiskRows.length} sample rows from {techBottleneckSummary.riskQueueRows} risk review
          rows. Risk rows support manual review only. auto_exclude = false.
        </p>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Risk type</th>
              <th>Severity</th>
              <th>Reason</th>
              <th>Review action</th>
              <th>Auto exclude</th>
            </tr>
          </thead>
          <tbody>
            {techBottleneckRiskRows.map((row) => (
              <tr key={`${row.assetId}-${row.riskType}`}>
                <td>{row.symbol}</td>
                <td>{row.name}</td>
                <td>{row.riskType}</td>
                <td>{row.severity}</td>
                <td>{row.riskReason}</td>
                <td>{row.recommendedReviewAction}</td>
                <td>auto_exclude = {String(row.autoExclude)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-label="Manual Review Template Status">
        <h2>Manual Review Template Status</h2>
        <dl>
          <dt>Template rows</dt>
          <dd>{techBottleneckManualTemplateStatus.templateRows}</dd>
          <dt>Manual review conclusion</dt>
          <dd>manual_review_conclusion = not_reviewed</dd>
          <dt>Not reviewed rows</dt>
          <dd>{techBottleneckManualTemplateStatus.notReviewedCount}</dd>
          <dt>History rows</dt>
          <dd>{techBottleneckManualTemplateStatus.historyRows}</dd>
          <dt>Writeback status</dt>
          <dd>writeback disabled</dd>
          <dt>Next step</dt>
          <dd>{techBottleneckManualTemplateStatus.nextStep}</dd>
        </dl>
      </section>

      <section aria-label="Consolidated Report Links">
        <h2>Consolidated Report Links</h2>
        <p>
          Showing {techBottleneckReportLinks.length} sample links from {techBottleneckSummary.consolidatedReportLinks}
          consolidated reports.
        </p>
        <ul>
          {techBottleneckReportLinks.map((report) => (
            <li key={report.assetId}>
              <strong>
                {report.symbol} {report.name}
              </strong>
              <span> {report.path}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Methodology">
        <h2>Methodology Panel</h2>
        <p>Baseline admission remains unchanged.</p>
        <p>Forward return context is displayed only as prior validation context outside this page.</p>
        <p>Manual review labels are not consumed by automated execution logic.</p>
      </section>
    </section>
  );
}
