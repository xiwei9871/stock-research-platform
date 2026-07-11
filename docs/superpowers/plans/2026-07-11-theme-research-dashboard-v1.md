# Theme Research Dashboard v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 7's read-only Theme Research dashboard on top of validated P1-P6 artifacts, with a theme index, route-backed detail tabs, and links into the existing tech-bottleneck stock workflow.

**Architecture:** A focused Python read-model module joins existing P1-P6 loaders and is exposed through six GET-only FastAPI routes. A feature-local React API/type layer and one route-aware workspace integrate into the existing `AppShell` without adding a router dependency or any write path.

**Tech Stack:** Python 3, FastAPI, pytest, React 19, TypeScript, Vite, Vitest, Testing Library, Playwright, lucide-react, existing CSS system.

---

### Task 1: Backend theme research read models

**Files:**
- Create: `tests/test_dashboard_theme_research.py`
- Create: `src/stock_research/dashboard/theme_research.py`

- [x] **Step 1: Write failing read-model tests**

Add tests that call the public functions directly and assert:

```python
def test_theme_index_aggregates_validated_phase_outputs():
    payload = list_theme_research_themes()
    assert payload["total"] == 2
    ai_power = next(row for row in payload["items"] if row["theme_id"] == "ai_power_value_capture_v1")
    assert ai_power["node_count"] == 13
    assert ai_power["company_count"] == 4
    assert ai_power["research_only"] is True
    assert ai_power["used_for_signal"] is False


def test_theme_detail_contains_priority_and_evidence_distributions():
    detail = get_theme_research_theme("ai_power_value_capture_v1")
    assert detail["theme"]["theme_name"] == "AI供电产业链：谁在拿走价值量"
    assert detail["company_summary"]["total"] == 4
    assert detail["evidence_gap_summary"]["total"] > 0
    assert detail["source_reliability_distribution"]


def test_theme_collections_are_scoped_and_joined():
    nodes = list_theme_research_nodes("ai_power_value_capture_v1")
    companies = list_theme_research_companies("ai_power_value_capture_v1")
    assert all(row["theme_id"] == "ai_power_value_capture_v1" for row in nodes["items"])
    assert companies["items"][0]["tech_bottleneck_stock_path"].startswith("/tech-bottleneck/stock/")
    assert all(row["used_for_signal"] is False for row in companies["items"])
```

Also cover sources, claims, deterministic ordering, unknown themes, and absence of DB/network calls.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_theme_research.py -q
```

Expected: import failure because `stock_research.dashboard.theme_research` does not exist.

- [x] **Step 3: Implement the read-model module**

Create these public functions:

```python
class ThemeResearchNotFoundError(LookupError):
    pass


def list_theme_research_themes() -> dict[str, Any]: ...
def get_theme_research_theme(theme_id: str) -> dict[str, Any]: ...
def list_theme_research_nodes(theme_id: str) -> dict[str, Any]: ...
def list_theme_research_sources(theme_id: str) -> dict[str, Any]: ...
def list_theme_research_claims(theme_id: str) -> dict[str, Any]: ...
def list_theme_research_companies(theme_id: str) -> dict[str, Any]: ...
```

Load `load_theme_research_priority_package()` once per function call, derive indexes from its included P1-P6 packages, and return new dictionaries rather than mutating loader output. Use stable sorts:

```text
themes: theme_name, theme_id
nodes: descending priority_score, node_id
sources: reliability_level, publish_date descending, source_id
claims: evidence_status, claim_id
companies: descending company_research_priority_score, company_code, mapping_id
```

Company paths use the six-digit code:

```python
stock_code = row["company_code"].split(".", 1)[0]
path = f"/tech-bottleneck/stock/{stock_code}?source=theme_research"
```

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_theme_research.py -q
```

Expected: all direct read-model tests pass.

### Task 2: GET-only FastAPI routes

**Files:**
- Modify: `tests/test_dashboard_theme_research.py`
- Modify: `src/stock_research/dashboard/app.py`

