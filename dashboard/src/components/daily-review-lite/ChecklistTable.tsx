import type { DailyReviewLiteChecklistItem } from '../../api/types';

type ChecklistTableProps = {
  items: DailyReviewLiteChecklistItem[];
};

export function ChecklistTable({ items }: ChecklistTableProps) {
  if (items.length === 0) {
    return <p>No checklist items.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th scope="col">Asset</th>
          <th scope="col">Priority</th>
          <th scope="col">Reasons</th>
          <th scope="col">Actions</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={`${item.asset_id ?? item.ts_code ?? item.stock_name ?? 'checklist'}-${index}`}>
            <td>
              <p>{item.stock_name ?? item.ts_code ?? item.asset_id ?? 'Unknown asset'}</p>
              {formatAssetSecondaryIdentity(item) ? <p>{formatAssetSecondaryIdentity(item)}</p> : null}
            </td>
            <td>{item.review_priority ?? 'unknown'}</td>
            <td>
              {item.reasons.length > 0 ? (
                <ul>
                  {item.reasons.map((reason, reasonIndex) => (
                    <li key={`${item.asset_id ?? index}-reason-${reasonIndex}`}>
                      {reason.strategy_id ? <p>Strategy: {reason.strategy_id}</p> : null}
                      {reason.summary ? <p>Summary: {reason.summary}</p> : null}
                      {reason.detail ? <p>{reason.detail}</p> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No reasons provided.</p>
              )}
            </td>
            <td>
              {item.actions.length > 0 ? (
                <ul>
                  {item.actions.map((action, actionIndex) => (
                    <li key={`${item.asset_id ?? index}-action-${actionIndex}`}>{action}</li>
                  ))}
                </ul>
              ) : (
                <p>No actions provided.</p>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatAssetSecondaryIdentity(item: DailyReviewLiteChecklistItem) {
  const secondary = [item.ts_code, item.asset_id].filter(
    (value, index, values) => value && values.indexOf(value) === index
  );
  return secondary.length > 0 ? secondary.join(' / ') : null;
}
