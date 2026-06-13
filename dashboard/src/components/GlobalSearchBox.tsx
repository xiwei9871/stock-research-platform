import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { fetchGlobalSearch } from '../api/client';
import type { GlobalSearchResponse, GlobalSearchResult } from '../api/types';

type GlobalSearchBoxProps = {
  onOpenResult: (result: GlobalSearchResult) => void;
};

export function GlobalSearchBox({ onOpenResult }: GlobalSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [payload, setPayload] = useState<GlobalSearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [dismissedQuery, setDismissedQuery] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const trimmedQuery = query.trim();
  const groups = payload?.groups ?? [];
  const results = useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const hasSearched = trimmedQuery.length >= 2;
  const isMenuOpen = hasSearched && (isSearching || Boolean(error) || Boolean(payload));

  useEffect(() => {
    if (trimmedQuery.length < 2 || dismissedQuery === trimmedQuery) {
      requestIdRef.current += 1;
      setPayload(null);
      setError(null);
      setIsSearching(false);
      setHighlightedIndex(-1);
      return;
    }

    const timer = window.setTimeout(() => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setIsSearching(true);
      setError(null);

      fetchGlobalSearch(trimmedQuery, 5)
        .then((nextPayload) => {
          if (requestIdRef.current !== requestId) return;
          setPayload(nextPayload);
          setHighlightedIndex(-1);
        })
        .catch((reason: unknown) => {
          if (requestIdRef.current !== requestId) return;
          setPayload(null);
          setError(reason instanceof Error ? reason.message : 'Search failed.');
          setHighlightedIndex(-1);
        })
        .finally(() => {
          if (requestIdRef.current === requestId) {
            setIsSearching(false);
          }
        });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [dismissedQuery, trimmedQuery]);

  function handleQueryChange(nextQuery: string) {
    requestIdRef.current += 1;
    setDismissedQuery(null);
    setQuery(nextQuery);
    setPayload(null);
    setError(null);
    setIsSearching(false);
    setHighlightedIndex(-1);
  }

  function clearSearch() {
    requestIdRef.current += 1;
    setDismissedQuery(null);
    setQuery('');
    setPayload(null);
    setError(null);
    setIsSearching(false);
    setHighlightedIndex(-1);
  }

  function openResult(result: GlobalSearchResult) {
    onOpenResult(result);
    clearSearch();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      requestIdRef.current += 1;
      setDismissedQuery(trimmedQuery);
      setPayload(null);
      setError(null);
      setIsSearching(false);
      setHighlightedIndex(-1);
      return;
    }

    if (event.key === 'ArrowDown') {
      if (results.length === 0) return;
      event.preventDefault();
      setHighlightedIndex((current) => (current + 1) % results.length);
      return;
    }

    if (event.key === 'ArrowUp') {
      if (results.length === 0) return;
      event.preventDefault();
      setHighlightedIndex((current) => {
        if (current <= 0) return results.length - 1;
        return current - 1;
      });
      return;
    }

    if (event.key === 'Enter' && highlightedIndex >= 0) {
      const result = results[highlightedIndex];
      if (result) {
        event.preventDefault();
        openResult(result);
      }
    }
  }

  return (
    <div className="global-search-box">
      <input
        aria-activedescendant={highlightedIndex >= 0 ? `global-search-result-${highlightedIndex}` : undefined}
        aria-controls={isMenuOpen ? 'global-search-results' : undefined}
        aria-expanded={isMenuOpen}
        aria-label="Global search"
        autoComplete="off"
        onChange={(event) => handleQueryChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Search stocks, news, reports"
        role="combobox"
        type="search"
        value={query}
      />

      {isMenuOpen ? (
        <div aria-label="Global search results" className="global-search-menu">
          {isSearching ? <div className="global-search-status">Searching...</div> : null}
          {error ? <div className="global-search-error">{error}</div> : null}
          {!isSearching && !error && payload && results.length === 0 ? (
            <div className="global-search-empty">No results found.</div>
          ) : null}
          {!error && payload?.warnings?.length ? (
            <div className="global-search-warnings">
              {payload.warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}
          {!error && results.length ? (
            <div id="global-search-results" role="listbox">
              {groups.map((group) =>
                group.items.length ? (
                  <div
                    aria-label={group.label}
                    className="global-search-group"
                    key={group.key}
                    role="group"
                  >
                    <div className="global-search-group-heading">{group.label}</div>
                    {group.items.map((result) => {
                      const resultIndex = results.indexOf(result);
                      const isHighlighted = resultIndex === highlightedIndex;
                      return (
                        <div
                          aria-selected={isHighlighted}
                          className={isHighlighted ? 'global-search-result is-highlighted' : 'global-search-result'}
                          id={`global-search-result-${resultIndex}`}
                          key={`${group.key}:${result.type}:${result.id}:${resultIndex}`}
                          onClick={() => openResult(result)}
                          role="option"
                          tabIndex={-1}
                        >
                          <span className="global-search-result-text">
                            <span className="global-search-result-main">
                              <span className="global-search-result-title">{result.title}</span>
                              {result.subtitle ? (
                                <span className="global-search-result-subtitle">{result.subtitle}</span>
                              ) : null}
                            </span>
                            {result.match_reason ? (
                              <span className="global-search-option-reason">{result.match_reason}</span>
                            ) : null}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : null
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
