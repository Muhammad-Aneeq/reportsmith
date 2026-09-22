/**
 * ConfidencePill, StatBadge, RiskTag — spec 00 A2.
 *
 * Grouped by role rather than one file per component: these three are the "how should I feel
 * about this?" primitives, they share the band logic below, and splitting them would mean
 * three files importing the same table.
 */

import type { ReactNode } from 'react';

/**
 * Confidence bands. Spec 00 A2 asks for *"ConfidencePill (0-1 → color+label)"* — a colour
 * **and** a label, and the label is not decoration:
 *
 * - a reviewer with deuteranopia cannot distinguish amber from green, and this is the widget
 *   the whole human gate is read through;
 * - a colour says "bad" where a word can say *why* — "review" and "cannot tell" are different
 *   requests, and a pill that renders them identically turns the gate into a rubber stamp.
 *
 * The boundaries are the manifest's thresholds (0.85 / 0.60). They are duplicated here as a
 * *presentation* default and the pill accepts overrides, because the console renders decisions
 * made under whichever manifest was active at the time — hard-coding today's numbers would
 * mislabel yesterday's decisions after a rollback.
 */
export const CONFIDENCE_BANDS = [
  { min: 0.85, label: 'auto', color: 'var(--aurora-positive)', hint: 'posted without review' },
  { min: 0.6, label: 'review', color: 'var(--aurora-amber)', hint: 'a human confirms the target' },
  { min: 0.0, label: 'cannot tell', color: 'var(--aurora-rose)', hint: 'no target proposed' },
] as const;

export function bandFor(
  confidence: number,
  thresholds?: { auto: number; escalateFloor: number },
): (typeof CONFIDENCE_BANDS)[number] {
  if (thresholds) {
    if (confidence >= thresholds.auto) return CONFIDENCE_BANDS[0];
    if (confidence >= thresholds.escalateFloor) return CONFIDENCE_BANDS[1];
    return CONFIDENCE_BANDS[2];
  }
  return CONFIDENCE_BANDS.find((band) => confidence >= band.min) ?? CONFIDENCE_BANDS[2];
}

export interface ConfidencePillProps {
  confidence: number;
  /** Override the bands with the manifest that produced this decision. */
  thresholds?: { auto: number; escalateFloor: number };
  /** Hide the word, for dense table cells where the header already says what the column is. */
  showLabel?: boolean;
  className?: string;
}

export function ConfidencePill({
  confidence,
  thresholds,
  showLabel = true,
  className = '',
}: ConfidencePillProps) {
  const band = bandFor(confidence, thresholds);
  const percent = `${Math.round(confidence * 100)}%`;

  return (
    <span
      className={`au-pill ${className}`}
      style={{ color: band.color }}
      /* The band name and its meaning in the accessible name, so a screen reader gets
         "72%, review — a human confirms the target" rather than "72%". */
      title={`${percent} · ${band.label} — ${band.hint}`}
      aria-label={`confidence ${percent}, ${band.label}`}
      data-testid="confidence-pill"
      data-band={band.label}
    >
      <span className="au-pill__dot" aria-hidden="true" />
      <span className="au-pill__value">{percent}</span>
      {showLabel ? <span className="au-pill__label">{band.label}</span> : null}
    </span>
  );
}

export type BadgeTone = 'neutral' | 'good' | 'warn' | 'bad';

export interface StatBadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  /**
   * Marks a value that is not a real measurement — an offline eval run, a fallback corpus.
   * Renders a dashed border on top of the tone, because a green PASS next to a subtle grey
   * "offline" reads as a pass. The repo's honesty rests on this being visible at a glance
   * (BLOCKERS.md B2).
   */
  mock?: boolean;
  title?: string;
}

export function StatBadge({ children, tone = 'neutral', mock = false, title }: StatBadgeProps) {
  const classes = ['au-badge'];
  if (tone !== 'neutral') classes.push(`au-badge--${tone}`);
  if (mock) classes.push('au-badge--mock');

  return (
    <span className={classes.join(' ')} title={title} data-testid="stat-badge" data-tone={tone}>
      {children}
      {mock ? <span aria-label="not a live measurement">·mock</span> : null}
    </span>
  );
}

/**
 * Why a decision needs a human, as a tag. Spec 00 A2's `RiskTag`.
 *
 * Keyed on the agent's closed `reason_code` vocabulary rather than on free text, and ordered by
 * *what a reviewer must do*: a suspected duplicate needs someone to stop a second payment,
 * which is a different urgency from a missing reference. The queue sorts on these, so a wrong
 * tone here buries the case that matters.
 */
const RISK_STYLES: Record<string, { label: string; color: string; glyph: string }> = {
  duplicate_suspected: { label: 'duplicate', color: 'var(--aurora-rose)', glyph: '⧉' },
  dispute_suspected: { label: 'dispute', color: 'var(--aurora-rose)', glyph: '⚖' },
  ambiguous_candidates: { label: 'ambiguous', color: 'var(--aurora-amber)', glyph: '⁇' },
  insufficient_evidence: { label: 'no evidence', color: 'var(--aurora-amber)', glyph: '∅' },
  unresolved_counterparty: { label: 'unknown payee', color: 'var(--aurora-amber)', glyph: '?' },
  partial_payment: { label: 'partial', color: 'var(--aurora-amber)', glyph: '½' },
  amount_mismatch: { label: 'amount', color: 'var(--aurora-amber)', glyph: '≠' },
  low_confidence: { label: 'low confidence', color: 'var(--aurora-slate)', glyph: '·' },
};

export interface RiskTagProps {
  /** A `reason_code` from the agent, or any string — unknown codes render as themselves. */
  code: string | null | undefined;
  className?: string;
}

export function RiskTag({ code, className = '' }: RiskTagProps) {
  if (!code) return null;

  // An unknown code renders as itself rather than as "unknown". A new reason code shipped by
  // the agent should show up in the console immediately, even before the styling catches up —
  // silently swallowing it would hide the thing the agent is trying to say.
  const style = RISK_STYLES[code] ?? {
    label: code.replace(/_/g, ' '),
    color: 'var(--aurora-slate)',
    glyph: '·',
  };

  return (
    <span
      className={`au-risk ${className}`}
      style={{ color: style.color }}
      title={code}
      data-testid="risk-tag"
      data-code={code}
    >
      <span className="au-risk__glyph" aria-hidden="true">
        {style.glyph}
      </span>
      {style.label}
    </span>
  );
}
