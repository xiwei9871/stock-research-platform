import type { ReportLink } from '../api/types';

type ReportPanelProps = {
  reports: ReportLink[];
  isLoading?: boolean;
  selectedPath?: string;
};

export function ReportPanel({ reports, isLoading = false, selectedPath }: ReportPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Reports</h2>
      {isLoading ? (
        <p className="muted">Loading reports...</p>
      ) : reports.length > 0 ? (
        <div className="report-list">
          {reports.map((report) => {
            const isSelected = selectedPath ? report.path === selectedPath : false;

            return (
              <article
                key={report.path}
                className={`report-card${isSelected ? ' report-card--selected' : ''}`}
                aria-label={isSelected ? 'Selected generated report' : undefined}
                aria-current={isSelected ? 'true' : undefined}
              >
                <a href={report.path}>
                  <span>{report.report_type}</span>
                  <strong>{report.title}</strong>
                </a>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="muted">No reports for selected date.</p>
      )}
    </section>
  );
}
