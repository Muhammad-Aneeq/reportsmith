/**
 * Renders one assembled section, of whichever of the four types it is.
 *
 * A gapped section renders as a **gap**, never as an empty table. Those are different facts
 * — "the binding did not resolve" and "there were no rows" — and a reader who cannot tell
 * them apart cannot review the pack.
 */

import type { FlagItem, Kpi, Section, TableContent } from '../lib/api';
import { SeverityBadge, Trend, VerifiedBadge } from './Status';

export function GapNotice({
  gaps,
  required,
}: {
  gaps: { reason: string; detail: string; source: string; dataset: string }[];
  required: boolean;
}) {
  return (
    <>
      {gaps.map((gap, i) => (
        <div className="rs-gap" key={i}>
          <div className="rs-gap-head">
            <span className="rs-badge rs-badge-amber">
              <span aria-hidden>▲</span>Not available
            </span>
            <code>{gap.reason}</code>
            {required && (
              <span className="rs-badge rs-badge-rose">
                <span aria-hidden>✕</span>blocks issuance
              </span>
            )}
          </div>
          <p className="rs-gap-detail">{gap.detail}</p>
          <p className="rs-note">
            Source <code>{gap.source}</code> · dataset <code>{gap.dataset}</code>
          </p>
        </div>
      ))}
      {required && (
        <p className="rs-note">
          This section is marked required, so the pack cannot be issued until the gap is
          resolved or a reviewer records a waiver explaining why it is going out without it.
        </p>
      )}
    </>
  );
}

function TableView({ content }: { content: TableContent }) {
  return (
    <>
      <div className="rs-table-wrap">
        <table className="rs-table">
          <thead>
            <tr>
              {content.columns.map((column) => (
                <th key={column.field} className={column.align === 'right' ? 'rs-right' : ''}>
                  {column.label || ' '}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {content.rows.map((row, i) => (
              <tr key={i}>
                {content.columns.map((column) => (
                  <td key={column.field} className={column.align === 'right' ? 'rs-right' : ''}>
                    {row[column.field]?.display ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {content.total && (
            <tfoot>
              <tr>
                {content.columns.map((column) => (
                  <td key={column.field} className={column.align === 'right' ? 'rs-right' : ''}>
                    {content.total?.[column.field]?.display ?? ''}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {/* Never let a truncated table read as "this is everything". */}
      {content.truncated_from ? (
        <p className="rs-note">
          Showing {content.row_count} of {content.truncated_from} rows, as the template's
          <code> limit</code> requires.
        </p>
      ) : null}
    </>
  );
}

function KpiView({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="rs-kpi-grid">
      {kpis.map((kpi) => (
        <div key={kpi.id} className={`rs-kpi${kpi.missing ? ' is-missing' : ''}`}>
          <div className="rs-kpi-label">{kpi.label}</div>
          <div className="rs-kpi-value">{kpi.missing ? 'unavailable' : kpi.display}</div>
          <div className="rs-kpi-foot">
            {kpi.missing ? (
              <span>{kpi.note}</span>
            ) : (
              <>
                <Trend
                  direction={kpi.direction}
                  sentiment={kpi.sentiment}
                  display={kpi.delta_display}
                />
                {kpi.prior_display && kpi.prior_display !== 'n/a' && (
                  <span>from {kpi.prior_display}</span>
                )}
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function FlagsView({ items }: { items: FlagItem[] }) {
  if (items.length === 0) {
    // A good month is information. It must not look like a rendering failure.
    return (
      <p className="rs-prose" style={{ color: 'var(--aurora-text-dim)' }}>
        Nothing was flagged this period. Every rule ran; none fired.
      </p>
    );
  }
  return (
    <ul className="rs-list-reset" style={{ display: 'grid', gap: 10 }}>
      {items.map((item) => (
        <li key={`${item.rule_id}-${item.reference ?? ''}`} className="rs-card" style={{ padding: '13px 15px' }}>
          <div className="rs-gap-head">
            <SeverityBadge severity={item.severity} />
            <strong>{item.label}</strong>
            {item.amount_display && <span className="rs-num">{item.amount_display}</span>}
          </div>
          <p className="rs-gap-detail">{item.message}</p>
          {item.evidence && <p className="rs-note">Evidence — {item.evidence}</p>}
        </li>
      ))}
    </ul>
  );
}

export function NarrativeView({ section }: { section: Section }) {
  const content = section.content;
  return (
    <>
      <div className="rs-card-head">
        <VerifiedBadge
          verified={Boolean(content.verified)}
          checked={content.figures_checked ?? 0}
        />
        {content.retried && (
          <span className="rs-badge rs-badge-amber" title="The first draft stated a figure the data did not support">
            <span aria-hidden>↺</span>re-drafted
          </span>
        )}
        {section.has_human_edits && (
          <span className="rs-badge rs-badge-slate">
            <span aria-hidden>✎</span>
            {section.edit_count} human edit{section.edit_count === 1 ? '' : 's'}
          </span>
        )}
      </div>

      <p className="rs-prose">{content.text || <em>Not drafted.</em>}</p>

      {content.dropped_sentences && content.dropped_sentences.length > 0 && (
        <div className="rs-gap" style={{ marginTop: 14 }}>
          <div className="rs-gap-head">
            <span className="rs-badge rs-badge-amber">
              <span aria-hidden>✂</span>
              {content.dropped_sentences.length} sentence(s) removed
            </span>
          </div>
          <p className="rs-gap-detail">
            These stated a figure that no bound value supported, and did not survive the
            numeric cross-check:
          </p>
          <ul className="rs-list-reset rs-note">
            {content.dropped_sentences.map((sentence, i) => (
              <li key={i}>“{sentence}”</li>
            ))}
          </ul>
        </div>
      )}

      {content.violations && content.violations.length > 0 && (
        <p className="rs-note">
          Tone linter:{' '}
          {content.violations
            .map((v) => `${v.rule}${v.fixed ? ' (fixed)' : ''}`)
            .join(' · ')}
        </p>
      )}
    </>
  );
}

export function SectionView({ section }: { section: Section }) {
  if (section.gaps.length > 0) {
    return <GapNotice gaps={section.gaps} required={section.required} />;
  }
  switch (section.type) {
    case 'table':
      return <TableView content={section.content as TableContent} />;
    case 'kpi_grid':
      return <KpiView kpis={section.content.kpis ?? []} />;
    case 'flags':
      return <FlagsView items={section.content.items ?? []} />;
    case 'narrative':
      return <NarrativeView section={section} />;
  }
}
