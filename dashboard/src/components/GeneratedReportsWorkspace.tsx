import { ReportsWorkspace } from './ReportsWorkspace';

type GeneratedReportsWorkspaceProps = {
  initialQuery?: string;
  initialTradeDate?: string;
  initialPath?: string;
};

export function GeneratedReportsWorkspace({
  initialQuery,
  initialTradeDate,
  initialPath
}: GeneratedReportsWorkspaceProps = {}) {
  return (
    <ReportsWorkspace
      title="Generated Reports"
      description="Local generated artifacts from TopN, risk, factor, backtest, and validation jobs."
      ariaLabel="Generated Reports workspace"
      initialQuery={initialQuery}
      initialTradeDate={initialTradeDate}
      initialPath={initialPath}
    />
  );
}
