/**
 * EvidencePanel and TraceTimeline — spec 00 A2, and the heart of spec 06 §9 screen 3.
 *
 * These two are the ones the whole project is about. Everything else in the console is
 * navigation; these are where a reviewer answers *"can I trust this decision?"*
 */

import type { ReactNode } from 'react';

/** What an evidence id refers to, inferred from its prefix. */
function kindOf(id: string): string {
  if (id.startsWith('TXN-')) return 'txn';
  if (id.startsWith('INV-')) return 'invoice';
  if (id.startsWith('GL-')) return 'gl';
  if (id.startsWith('CP-')) return 'payee';
  if (id.startsWith('NOTE-')) return 'note';
  return 'id';
}

export interface EvidencePanelProps {
  evidenceIds: string[];
  /**
   * The id the decision concludes *is* the answer. Highlighted, because "the evidence includes
   * the thing concluded" is one of check 3's rules — a reviewer should be able to see it holds
   * rather than take it on trust.
   */
  targetId?: string | null;
  /**
   * Ids the run never observed. Should always be empty: `validate_for_persistence` refuses a
   * match with an ungrounded citation before it can be persisted (check 3). Rendered anyway,
   * in red, because if enforcement is ever bypassed the console must *show* it rather than
   * display a fabrication as though it were evidence.
   */
  ungroundedIds?: string[];
  emptyHint?: string;
}

export function EvidencePanel({
  evidenceIds,
  targetId,
  ungroundedIds = [],
  emptyHint = 'This decision cites nothing, which check 3 should have prevented.',
}: EvidencePanelProps) {
  if (evidenceIds.length === 0) {
    return (
      <p className="au-timeline__attrs" data-testid="evidence-empty">
        {emptyHint}
      </p>
    );
  }

  const ungrounded = new Set(ungroundedIds);

  return (
    <div className="au-evidence" data-testid="evidence-panel">
      {evidenceIds.map((id) => {
        const classes = ['au-chip'];
        if (id === targetId) classes.push('au-chip--target');
        if (ungrounded.has(id)) classes.push('au-chip--ungrounded');

        return (
          <span
            key={id}
            className={classes.join(' ')}
            data-testid="evidence-chip"
            data-grounded={ungrounded.has(id) ? 'false' : 'true'}
            title={
              ungrounded.has(id)
                ? `${id} was never returned by a tool call in this run — an ungrounded citation`
                : id === targetId
                  ? `${id} is the proposed target, and it is cited`
                  : id
            }
          >
            <span className="au-chip__kind">{kindOf(id)}</span>
            {id}
            {ungrounded.has(id) ? <span aria-label="ungrounded">⚠</span> : null}
          </span>
        );
      })}
    </div>
  );
}

/** One row of the timeline. Mirrors the companion's span shape. */
export interface TraceSpan {
  span_id: string;
  name: string
  duration_ms: number;
  attributes: Record<string, unknown>;
  events?: { name: string; attributes: Record<string, unknown> }[];
}

export interface TraceTimelineProps {
  spans: TraceSpan[];
  /** The span that produced the decision being viewed — highlighted in the sequence. */
  highlightSpanId?: string | null;
  emptyTitle?: string;
  emptyHint?: string;
}

/**
 * Spec 00 A2's `TraceTimeline` — *"step list for agent runs"* — and spec 06 §9 screen 3's
 * *"TraceTimeline of the decision"*.
 *
 * Reads as the graph's own sequence: `load_period → fetch_data → propose_matches →
 * score_confidence → route → …`, because the companion orders spans by start time with the
 * agent's monotonic sequence as the tie-break. That ordering is load-bearing rather than
 * cosmetic — on Windows two fast nodes start in the same clock tick, and an early version of
 * this rendered `route` after `emit_approval_request`. A timeline that lies about the order
 * work happened in is worse than no timeline.
 *
 * The decision's own span is highlighted rather than shown alone. A reviewer asks two
 * questions — "what happened here?" and "where in the run did this happen?" — and the second
 * one arrives as soon as something looks wrong.
 */
export function TraceTimeline({
  spans,
  highlightSpanId,
  emptyTitle = 'No trace for this decision',
  emptyHint = 'Tracing may be disabled, or the spans have rotated. See docs/CHECKS.md.',
}: TraceTimelineProps) {
  if (spans.length === 0) {
    return (
      <div className="au-empty" data-testid="timeline-empty">
        <div className="au-empty__glyph" aria-hidden="true">
          ◌
        </div>
        <div className="au-empty__title">{emptyTitle}</div>
        <p className="au-empty__hint">{emptyHint}</p>
      </div>
    );
  }

  return (
    <div className="au-timeline" data-testid="trace-timeline">
      {spans.map((span) => {
        const isDecision = span.name === 'decision';
        const isHighlighted = highlightSpanId ? span.span_id === highlightSpanId : false;

        return (
          <div
            className="au-timeline__row"
            key={span.span_id}
            data-testid="timeline-row"
            data-span-name={span.name}
            data-highlighted={isHighlighted ? 'true' : 'false'}
            style={
              isHighlighted
                ? { background: 'var(--aurora-accent-glow)', borderRadius: 8, paddingLeft: 4 }
                : undefined
            }
          >
            <span
              className={`au-timeline__dot${isDecision ? ' au-timeline__dot--decision' : ''}`}
              aria-hidden="true"
            />
            <div>
              <div className="au-timeline__name">
                {/* `node.` is noise once you know you are looking at a graph. */}
                {span.name.replace(/^node\./, '')}
                {isHighlighted ? ' ← this decision' : ''}
              </div>
              {renderAttributes(span.attributes)}
              {(span.events ?? []).map((event, index) => (
                <div className="au-timeline__event" key={`${event.name}-${index}`}>
                  ⚠ {event.name.replace(/_/g, ' ')}
                  {renderEventDetail(event.attributes)}
                </div>
              ))}
            </div>
            <div className="au-timeline__duration">{span.duration_ms.toFixed(1)} ms</div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Span attributes, as a compact line.
 *
 * `run_id`, `node` and `seq` are dropped: the first is on every span in the trace, the second
 * duplicates the row's own name, and the third is an ordering mechanism rather than a fact
 * about the work. Showing all three would bury `txn_id` and `confidence`, which are the two a
 * reviewer is actually reading.
 */
function renderAttributes(attributes: Record<string, unknown>): ReactNode {
  const shown = Object.entries(attributes).filter(
    ([key]) => !['run_id', 'node', 'seq', 'period', 'agent_version', 'config_hash'].includes(key),
  );
  if (shown.length === 0) return null;

  return (
    <div className="au-timeline__attrs">
      {shown.map(([key, value]) => `${key}=${String(value)}`).join('  ·  ')}
    </div>
  );
}

function renderEventDetail(attributes: Record<string, unknown>): ReactNode {
  const ids = attributes['ledgerguard.ungrounded_ids'] ?? attributes['ungrounded_ids'];
  if (Array.isArray(ids) && ids.length > 0) {
    return <> — cited {ids.join(', ')}, which the run never saw</>;
  }
  return null;
}
