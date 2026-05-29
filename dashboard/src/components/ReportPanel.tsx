import type { ReportLink } from '../api/types';

type ReportPanelProps = {
  reports: ReportLink[];
};

export function ReportPanel({ reports }: ReportPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Reports</h2>
      <div className="report-list">
        {reports.map((report) => (
          <a key={report.path} href={report.path}>
            <span>{report.report_type}</span>
            <strong>{report.title}</strong>
          </a>
        ))}
      </div>
    </section>
  );
}
