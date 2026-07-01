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
              <a
                key={report.path}
                className={`report-card${isSelected ? ' report-card--selected' : ''}`}
                href={report.path}
              >
                <span>{report.report_type}</span>
                <strong>{report.title}</strong>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          <strong>当前日期没有生成报告。</strong>
          <p className="muted">可能是报告生成任务尚未运行，或报告目录没有命中该日期。</p>
          <p className="muted">可以切换交易日期查看历史报告，或重新运行生成报告任务。</p>
        </div>
      )}
    </section>
  );
}
