/**
 * The `/aurora` demo route — spec 00 A2's stated acceptance criterion:
 * *"Storybook (or a demo route) renders every component."*
 *
 * All nine on one page. If a token drifts, or a theme is only half-designed, this is the
 * screen where it shows — which is why it is linked from the footer rather than hidden.
 */

import {
  Card,
  ConfidencePill,
  EmptyState,
  EvidencePanel,
  MetricTile,
  RiskTag,
  StatBadge,
  SyntheticDataBanner,
  TraceTimeline,
} from '../components/aurora';

const SPANS = [
  { span_id: '1', name: 'draft', duration_ms: 412, attributes: { sentences: 4 } },
  { span_id: '2', name: 'numcheck', duration_ms: 3, attributes: { figures_checked: 6 } },
  { span_id: '3', name: 'lint', duration_ms: 2, attributes: { fixed: 'currency.negative' } },
  { span_id: '4', name: 'reverify', duration_ms: 3, attributes: { verdict: 'unchanged' } },
];

export function AuroraRoute() {
  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>aurora</h2>
          <p>
            The shared design system (spec 00 A2), implemented locally under{' '}
            <code>src/components/aurora/</code> because no published package exists. All nine
            components render below — that is the spec's acceptance criterion. Use the theme
            toggle in the header to check both modes.
          </p>
        </div>
      </div>

      <div className="rs-card">
        <div className="rs-card-head">
          <h3>Surfaces</h3>
        </div>
        <div
          style={{
            display: 'grid',
            gap: 14,
            gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
          }}
        >
          <Card title="Card" subtitle="frosted surface">
            A hairline border does the edge work, not a heavy shadow.
          </Card>
          <MetricTile label="Revenue" value="£3,815,071" hint="+2.9% on prior month" tone="accent" />
          <MetricTile label="Operating profit" value="(£57,087)" hint="down from £4,747" tone="bad" />
          <MetricTile label="Payables exceptions" value="17" hint="to chase" tone="warn" />
        </div>

        <div style={{ marginTop: 16 }}>
          <EmptyState
            title="EmptyState"
            hint="Always says what would put something here — never just 'nothing found'."
          />
        </div>

        <div style={{ marginTop: 16 }}>
          <SyntheticDataBanner profile="squeeze" seed={42} />
        </div>
      </div>

      <div className="rs-card">
        <div className="rs-card-head">
          <h3>Indicators</h3>
          <p className="rs-card-sub">
            Each carries a text label as well as a colour, so nothing here signals by hue alone.
          </p>
        </div>
        <div className="rs-toolbar">
          <StatBadge>11 sections</StatBadge>
          <StatBadge tone="warn">1 gap</StatBadge>
          <StatBadge tone="good">2 issued</StatBadge>
          <StatBadge tone="good" mock>
            mock LLM
          </StatBadge>
          <ConfidencePill confidence={0.94} />
          <ConfidencePill confidence={0.62} />
          <ConfidencePill confidence={0.21} />
          <RiskTag code="duplicate" />
          <RiskTag code="dispute" />
          <RiskTag code="timing" />
        </div>
      </div>

      <div className="rs-card">
        <div className="rs-card-head">
          <h3>Evidence</h3>
          <p className="rs-card-sub">
            In this product the evidence is the figure refs a narrative section was allowed to
            cite, and the pipeline that checked them.
          </p>
        </div>
        <EvidencePanel
          evidenceIds={['revenue.amount', 'gross_profit.amount', 'cogs.amount']}
          targetId="revenue.amount"
          emptyHint="No figures were bound to this section."
        />
        <div style={{ marginTop: 16 }}>
          <TraceTimeline spans={SPANS} highlightSpanId="2" />
        </div>
      </div>
    </>
  );
}
