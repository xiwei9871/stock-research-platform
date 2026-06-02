import type { ReportLink } from '../api/types';

type ReportPanelProps = {
  reports: ReportLink[];
  isLoading?: boolean;
};

export function ReportPanel({ reports, isLoading = false }: ReportPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Reports</h2>
      {isLoading ? (
        <p className="muted">Loading reports...</p>
      ) : reports.length > 0 ? (
        <div className="report-list">
          {reports.map((report) => (
            <a key={report.path} href={report.path}>
              <span>{report.report_type}</span>
              <strong>{report.title}</strong>
            </a>
          ))}
        </div>
      ) : (
        <p className="muted">No reports for selected date.</p>
      )}
    </section>
  );
}
