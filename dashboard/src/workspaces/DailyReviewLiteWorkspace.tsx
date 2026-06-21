import { DailyReviewLitePage } from '../pages/DailyReviewLitePage';

type DailyReviewLiteWorkspaceProps = {
  tradeDate?: string;
  onTradeDateChange?: (value: string) => void;
};

export function DailyReviewLiteWorkspace({ tradeDate, onTradeDateChange }: DailyReviewLiteWorkspaceProps) {
  return <DailyReviewLitePage tradeDate={tradeDate} onTradeDateChange={onTradeDateChange} />;
}
