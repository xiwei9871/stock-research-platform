# Market Chart Tooltip Interaction Design

**Date:** 2026-07-27

**Status:** Approved design, pending written-spec review

## Context

Two user-facing chart interaction defects were confirmed on the live local platform:

1. Concept-sector heatmap tiles such as `ST板块` do not show hover details. The API data is complete, but the page is displaying the compatibility/fallback treemap while the ECharts layer has no rendered children. The fallback tiles only implement click behavior and do not implement the tooltip contract used by ECharts.
2. In the stock workspace, hovering the rightmost bar positions the K-line tooltip at `pointerX + 14` without accounting for tooltip width or chart boundaries. The tooltip extends beyond the right edge and clips fields such as high, close, and amount.

The industry heatmap containing only one rising sector on 2026-07-24 is not a defect. The industry API returned 85 completed rows with one positive and 84 negative sectors.

## Goal

Make chart hover behavior complete and consistent across industry heatmaps, concept heatmaps, and stock price charts. Every supported rendering path must expose the same human-readable information, and tooltips must remain fully visible within the chart area.

## Non-Goals

- Do not change sector-return calculations, sector ranking, heatmap sizing, or market data.
- Do not add new sector-detail fields or backend endpoints.
- Do not redesign the stock chart, range selector, candle rendering, or time-axis logic.
- Do not introduce Firefox as a required browser target; the release gate remains Chromium-first.
- Do not modify strategy publication behavior or the three dirty Tech Bottleneck research datasets in the main checkout.

## Considered Approaches

### A. Repair only the ECharts path

Ensure ECharts always initializes and rely on its built-in tooltip.

This is insufficient because the compatibility path is intentionally present for environments where ECharts cannot render. A fallback without equivalent information remains an accessibility and reliability gap.

### B. Add browser-native `title` attributes only

Add a `title` string to fallback heatmap tiles and rely on the browser tooltip.

This is low effort but produces delayed, inconsistently styled tooltips and cannot be tested reliably for full content or positioning.

### C. Shared explicit tooltip contract for all paths

Use one normalized tooltip-content model for ECharts and fallback heatmaps, add a controlled hover panel to the fallback path, and introduce a reusable boundary-aware position calculation for stock-chart tooltips.

This is the selected approach. It fixes the current fallback behavior while keeping ECharts as the preferred renderer and makes the contracts directly testable.

## Design

### 1. Heatmap Information Contract

Industry and concept tiles expose the same fields when hovered or keyboard-focused:

- sector name;
- signed change percentage;
- traded amount;
- rising constituent count;
- falling constituent count;
- total constituent count when available;
- main net inflow when available, otherwise `--` rather than a fabricated zero.

The current frontend mapper must preserve nullable values required by this display contract. Missing backend values must remain distinguishable from real zero values.

### 2. Preferred ECharts Rendering

The ECharts tooltip formatter continues to consume the normalized sector item. Initialization readiness must be determined from the actual chart instance/rendered canvas state rather than a fragile immediate child-count assumption.

When the chart is ready:

- the compatibility layer is removed from pointer interaction;
- hovering any tile displays the shared information contract;
- clicking a tile selects the sector and loads the existing detail flow;
- switching between industry and concept updates data without leaving a stale chart instance or tooltip.

Initialization failure remains recoverable and must not make the heatmap unusable.

### 3. Compatibility Heatmap Rendering

The fallback treemap gains an explicit controlled tooltip:

- pointer enter or keyboard focus selects the hovered item for display;
- pointer leave or blur hides the tooltip;
- click retains the existing sector-selection behavior;
- the tooltip uses the same content formatter as ECharts;
- its position is clamped within the heatmap chart container;
- it does not obscure pointer events on the underlying tile.

This makes industry and concept interaction identical even when ECharts is unavailable.

### 4. Stock K-Line Tooltip Positioning

Replace the fixed `left: pointerX + 14` placement with a boundary-aware calculation based on:

- pointer coordinates relative to the chart shell;
- measured tooltip width and height;
- chart-shell width and height;
- a fixed safe margin and cursor gap.

Horizontal behavior:

1. Prefer the right side of the cursor.
2. If the tooltip would cross the right safe margin, place it to the left of the cursor.
3. Clamp the final position between the left and right safe margins.

Vertical behavior:

1. Prefer above the cursor using the existing visual offset.
2. Clamp the final position so the top and bottom remain inside the chart region.

The content remains `time, open, high, low, close, volume, amount`. The same positioning function applies to daily, weekly, monthly, and intraday modes.

### 5. Component Boundaries

Keep the changes focused:

- `SectorHeatmapPanel.tsx`: shared heatmap tooltip formatting, renderer readiness, fallback hover/focus state, and fallback tooltip markup;
- `AssetChart.tsx`: tooltip measurement and pure boundary-aware position calculation;
- `styles.css`: tooltip presentation only;
- focused frontend tests and Playwright acceptance coverage.

Pure formatting and positioning logic should be separately testable without mounting the chart library.

## Error And Edge Handling

- Null amount, constituent counts, or net inflow render as `--`.
- A heatmap with one tile still supports hover, focus, and click.
- An empty directional side keeps the existing no-data message and creates no tooltip.
- Switching sector type clears obsolete hover state.
- Resizing the chart recomputes tooltip placement from the latest container dimensions.
- A tooltip wider than the available chart area is constrained by CSS and clamped to the safe margin.
- Moving off a K-line data point clears the tooltip as today.

## Testing Strategy

Implementation follows test-driven development.

### Unit And Component Tests

- heatmap tooltip formatter preserves `null` as `--` and displays real zero as zero;
- fallback industry and concept tiles expose identical hover/focus content;
- fallback click still selects the correct sector;
- switching industry/concept clears stale hover content;
- position helper prefers the right side in the chart center;
- position helper flips left at the rightmost bar;
- position helper clamps at the left, top, and bottom edges;
- all six K-line fields remain in the rendered tooltip.

### Playwright Acceptance

Chromium-first checks cover:

- industry heatmap tile hover and click;
- concept `ST板块` hover and click;
- fallback mode with complete hover information;
- daily, weekly, monthly, and intraday rightmost-bar hover;
- tooltip bounding box remains inside the chart shell;
- `开、高、低、收、量、额` are all visible at the right edge.

The tests must assert geometry and visible content, not only the presence of a tooltip DOM node.

## Acceptance Criteria

- Industry and concept heatmaps provide the same hover, keyboard-focus, and click semantics.
- `ST板块` displays complete hover information in both ECharts and fallback rendering paths.
- Missing net inflow or count fields are not silently converted to zero.
- The stock tooltip never crosses the chart shell's left, right, top, or bottom safe margin.
- The rightmost daily, weekly, monthly, and intraday bars show all six price/volume fields.
- Existing heatmap selection, sector-detail loading, stock-chart range controls, and candle data remain unchanged.
- Focused dashboard tests, dashboard build, and Chromium Playwright acceptance pass from the stable integration worktree.

## Rollback

Revert the focused frontend commit. No database, market-data, or publication artifact rollback is required.
