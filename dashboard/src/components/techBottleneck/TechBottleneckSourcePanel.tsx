import type { TechBottleneckReviewSource } from '../../types/techBottleneckReview';

export function TechBottleneckSourcePanel({ sources }: { sources: TechBottleneckReviewSource[] }) {
  if (!sources.length) {
    return <p className="muted">该股票暂无来源记录。</p>;
  }

  return (
    <div className="table-scroll">
      <table aria-label="科技卡脖子来源表">
        <thead>
          <tr>
            <th>来源类型</th>
            <th>来源标题</th>
            <th>来源文件</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source, index) => (
            <tr key={`${source.stock_code}:${source.source_file}:${index}`}>
              <td>{source.source_type}</td>
              <td>{source.source_title}</td>
              <td>{source.source_file}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
