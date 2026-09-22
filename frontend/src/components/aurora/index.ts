/**
 * aurora — the shared design system, per spec 00 A2.
 *
 * All nine components the spec names:
 *
 * | component            | file            | spec 00 A2 |
 * |----------------------|-----------------|------------|
 * | `Card` (frosted)     | surfaces.tsx    | ✓ |
 * | `StatBadge`          | indicators.tsx  | ✓ |
 * | `ConfidencePill`     | indicators.tsx  | ✓ (0-1 → colour + label) |
 * | `EvidencePanel`      | evidence.tsx    | ✓ |
 * | `TraceTimeline`      | evidence.tsx    | ✓ (step list for agent runs) |
 * | `RiskTag`            | indicators.tsx  | ✓ |
 * | `MetricTile`         | surfaces.tsx    | ✓ |
 * | `EmptyState`         | surfaces.tsx    | ✓ |
 * | `SyntheticDataBanner`| surfaces.tsx    | ✓ |
 *
 * **Why four files and not nine.** Grouped by role — surfaces, indicators, evidence — because
 * the indicators share the confidence-band table and splitting them would mean three files
 * importing it. A one-component-per-file layout is the usual convention and would be right for
 * a published package; here the grouping is what keeps the shared logic in one place.
 *
 * **Why they live in this repo rather than an `aurora-ui` package.** The brief specifies
 * `frontend/src/components/aurora/`. Spec 00 A2's own argument for a package still applies —
 * *"one import line in any project yields the shared look"* — so nothing here imports from a
 * screen, and the CSS is token-driven rather than utility-driven. Lifting this directory into a
 * package is a move, not a rewrite.
 *
 * Every one of them is rendered on the `/aurora` route, which is spec 00 A2's acceptance
 * criterion: *"Storybook (or a demo route) renders every component."*
 */

import './tokens.css';
import './aurora.css';

export { Card, EmptyState, MetricTile, SyntheticDataBanner } from './surfaces';
export type {
  CardProps,
  EmptyStateProps,
  MetricTileProps,
  SyntheticDataBannerProps,
} from './surfaces';

export { CONFIDENCE_BANDS, ConfidencePill, RiskTag, StatBadge, bandFor } from './indicators';
export type { BadgeTone, ConfidencePillProps, RiskTagProps, StatBadgeProps } from './indicators';

export { EvidencePanel, TraceTimeline } from './evidence';
export type {
  EvidencePanelProps,
  TraceSpan,
  TraceTimelineProps,
} from './evidence';