- [x] **Step 1: Add failing API tests**

Add `TestClient` tests for all six routes:

```python
def test_theme_research_routes_are_read_only_and_return_scoped_payloads():
    client = TestClient(dashboard_app.create_app())
    themes = client.get("/api/research/theme-decomposition/themes")
    nodes = client.get("/api/research/theme-decomposition/themes/ai_power_value_capture_v1/nodes")
    assert themes.status_code == 200
    assert nodes.status_code == 200
    assert all(row["theme_id"] == "ai_power_value_capture_v1" for row in nodes.json()["items"])
    assert client.post("/api/research/theme-decomposition/themes", json={}).status_code == 405


def test_unknown_theme_returns_404():
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/research/theme-decomposition/themes/missing-theme")
    assert response.status_code == 404
    assert response.json()["detail"] == "theme_not_found"
```

- [x] **Step 2: Run API tests and verify RED**

Run the two route tests and expect 404 because routes are absent.

- [x] **Step 3: Register the six GET routes**

Import the read functions and translate `ThemeResearchNotFoundError` to:

```python
raise HTTPException(status_code=404, detail="theme_not_found") from exc
```

Do not add POST, PATCH, PUT, DELETE, write guards, cache invalidation, or database setup.

- [x] **Step 4: Run backend regression**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_theme_research.py tests/test_theme_research_priority.py tests/test_theme_tech_bottleneck_crosswalk.py tests/test_theme_company_mapping.py tests/test_theme_decomposition.py -q
```

Expected: all tests pass.

### Task 3: Frontend API contract and workspace states

**Files:**
- Create: `dashboard/src/types/themeResearch.ts`
- Create: `dashboard/src/api/themeResearch.ts`
- Create: `dashboard/tests/theme-research-workspace.test.tsx`
- Create: `dashboard/src/components/ThemeResearchWorkspace.tsx`

- [x] **Step 1: Define failing component tests with mocked GET APIs**

Test these user-visible behaviors:

```tsx
it('shows the theme index and opens a theme overview', async () => {
  render(<ThemeResearchWorkspace pathname="/theme-research" onNavigate={navigate} />);
  expect(await screen.findByRole('heading', { name: '主题研究' })).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: /AI供电产业链/ }));
  expect(navigate).toHaveBeenCalledWith('/theme-research/ai_power_value_capture_v1');
});

it('renders route-backed node, source and company states', async () => {
  const { rerender } = render(<ThemeResearchWorkspace pathname="/theme-research/ai_power_value_capture_v1/nodes" onNavigate={navigate} />);
  expect(await screen.findByText('证据补齐优先')).toBeInTheDocument();
  rerender(<ThemeResearchWorkspace pathname="/theme-research/ai_power_value_capture_v1/companies" onNavigate={navigate} />);
  expect(await screen.findByText('覆盖缺口')).toBeInTheDocument();
});
```

Also test loading, retryable error, empty theme list, missing theme, source and claim separation, and stock-link callback.

- [x] **Step 2: Run Vitest and verify RED**

Run:

```bash
rtk pnpm --dir dashboard test -- theme-research-workspace.test.tsx
```

Expected: import failure because the feature files do not exist.

- [x] **Step 3: Implement TypeScript types and GET client**

Define explicit types for theme index/detail, node, source, claim, company, and collection responses. Implement:

```typescript
fetchThemeResearchThemes()
fetchThemeResearchTheme(themeId)
fetchThemeResearchNodes(themeId)
fetchThemeResearchSources(themeId)
fetchThemeResearchClaims(themeId)
fetchThemeResearchCompanies(themeId)
```

Use the existing `getJson` client helper and `encodeURIComponent(themeId)`.

- [x] **Step 4: Implement the workspace**

The component accepts:

```typescript
type Props = {
  pathname: string;
  onNavigate: (path: string) => void;
  onOpenStock: (path: string) => void;
};
```

Implement the theme index and overview/nodes/sources/companies tabs. Keep filters local. Use semantic tables, `aria-selected` tabs, explicit loading/error/empty states, and lucide icons for back, retry, and external handoff actions.

- [x] **Step 5: Run component tests and verify GREEN**

Run the focused Vitest file until all states pass.

### Task 4: AppShell routing and cross-workspace handoff

**Files:**
- Create: `dashboard/tests/theme-research-route.test.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`

- [x] **Step 1: Add failing shell route tests**

Mock `ThemeResearchWorkspace` and assert:

```tsx
it('opens theme research from primary navigation', () => {
  render(<AppShell />);
  fireEvent.click(screen.getByRole('button', { name: 'Open Theme Research workspace' }));
  expect(window.location.pathname).toBe('/theme-research');
});

