# Theme Research And Industry Catalog Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing `主题研究` Dashboard entry into one `主题研究与产业目录` workspace on port 5174, with the current theme-research views and a new read-only industry-catalog browser.

**Architecture:** Keep the canonical AppShell and existing ThemeResearchWorkspace. Add a thin combined workspace that owns the top-level view switch, a focused IndustryCatalogWorkspace for catalog list/detail rendering, and two read-only FastAPI endpoints backed by the existing validated artifact loader.

**Tech Stack:** Python 3.12, FastAPI, pytest, React 18, TypeScript, Vitest, Testing Library, Lucide React, Playwright, Vite.

---

## File Map

- Modify `src/stock_research/dashboard/app.py`: expose catalog list and chain-detail read endpoints.
- Create `tests/test_dashboard_technology_industry_catalog.py`: verify API payloads, 404 handling, and read-only methods.
- Create `dashboard/src/types/technologyIndustryCatalog.ts`: frontend API contracts.
- Create `dashboard/src/api/technologyIndustryCatalog.ts`: typed read-only API client.
- Create `dashboard/src/components/ThemeResearchAndIndustryCatalogWorkspace.tsx`: own top-level segmented navigation and route delegation.
- Create `dashboard/src/components/IndustryCatalogWorkspace.tsx`: render catalog index, hierarchy, filters, and chain detail.
- Modify `dashboard/src/components/AppShell.tsx`: rename navigation and render the combined workspace without changing port or AppShell ownership.
- Modify `dashboard/src/styles.css`: add catalog-specific dense, responsive styles.
- Create `dashboard/tests/technology-industry-catalog-workspace.test.tsx`: component behavior tests.
- Modify `dashboard/tests/theme-research-route.test.tsx`: route and navigation compatibility tests.
- Create `dashboard/tests/theme-research-industry-catalog-full-flow.spec.ts`: real-browser acceptance at port 5174.
- Modify `docs/theme_research_dashboard_v1.md`: document the combined navigation and new routes/API.

### Task 1: Add The Read-only Catalog API

**Files:**
- Create: `tests/test_dashboard_technology_industry_catalog.py`
- Modify: `src/stock_research/dashboard/app.py`

- [ ] **Step 1: Write failing list and detail API tests**

Add tests that create the Dashboard app and assert:

```python
def test_catalog_index_exposes_summary_sectors_and_chains(client):
    response = client.get("/api/research/technology-industry-catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["sector_count"] == 10
    assert payload["summary"]["chain_count"] == 82
    assert payload["research_only"] is True
    assert payload["used_for_signal"] is False
    assert payload["used_for_admission"] is False
    assert len(payload["sectors"]) == 10
    assert len(payload["chains"]) == 82


def test_catalog_chain_detail_exposes_nodes_edges_and_theme_links(client):
    response = client.get(
        "/api/research/technology-industry-catalog/chains/ai_data_center_power"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == "ai_data_center_power"
    assert {node["level"] for node in payload["nodes"]} == {"L3", "L4"}
    assert payload["theme_links"][0]["theme_id"] == "ai_power_value_capture_v1"
```

