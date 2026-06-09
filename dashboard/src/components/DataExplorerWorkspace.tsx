import { FormEvent, useEffect, useRef, useState } from 'react';
import { fetchAssetProfile } from '../api/client';
import type { AssetProfile } from '../api/types';
import { AssetChart } from '../charts/AssetChart';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_ADJUST_TYPE = 'qfq';
const SCORE_VERSION = 'manual_v1';

function offsetDate(dateValue: string, dayOffset: number) {
  const date = new Date(`${dateValue}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayOffset);
  return date.toISOString().slice(0, 10);
}

function formatValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (value == null) {
    return '-';
  }
  return JSON.stringify(value);
}

function formatScore(profile: AssetProfile | null) {
  const score = profile?.score?.score_total;
  return typeof score === 'number' ? score.toFixed(1) : '-';
}

type FactorDisplayRow = {
  group: string;
  name: string;
  value: unknown;
};

function getFactorRows(profile: AssetProfile | null): FactorDisplayRow[] {
  const rows = profile?.factor_values ?? [];
  if (rows.some((row) => 'factor_name' in row)) {
    return rows.map((row) => ({
      group: formatValue(row.factor_group),
      name: formatValue(row.factor_name),
      value: row.factor_value
    }));
  }

  const latestFactors = rows[0] ?? {};
  return Object.entries(latestFactors)
    .filter(([key]) => key !== 'asset_id' && key !== 'trade_date')
    .map(([key, value]) => ({ group: '-', name: key, value }));
}

export function DataExplorerWorkspace() {
  const [assetId, setAssetId] = useState(DEFAULT_ASSET_ID);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [adjustType, setAdjustType] = useState(DEFAULT_ADJUST_TYPE);
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const loadProfile = (nextAssetId = assetId, nextTradeDate = tradeDate, nextAdjustType = adjustType) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const normalizedAssetId = nextAssetId.trim();
    const startDate = offsetDate(nextTradeDate, -180);

    setIsLoading(true);
    setError(null);

    fetchAssetProfile(normalizedAssetId, nextTradeDate, startDate, nextTradeDate, SCORE_VERSION, nextAdjustType)
      .then((nextProfile) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setProfile(nextProfile);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      });
  };

  useEffect(() => {
    loadProfile(DEFAULT_ASSET_ID, DEFAULT_TRADE_DATE, DEFAULT_ADJUST_TYPE);
  }, []);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    loadProfile();
  };

  const identityName = profile?.asset?.name ?? profile?.asset_id ?? assetId;
  const canonicalAssetId = profile?.canonical_asset_id ?? '-';
  const coverageRows = Object.entries(profile?.coverage ?? {});
  const factorRows = getFactorRows(profile);

  return (
    <section className="data-explorer-workspace" aria-label="Data Explorer workspace">
      <header className="workspace-header">
        <h1>Data Explorer</h1>
      </header>

      <form className="data-explorer-toolbar" onSubmit={handleSubmit}>
        <label>
          Asset
          <input aria-label="asset id" value={assetId} onChange={(event) => setAssetId(event.target.value)} />
        </label>
        <label>
          Trade Date
          <input
            aria-label="trade date"
            type="date"
            value={tradeDate}
            onChange={(event) => setTradeDate(event.target.value)}
          />
        </label>
        <label>
          Adjust
          <select aria-label="adjust type" value={adjustType} onChange={(event) => setAdjustType(event.target.value)}>
            <option value="qfq">qfq</option>
            <option value="hfq">hfq</option>
            <option value="none">none</option>
          </select>
        </label>
        <button type="submit">Load Asset</button>
        {isLoading ? <span className="muted">Loading asset profile...</span> : null}
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      {profile ? (
        <>
          <section className="data-explorer-summary" aria-label="Asset identity">
            <div>
              <span>Name</span>
              <strong>{identityName}</strong>
            </div>
            <div>
              <span>Canonical Asset ID</span>
              <strong>{canonicalAssetId}</strong>
            </div>
            <div>
              <span>Score</span>
              <strong>Score {formatScore(profile)}</strong>
            </div>
          </section>

          <section className="data-explorer-grid">
            <article className="workspace-band">
              <div className="section-heading">
                <h2>Data Coverage</h2>
              </div>
              <dl className="data-kv-list">
                {coverageRows.map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{formatValue(value)}</dd>
                  </div>
                ))}
                {coverageRows.length === 0 ? <p className="muted">No coverage metadata available.</p> : null}
              </dl>
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Factors</h2>
              </div>
              {factorRows.length > 0 ? (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Group</th>
                      <th>Factor</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factorRows.map((row) => (
                      <tr key={`${row.group}-${row.name}`}>
                        <td>{row.group}</td>
                        <td>{row.name}</td>
                        <td>{formatValue(row.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">No factor values available.</p>
              )}
            </article>
          </section>

          {profile.bars.length > 0 ? (
            <section className="workspace-band data-chart-panel" aria-label="Daily bars">
              <div className="section-heading">
                <h2>Daily Bars</h2>
                <span className="muted">{profile.bars.length} bars</span>
              </div>
              <AssetChart bars={profile.bars} />
            </section>
          ) : (
            <section className="workspace-band" aria-label="Daily bars">
              <p className="muted">No daily bars available.</p>
            </section>
          )}
        </>
      ) : null}
    </section>
  );
}