it('restores direct child routes and hands companies to the stock workspace', () => {
  window.history.pushState({}, '', '/theme-research/ai_power_value_capture_v1/companies');
  render(<AppShell />);
  expect(screen.getByText('/theme-research/ai_power_value_capture_v1/companies')).toBeInTheDocument();
});
```

- [x] **Step 2: Run route tests and verify RED**

Expected: navigation item and workspace mode are absent.

- [x] **Step 3: Integrate `themeResearch` workspace mode**

Add:

```text
WorkspaceMode: themeResearch
NAV_ITEMS label: 主题研究
path matcher: /theme-research and descendants
primary path: /theme-research
```

Pass `window.location.pathname` into the workspace. Theme child navigation pushes history and updates component state. Company stock paths use the existing location-change mechanism so the normal Stock Workspace handoff handles `/tech-bottleneck/stock/...`.

- [x] **Step 4: Add scoped responsive CSS**

Add `.theme-research-*` rules for:

- compact header and metric strip;
- route tabs;
- filters;
- fixed-layout tables and score columns;
- categorical badges;
- desktop and mobile overflow behavior;
- loading, empty, error, and not-found states.

Avoid nested cards and preserve `border-radius <= 8px`.

- [x] **Step 5: Run frontend unit tests and build**

Run:

```bash
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

Expected: all Vitest tests and TypeScript/Vite build pass.

### Task 5: Browser acceptance and documentation

**Files:**
- Create: `dashboard/tests/theme-research-full-flow.spec.ts`
- Create: `docs/theme_research_dashboard_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] **Step 1: Add Playwright acceptance**

Cover desktop `1440x900` and mobile `390x844`:

```text
open /theme-research
verify two themes and summary counts
open AI power overview
navigate nodes, sources, companies
verify URL for every tab
verify evidence-gap and coverage-gap labels
open a mapped stock and verify stock-workspace route
use browser back to return to the companies tab
```

Use route mocks only if the normal local API cannot run in Playwright; otherwise use the real P1-P6 artifact API.

- [x] **Step 2: Start or reuse local servers**

Start the API and Vite frontend on free ports. Record the user-facing frontend URL. Do not replace a running service on port 5174.

- [x] **Step 3: Run Playwright and inspect screenshots**

Run the focused spec. Inspect desktop and mobile screenshots for blank content, clipped text, overlapping controls, unstable table columns, and broken stock handoff.

- [x] **Step 4: Document Phase 7**

Document routes, API endpoints, read-only guardrails, navigation model, company handoff, commands, and current boundaries in `docs/theme_research_dashboard_v1.md`. Mark Phase 7 complete while keeping Phases 8-10 unfinished.

- [x] **Step 5: Final verification**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_theme_research.py tests/test_theme_research_priority.py tests/test_theme_tech_bottleneck_crosswalk.py tests/test_theme_company_mapping.py tests/test_theme_decomposition.py -q
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
rtk pnpm --dir dashboard test:e2e -- theme-research-full-flow.spec.ts
```

Also validate Python compilation, TypeScript build output, scoped trailing whitespace, route methods, and independent review findings before declaring Phase 7 complete.