Also assert an unknown chain returns `404 {"detail": "chain_not_found"}` and `POST`, `PATCH`, `PUT`, and `DELETE` return `405` for both routes.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_technology_industry_catalog.py -q
```

Expected: failures with `404 Not Found` for the new GET routes.

- [ ] **Step 3: Implement the list and detail endpoints**

Import `load_industry_catalog`, `summarize_industry_catalog`, `get_industry_chain`, and `IndustryCatalogValidationError`. Add a small payload builder and these handlers:

```python
@app.get("/api/research/technology-industry-catalog")
def technology_industry_catalog_index():
    catalog = load_industry_catalog()
    return {
        "summary": summarize_industry_catalog(catalog),
        "sectors": catalog["sectors"],
        "chains": catalog["chains"],
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


@app.get("/api/research/technology-industry-catalog/chains/{chain_id}")
def technology_industry_catalog_chain(chain_id: str):
    catalog = load_industry_catalog()
    try:
        detail = get_industry_chain(catalog, chain_id.strip())
    except IndustryCatalogValidationError as exc:
        if exc.code == "CHAIN_NOT_FOUND":
            raise HTTPException(status_code=404, detail="chain_not_found") from exc
        raise
    return {
        **detail,
        "theme_links": [
            link for link in catalog["theme_links"] if link["chain_id"] == chain_id.strip()
        ],
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }
```

- [ ] **Step 4: Run the API tests**

Run `rtk .venv/bin/pytest tests/test_dashboard_technology_industry_catalog.py -q`.

Expected: all tests pass.

- [ ] **Step 5: Commit the API slice**

```bash
rtk git add src/stock_research/dashboard/app.py tests/test_dashboard_technology_industry_catalog.py
rtk git commit -m "feat: expose technology industry catalog dashboard api"
```

### Task 2: Add Typed Frontend Data Access

**Files:**
- Create: `dashboard/src/types/technologyIndustryCatalog.ts`
- Create: `dashboard/src/api/technologyIndustryCatalog.ts`
- Create: `dashboard/tests/technology-industry-catalog-api.test.ts`

- [ ] **Step 1: Write failing API-client tests**

Mock `fetch` and assert the client calls exactly:

```typescript
expect(fetch).toHaveBeenCalledWith('/api/research/technology-industry-catalog', expect.any(Object));
expect(fetch).toHaveBeenCalledWith(
  '/api/research/technology-industry-catalog/chains/ai_data_center_power',
  expect.any(Object)
);
```

Assert a backend `{"detail":"chain_not_found"}` response rejects with `chain_not_found`.

- [ ] **Step 2: Run the client test and verify failure**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/technology-industry-catalog-api.test.ts
```

Expected: module import failure because the client does not exist.

- [ ] **Step 3: Define exact catalog contracts and API functions**

Define `TechnologyIndustryCatalogSummary`, `TechnologyIndustrySector`, `TechnologyIndustryChain`, `TechnologyIndustryNode`, `TechnologyIndustryEdge`, `TechnologyIndustryThemeLink`, `TechnologyIndustryCatalogIndex`, and `TechnologyIndustryChainDetail`. Implement:

```typescript
export function fetchTechnologyIndustryCatalog(): Promise<TechnologyIndustryCatalogIndex> {
  return getJson('/api/research/technology-industry-catalog');
}

export function fetchTechnologyIndustryChain(chainId: string): Promise<TechnologyIndustryChainDetail> {
  return getJson(`/api/research/technology-industry-catalog/chains/${encodeURIComponent(chainId)}`);
}
```

Use the same error-detail parsing convention as `dashboard/src/api/themeResearch.ts`.

- [ ] **Step 4: Run the API-client test**

Run `rtk pnpm --dir dashboard exec vitest run tests/technology-industry-catalog-api.test.ts`.

Expected: all tests pass.

- [ ] **Step 5: Commit the typed data-access slice**

```bash
rtk git add dashboard/src/types/technologyIndustryCatalog.ts dashboard/src/api/technologyIndustryCatalog.ts dashboard/tests/technology-industry-catalog-api.test.ts
rtk git commit -m "feat: add industry catalog dashboard client"
```

### Task 3: Build The Combined Workspace And Catalog Views

**Files:**
- Create: `dashboard/src/components/ThemeResearchAndIndustryCatalogWorkspace.tsx`
- Create: `dashboard/src/components/IndustryCatalogWorkspace.tsx`
- Create: `dashboard/tests/technology-industry-catalog-workspace.test.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/theme-research-route.test.tsx`

- [ ] **Step 1: Write failing workspace tests**

Cover these behaviors with Testing Library:

```typescript
expect(screen.getByRole('button', { name: 'Open Theme Research and Industry Catalog workspace' })).toHaveTextContent(
  '主题研究与产业目录'
);
fireEvent.click(screen.getByRole('tab', { name: '产业目录' }));
expect(window.location.pathname).toBe('/theme-research/catalog');
expect(await screen.findByText('科技产业目录')).toBeInTheDocument();
```

Mock catalog responses and assert:

- summary shows `10` sectors, `82` chains, `13` detailed chains, and `15.85%` completeness;
- search by `AI 数据中心供电` leaves the matching chain visible;
- sector filter restricts chains;
- opening `ai_data_center_power` renders L3/L4 nodes and its linked AI-power theme;
- a skeleton chain renders `该产业链尚未展开 L3/L4 节点`;
- API failure renders a retry button and retry issues a second request.

- [ ] **Step 2: Run workspace tests and verify failure**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/technology-industry-catalog-workspace.test.tsx tests/theme-research-route.test.tsx
```

Expected: missing component and unchanged navigation label failures.

- [ ] **Step 3: Implement the combined route owner**

Create `ThemeResearchAndIndustryCatalogWorkspace` with route classification:

```typescript
const catalogRoute = pathname === '/theme-research/catalog' || pathname.startsWith('/theme-research/catalog/');

return (
  <section className="theme-catalog-shell">
    <nav className="theme-catalog-view-tabs" role="tablist" aria-label="主题研究与产业目录视图">
      <button role="tab" aria-selected={!catalogRoute} onClick={() => onNavigate('/theme-research')}>主题研究</button>
      <button role="tab" aria-selected={catalogRoute} onClick={() => onNavigate('/theme-research/catalog')}>产业目录</button>
    </nav>
    {catalogRoute ? (
      <IndustryCatalogWorkspace pathname={pathname} onNavigate={onNavigate} />
    ) : (
      <ThemeResearchWorkspace pathname={pathname} onNavigate={onNavigate} onOpenStock={onOpenStock} />
    )}
  </section>
);
```

Update AppShell to use the combined component and rename only the existing navigation item. Keep `WorkspaceMode` and `/theme-research` route ownership unchanged.

- [ ] **Step 4: Implement the catalog index and detail**

The index loads the catalog once, computes filtered chains with `useMemo`, and renders metrics plus a sector-grouped table/list. The detail parses `/theme-research/catalog/:chain_id`, loads one chain, groups L4 nodes under their L3 parent, and exposes a back button to `/theme-research/catalog`.

Use Lucide `Search`, `ArrowLeft`, `ChevronRight`, `RefreshCw`, and `Link2` icons. Render enum labels through local lookup tables without modifying artifact values.

- [ ] **Step 5: Run workspace tests**

Run `rtk pnpm --dir dashboard exec vitest run tests/technology-industry-catalog-workspace.test.tsx tests/theme-research-route.test.tsx`.

Expected: all tests pass.

- [ ] **Step 6: Commit the workspace slice**

```bash
rtk git add dashboard/src/components/ThemeResearchAndIndustryCatalogWorkspace.tsx dashboard/src/components/IndustryCatalogWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/tests/technology-industry-catalog-workspace.test.tsx dashboard/tests/theme-research-route.test.tsx
rtk git commit -m "feat: add combined theme research catalog workspace"
```

### Task 4: Add Responsive Styling And Documentation

**Files:**
- Modify: `dashboard/src/styles.css`
- Modify: `docs/theme_research_dashboard_v1.md`

- [ ] **Step 1: Add stable workspace styles**

Add catalog-prefixed classes with:

```css
.theme-catalog-view-tabs {
  display: inline-flex;
  min-height: 36px;
  border-bottom: 1px solid var(--line-soft);
}

.industry-catalog-layout {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 16px;
}

@media (max-width: 820px) {
  .industry-catalog-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

Match existing neutral dashboard colors, use borders rather than decorative cards, keep radii at 8px or less, and give long tables local horizontal overflow.

- [ ] **Step 2: Update the dashboard documentation**

Document the renamed navigation, `/theme-research/catalog` routes, two catalog APIs, read-only guardrails, and the current 10-sector/82-chain artifact scope.

- [ ] **Step 3: Run frontend tests and production build**

Run:

```bash
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

Expected: Vitest passes and Vite build completes without TypeScript errors.

- [ ] **Step 4: Run targeted backend regression tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_technology_industry_catalog.py tests/test_dashboard_theme_research.py tests/test_technology_industry_catalog.py tests/test_technology_industry_catalog_pilots.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit styles and docs**

```bash
rtk git add dashboard/src/styles.css docs/theme_research_dashboard_v1.md
rtk git commit -m "docs: describe combined theme catalog dashboard"
```

### Task 5: Verify The Real App On Port 5174

**Files:**
- Create: `dashboard/tests/theme-research-industry-catalog-full-flow.spec.ts`

- [ ] **Step 1: Write the Playwright acceptance flow**

The test opens the real AppShell, selects `主题研究与产业目录`, switches to `产业目录`, verifies summary and hierarchy data, opens AI data-center power, checks L3/L4 content and the linked theme, and returns to theme research. Repeat overflow checks at desktop `1440x900` and mobile `390x844`:

```typescript
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
expect(overflow).toBeLessThanOrEqual(1);
```

- [ ] **Step 2: Start the existing backend and frontend**

Run the backend from repository root:

```bash
rtk env PYTHONPATH=src .venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Run the existing frontend from `dashboard`:

```bash
rtk pnpm dev --host 127.0.0.1 --port 5174
```

Do not choose another frontend port. If 5174 is occupied, identify and stop the stale project dev server before starting this branch.

- [ ] **Step 3: Run Playwright**

Run:

```bash
rtk pnpm --dir dashboard exec playwright test tests/theme-research-industry-catalog-full-flow.spec.ts --project=chromium
```

Expected: desktop and mobile scenarios pass.

- [ ] **Step 4: Visually inspect screenshots**

Use the browser tooling to verify the real page at `http://127.0.0.1:5174/theme-research/catalog` has no overlapping controls, clipped labels, page-level horizontal overflow, or blank data regions.

- [ ] **Step 5: Run final verification and commit**

Run:

```bash
rtk git diff --check
rtk git status --short
```

Commit the Playwright test:

```bash
rtk git add dashboard/tests/theme-research-industry-catalog-full-flow.spec.ts
rtk git commit -m "test: cover theme catalog dashboard flow"
```

- [ ] **Step 6: Push the integration branch**

```bash
rtk git push -u origin integration/research-platform-validation-20260713
```

Expected: the remote integration branch contains the design, implementation, tests, and browser acceptance flow.
