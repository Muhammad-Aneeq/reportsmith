/**
 * Status signalling: colour **plus** an icon **plus** text. Never colour alone.
 *
 * That is the accessibility floor, and it is also just better design — a reviewer scanning
 * eleven sections should be able to tell approved from gapped in peripheral vision, and a
 * screenshot should survive being printed in greyscale.
 */

import type { PackStatus } from '../lib/api';

const PACK_STATUS: Record<PackStatus, { label: string; tone: string; glyph: string; hint: string }> = {
  draft: { label: 'Draft', tone: 'slate', glyph: '◌', hint: 'Assembled; not yet under review' },
  in_review: { label: 'In review', tone: 'amber', glyph: '◑', hint: 'Sections are being approved' },
  signed: { label: 'Signed', tone: 'emerald', glyph: '◕', hint: 'Signed off; issuing' },
  issued: { label: 'Issued', tone: 'emerald', glyph: '●', hint: 'Archived and immutable' },
};

export function PackStatusBadge({ status }: { status: PackStatus }) {
  const meta = PACK_STATUS[status];
  return (
    <span className={`rs-badge rs-badge-${meta.tone}`} title={meta.hint}>
      <span aria-hidden>{meta.glyph}</span>
      {meta.label}
    </span>
  );
}

export function SectionStateBadge({
  approved,
  gap,
  edited,
}: {
  approved: boolean;
  gap: boolean;
  edited: boolean;
}) {
  // Order matters: a gap outranks an approval in what a reviewer needs to see first.
  if (gap) {
    return (
      <span className="rs-badge rs-badge-amber" title="This binding did not resolve">
        <span aria-hidden>▲</span>Gap
      </span>
    );
  }
  if (approved) {
    return (
      <span className="rs-badge rs-badge-emerald" title="Approved by a reviewer">
        <span aria-hidden>✓</span>Approved
      </span>
    );
  }
  return (
    <span className="rs-badge rs-badge-slate" title={edited ? 'Edited since approval' : 'Not yet approved'}>
      <span aria-hidden>○</span>
      {edited ? 'Edited' : 'Unapproved'}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === 'high' ? 'rose' : severity === 'medium' ? 'amber' : 'slate';
  const glyph = severity === 'high' ? '▲' : severity === 'medium' ? '◆' : '•';
  return (
    <span className={`rs-badge rs-badge-${tone}`}>
      <span aria-hidden>{glyph}</span>
      {severity}
    </span>
  );
}

export function VerifiedBadge({ verified, checked }: { verified: boolean; checked: number }) {
  if (checked === 0) {
    // Not a pass. Prose with no figures cannot state a wrong one, and saying "verified"
    // here would be technically true and materially misleading.
    return (
      <span className="rs-badge rs-badge-slate" title="This draft states no figures">
        <span aria-hidden>–</span>no figures
      </span>
    );
  }
  return verified ? (
    <span
      className="rs-badge rs-badge-emerald"
      title={`All ${checked} figure(s) matched the bound data`}
    >
      <span aria-hidden>✓</span>
      {checked} figures verified
    </span>
  ) : (
    <span className="rs-badge rs-badge-rose" title="A figure did not match the bound data">
      <span aria-hidden>✕</span>unverified
    </span>
  );
}

export function Trend({
  direction,
  sentiment,
  display,
}: {
  direction?: 'up' | 'down' | 'flat';
  sentiment?: 'good' | 'bad' | 'neutral';
  display?: string;
}) {
  if (!display) return null;
  const arrow = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '–';
  // Colour comes from sentiment, never from the arrow: payables rising is not good news,
  // and the template is what says which way is better.
  return (
    <span className={`rs-trend rs-trend-${sentiment ?? 'neutral'}`}>
      <span aria-hidden>{arrow}</span>
      {display}
    </span>
  );
}
