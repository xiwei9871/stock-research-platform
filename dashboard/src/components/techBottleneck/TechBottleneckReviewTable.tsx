import type { TechBottleneckReviewStock } from '../../types/techBottleneckReview';
import { readableTechBottleneckOptionLabel } from './TechBottleneckFilterBar';

type Props = {
  rows: TechBottleneckReviewStock[];
  total: number;
  onOpenEvidence: (stockCode: string) => void;
  onOpenStock: (stock: TechBottleneckReviewStock) => void;
};

function conceptTags(row: TechBottleneckReviewStock) {
  if (Array.isArray(row.concept_tags)) return row.concept_tags;
  return String(row.concept_tags || '')
    .split(/[;,，、|/]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function formatScore(score: number | null | undefined) {
  return score === null || score === undefined || Number.isNaN(score) ? '-' : Number(score).toFixed(0);
}

const TABLE_COLUMNS = [
  { key: 'stock_code', label: '股票代码', width: 88 },
  { key: 'stock_name', label: '股票名称', width: 96 },
  { key: 'industry', label: '行业', width: 150 },
  { key: 'concept_tags', label: '概念板块', width: 260 },
  { key: 'evidence_strength', label: '证据强度', width: 86 },
  { key: 'bottleneck_relevance', label: '瓶颈相关性', width: 104 },
  { key: 'review_status', label: '复盘状态', width: 88 },
  { key: 'bottleneck_score', label: '瓶颈分', width: 84 },
  { key: 'evidence_score', label: '证据分', width: 84 },
  { key: 'evidence_count', label: '证据数', width: 72 },
  { key: 'page_citation_count', label: '页级引用', width: 72 },
  { key: 'source_pdf_count', label: '来源数', width: 72 },
  { key: 'evidence_detail', label: '证据详情', width: 140 }
] as const;

export function TechBottleneckReviewTable({ rows, total, onOpenEvidence, onOpenStock }: Props) {
  return (
    <section className="workspace-band" aria-label="科技卡脖子复盘股票列表">
      <p className="tech-bottleneck-table-summary">
        当前显示 {rows.length} / {total} 条 research-only 记录；复盘结论仅写入独立人工 overlay。
      </p>
      <div className="tech-bottleneck-table-scroll">
        <table className="tech-bottleneck-candidate-table" aria-label="科技卡脖子复盘股票表">
          <colgroup>
            {TABLE_COLUMNS.map((column) => (
              <col key={column.key} style={{ width: `${column.width}px` }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {TABLE_COLUMNS.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.stock_code}
                className="tech-bottleneck-clickable-row"
                tabIndex={0}
                onClick={() => onOpenStock(row)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    onOpenStock(row);
                  }
                }}
              >
                <td>{row.stock_code}</td>
                <td>{row.stock_name}</td>
                <td>{row.industry || '未映射'}</td>
                <td>{conceptTags(row).map(readableTechBottleneckOptionLabel).join(' / ') || '未映射'}</td>
                <td>{readableTechBottleneckOptionLabel(row.evidence_strength || '未分层')}</td>
                <td>{readableTechBottleneckOptionLabel(row.bottleneck_relevance || '待复核')}</td>
                <td>{readableTechBottleneckOptionLabel(row.reviewer_decision || row.review_status || row.frontend_review_status || 'pending')}</td>
                <td>{formatScore(row.bottleneckConfidenceScore)}</td>
                <td>{formatScore(row.evidenceQualityScore)}</td>
                <td>{row.evidence_count}</td>
                <td>{row.page_citation_count}</td>
                <td>{row.source_pdf_count}</td>
                <td>
                  <button
                    type="button"
                    className="secondary"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpenEvidence(row.stock_code);
                    }}
                  >
                    查看证据 {row.stock_code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
