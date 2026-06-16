import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchFactorLibrary, fetchFactorScorePreview } from '../api/client';
import type { FactorLibraryRow, FactorScorePreview, FactorSelection } from '../api/types';

const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_TOP_N = 30;

function formatValue(value: string | number | null | undefined) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  return value ?? '-';
}

function getDefaultSelection(row: FactorLibraryRow): FactorSelection {
  return {
    factor_name: row.factor_name,
    direction: row.direction === 'lower' ? 'lower' : 'higher',
    weight: row.manual_v1_weight ?? 1
  };
}

export function FactorLabWorkspace() {
  const [libraryRows, setLibraryRows] = useState<FactorLibraryRow[]>([]);
  const [selectedByName, setSelectedByName] = useState<Record<string, FactorSelection>>({});
  const [preview, setPreview] = useState<FactorScorePreview | null>(null);
  const [isLibraryLoading, setIsLibraryLoading] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const previewRequestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    setIsLibraryLoading(true);
    setLibraryError(null);

    fetchFactorLibrary()
      .then((rows) => {
        if (!mountedRef.current) {
          return;
        }
        setLibraryRows(rows);
        setIsLibraryLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) {
          return;
        }
        setLibraryError(err instanceof Error ? err.message : String(err));
        setIsLibraryLoading(false);
      });

    return () => {
      mountedRef.current = false;
    };
  }, []);

  const selectedFactors = useMemo(
    () => libraryRows.map((row) => selectedByName[row.factor_name]).filter(Boolean),
    [libraryRows, selectedByName]
  );
  const hasInvalidSelection = selectedFactors.some(
    (selection) => !Number.isFinite(selection.weight) || selection.weight <= 0
  );
  const canPreview = selectedFactors.length > 0 && !hasInvalidSelection && !isPreviewLoading;

  const invalidatePreview = () => {
    previewRequestIdRef.current += 1;
    setPreview(null);
    setPreviewError(null);
    setIsPreviewLoading(false);
  };

  const toggleSelection = (row: FactorLibraryRow) => {
    setSelectedByName((current) => {
      if (current[row.factor_name]) {
        const next = { ...current };
        delete next[row.factor_name];
        return next;
      }
      return { ...current, [row.factor_name]: getDefaultSelection(row) };
    });
    invalidatePreview();
  };

  const updateSelection = (factorName: string, updates: Partial<FactorSelection>) => {
    setSelectedByName((current) => {
      const existing = current[factorName];
      if (!existing) {
        return current;
      }
      return { ...current, [factorName]: { ...existing, ...updates } };
    });
    invalidatePreview();
  };

  const previewScores = () => {
    if (selectedFactors.length === 0 || hasInvalidSelection) {
      return;
    }

    const requestId = previewRequestIdRef.current + 1;
    previewRequestIdRef.current = requestId;
    setIsPreviewLoading(true);
    setPreviewError(null);

    fetchFactorScorePreview(DEFAULT_TRADE_DATE, selectedFactors, DEFAULT_TOP_N)
      .then((nextPreview) => {
        if (!mountedRef.current || previewRequestIdRef.current !== requestId) {
          return;
        }
        setPreview(nextPreview);
        setIsPreviewLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || previewRequestIdRef.current !== requestId) {
          return;
        }
        setPreviewError(err instanceof Error ? err.message : String(err));
        setIsPreviewLoading(false);
      });
  };

  return (
    <section className="factor-lab-workspace" aria-label="Factor Lab workspace">
      <header className="workspace-header">
        <h1>Factor Lab</h1>
      </header>

      <section className="factor-lab-toolbar" aria-label="Preview controls">
        <div>
          <span>Trade Date</span>
          <strong>{DEFAULT_TRADE_DATE}</strong>
        </div>
        <div>
          <span>Top N</span>
          <strong>{DEFAULT_TOP_N}</strong>
        </div>
        <button type="button" disabled={!canPreview} onClick={previewScores}>
          Preview Scores
        </button>
        {selectedFactors.length === 0 ? <span className="muted">请先选择至少 1 个因子，再预览评分。</span> : null}
        {selectedFactors.length > 0 && hasInvalidSelection ? (
          <span className="muted">已选因子的权重必须大于 0。</span>
        ) : null}
        {isPreviewLoading ? <span className="muted">Loading score preview...</span> : null}
      </section>

      {libraryError ? <p className="error-text">{libraryError}</p> : null}
      {previewError ? <p className="error-text">{previewError}</p> : null}

      <section className="factor-lab-grid">
        <article className="workspace-band factor-library-panel">
          <div className="section-heading">
            <h2>Factor Library</h2>
            {isLibraryLoading ? <span className="muted">Loading factor library...</span> : null}
          </div>

          {libraryRows.length > 0 ? (
            <div className="table-scroll">
              <table className="data-table factor-library-table">
                <thead>
                  <tr>
                    <th>Select</th>
                    <th>Factor</th>
                    <th>Group</th>
                    <th>Status</th>
                    <th>Direction</th>
                    <th>Manual V1</th>
                    <th>Latest</th>
                    <th>Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {libraryRows.map((row) => {
                    const selection = selectedByName[row.factor_name];
                    return (
                      <tr key={row.factor_name}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`select ${row.factor_name}`}
                            checked={Boolean(selection)}
                            onChange={() => toggleSelection(row)}
                          />
                        </td>
                        <td title={row.description || undefined}>
                          <strong>{row.factor_name}</strong>
                        </td>
                        <td>{row.factor_group}</td>
                        <td>{formatValue(row.status)}</td>
                        <td>
                          {selection ? (
                            <select
                              aria-label={`${row.factor_name} direction`}
                              value={selection.direction}
                              onChange={(event) =>
                                updateSelection(row.factor_name, {
                                  direction: event.target.value === 'lower' ? 'lower' : 'higher'
                                })
                              }
                            >
                              <option value="higher">higher</option>
                              <option value="lower">lower</option>
                            </select>
                          ) : (
                            formatValue(row.direction)
                          )}
                        </td>
                        <td>
                          <span>{row.used_in_manual_v1 ? 'Manual V1' : 'Not used'}</span>
                          <small>Weight {formatValue(row.manual_v1_weight)}</small>
                        </td>
                        <td>{formatValue(row.latest_available_date)}</td>
                        <td>{formatValue(row.coverage_count)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : !isLibraryLoading && !libraryError ? (
            <p className="muted">No factors available.</p>
          ) : null}
        </article>

        <article className="workspace-band selected-factor-panel">
          <div className="section-heading">
            <h2>Selected Factors</h2>
            <span className="muted">{selectedFactors.length} selected</span>
          </div>
          {selectedFactors.length > 0 ? (
            <div className="selected-factor-list">
              {selectedFactors.map((selection) => (
                <label key={selection.factor_name}>
                  <span>{selection.factor_name}</span>
                  <input
                    aria-label={`${selection.factor_name} weight`}
                    type="number"
                    min="0.0001"
                    step="0.1"
                    value={selection.weight}
                    onChange={(event) =>
                      updateSelection(selection.factor_name, { weight: Number(event.target.value) })
                    }
                  />
                </label>
              ))}
            </div>
          ) : (
            <p className="muted">从左侧因子库勾选因子后，可预览该组合的 TopN 评分排名。</p>
          )}
        </article>
      </section>

      <section className="workspace-band">
        <div className="section-heading">
          <h2>Score Preview</h2>
          {preview ? <span className="muted">{preview.items.length} rows</span> : null}
        </div>
        {preview ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Asset ID</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((row) => (
                  <tr key={`${row.rank}-${row.asset_id}`}>
                    <td>{row.rank}</td>
                    <td>{row.asset_id}</td>
                    <td>{formatValue(row.score_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No preview loaded.</p>
        )}
      </section>
    </section>
  );
}
