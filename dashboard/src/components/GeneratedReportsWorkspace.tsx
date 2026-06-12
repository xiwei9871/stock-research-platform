import { ReportsWorkspace } from './ReportsWorkspace';

type GeneratedReportsWorkspaceProps = {
  initialQuery?: string;
};

export function GeneratedReportsWorkspace({ initialQuery }: GeneratedReportsWorkspaceProps = {}) {
  return (
    <ReportsWorkspace
      title="Generated Reports"
      description="Local generated artifacts from TopN, risk, factor, backtest, and validation jobs."
      ariaLabel="Generated Reports workspace"
      initialQuery={initialQuery}
    />
  );
}
