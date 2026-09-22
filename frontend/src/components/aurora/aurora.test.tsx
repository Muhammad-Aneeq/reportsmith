/**
 * The aurora components' load-bearing behaviour.
 *
 * Not snapshot tests. What matters about these components is not how they look — that is what
 * the `/aurora` route and a screenshot are for — but the handful of places where getting the
 * *content* wrong would mislead a reviewer:
 *
 * - a confidence band mislabelled, so "cannot tell" reads as "review";
 * - a mock result rendered indistinguishably from a live one;
 * - an ungrounded citation shown as though it were evidence;
 * - a timeline in the wrong order.
 *
 * Each of those is a way the console could lie, which is the only kind of UI bug this project
 * cannot tolerate.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  ConfidencePill,
  EvidencePanel,
  RiskTag,
  StatBadge,
  SyntheticDataBanner,
  TraceTimeline,
  bandFor,
  type TraceSpan,
} from './index';

describe('ConfidencePill', () => {
  it('labels each band, not just colours it', () => {
    // Spec 00 A2 asks for "0-1 → color+label". The label is what a reviewer with
    // deuteranopia reads, and this is the widget the whole human gate runs through.
    render(<ConfidencePill confidence={1.0} />);
    expect(screen.getByTestId('confidence-pill')).toHaveAttribute('data-band', 'auto');
    expect(screen.getByText('auto')).toBeInTheDocument();
  });

  it.each([
    [1.0, 'auto'],
    [0.85, 'auto'],
    [0.8499, 'review'],
    [0.6, 'review'],
    [0.5999, 'cannot tell'],
    [0.0, 'cannot tell'],
  ])('%s falls in the %s band', (confidence, expected) => {
    // The same boundaries the manifest uses, tested at the edges: an off-by-one here would
    // mislabel individual decisions while leaving the distribution looking identical.
    expect(bandFor(confidence).label).toBe(expected);
  });

  it('honours the thresholds of the manifest that produced the decision', () => {
    // A rollback changes the thresholds. Rendering yesterday's decisions against today's
    // numbers would relabel history, so the pill takes the manifest's values.
    expect(bandFor(0.8, { auto: 0.75, escalateFloor: 0.5 }).label).toBe('auto');
    expect(bandFor(0.8).label).toBe('review');
  });

  it('puts the band in the accessible name', () => {
    render(<ConfidencePill confidence={0.72} />);
    expect(screen.getByLabelText('confidence 72%, review')).toBeInTheDocument();
  });
});

describe('StatBadge', () => {
  it('marks a value that is not a live measurement', () => {
    // Every eval number in this repo is currently offline (BLOCKERS.md B2). A green PASS with
    // no visible marker would be the single most misleading thing in the console.
    render(
      <StatBadge tone="good" mock>
        pass
      </StatBadge>,
    );
    expect(screen.getByLabelText('not a live measurement')).toBeInTheDocument();
  });

  it('does not mark a live one', () => {
    render(<StatBadge tone="good">pass</StatBadge>);
    expect(screen.queryByLabelText('not a live measurement')).not.toBeInTheDocument();
  });
});

describe('RiskTag', () => {
  it('renders a known reason code with its label', () => {
    render(<RiskTag code="duplicate_suspected" />);
    expect(screen.getByText('duplicate')).toBeInTheDocument();
  });

  it('renders an unknown code as itself rather than swallowing it', () => {
    // A new reason code from the agent must show up before the styling catches up. Hiding it
    // would hide what the agent is trying to say.
    render(<RiskTag code="some_new_code" />);
    expect(screen.getByText('some new code')).toBeInTheDocument();
  });

  it('renders nothing when there is no code', () => {
    const { container } = render(<RiskTag code={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('EvidencePanel', () => {
  it('highlights the cited target', () => {
    render(<EvidencePanel evidenceIds={['TXN-0009', 'INV-0009']} targetId="INV-0009" />);
    const chips = screen.getAllByTestId('evidence-chip');
    expect(chips).toHaveLength(2);
    expect(chips[1]).toHaveClass('au-chip--target');
  });

  it('marks an ungrounded citation instead of presenting it as evidence', () => {
    // This state should never occur — enforcement refuses it before persistence. Rendered
    // anyway so that if enforcement is ever bypassed, the console shows the fabrication.
    render(
      <EvidencePanel
        evidenceIds={['TXN-0001', 'INV-9999']}
        targetId="INV-9999"
        ungroundedIds={['INV-9999']}
      />,
    );
    const chips = screen.getAllByTestId('evidence-chip');
    expect(chips[0]).toHaveAttribute('data-grounded', 'true');
    expect(chips[1]).toHaveAttribute('data-grounded', 'false');
  });

  it('explains an empty panel rather than rendering nothing', () => {
    render(<EvidencePanel evidenceIds={[]} />);
    expect(screen.getByTestId('evidence-empty')).toHaveTextContent('check 3');
  });
});

describe('TraceTimeline', () => {
  const spans: TraceSpan[] = [
    { span_id: 's1', name: 'node.load_period', duration_ms: 0.4, attributes: {} },
    { span_id: 's2', name: 'node.route', duration_ms: 0.1, attributes: {} },
    {
      span_id: 's3',
      name: 'decision',
      duration_ms: 1.2,
      attributes: { txn_id: 'TXN-0009', confidence: 0.82, run_id: 'should-be-hidden' },
    },
  ];

  it('renders the spans in the order it is given them', () => {
    // The companion does the ordering — start time, then the agent's monotonic sequence. The
    // component must not re-sort, or it would undo the tie-break that stops two same-tick
    // nodes rendering backwards.
    render(<TraceTimeline spans={spans} />);
    const rows = screen.getAllByTestId('timeline-row');
    expect(rows.map((row) => row.getAttribute('data-span-name'))).toEqual([
      'node.load_period',
      'node.route',
      'decision',
    ]);
  });

  it('highlights the decision being viewed', () => {
    render(<TraceTimeline spans={spans} highlightSpanId="s3" />);
    const rows = screen.getAllByTestId('timeline-row');
    expect(rows[2]).toHaveAttribute('data-highlighted', 'true');
    expect(rows[0]).toHaveAttribute('data-highlighted', 'false');
  });

  it('shows the attributes a reviewer reads and hides the plumbing', () => {
    render(<TraceTimeline spans={spans} />);
    expect(screen.getByText(/txn_id=TXN-0009/)).toBeInTheDocument();
    expect(screen.queryByText(/should-be-hidden/)).not.toBeInTheDocument();
  });

  it('names a check-3 rejection recorded on a span', () => {
    render(
      <TraceTimeline
        spans={[
          {
            span_id: 's9',
            name: 'decision',
            duration_ms: 0.5,
            attributes: { txn_id: 'TXN-0001' },
            events: [
              {
                name: 'phantom_citation',
                attributes: { 'ledgerguard.ungrounded_ids': ['INV-9999'] },
              },
            ],
          },
        ]}
      />,
    );
    expect(screen.getByText(/phantom citation/)).toBeInTheDocument();
    expect(screen.getByText(/INV-9999/)).toBeInTheDocument();
  });

  it('explains an empty timeline', () => {
    render(<TraceTimeline spans={[]} emptyTitle="Tracing is not configured" />);
    expect(screen.getByTestId('timeline-empty')).toHaveTextContent('Tracing is not configured');
  });
});

describe('SyntheticDataBanner', () => {
  it('always says the data is synthetic', () => {
    // Spec 00 A1/A2 and spec 06 §11. A screenshot of this console will end up in a post; the
    // banner is what stops anyone wondering whose books they are looking at.
    render(<SyntheticDataBanner profile="realistic" seed={42} />);
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('All data is synthetic');
  });

  it('names the world so the data is reproducible rather than merely fake', () => {
    render(<SyntheticDataBanner profile="nightmare" seed={7} />);
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('nightmare');
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('seed 7');
  });

  it('still warns when the world is unknown', () => {
    render(<SyntheticDataBanner profile={null} seed={null} />);
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('All data is synthetic');
  });
});
