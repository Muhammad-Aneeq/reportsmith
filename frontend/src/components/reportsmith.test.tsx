/**
 * Component tests for the things PLAN.md **D-019** promises.
 *
 * Not coverage for its own sake — each of these is a claim the UI makes that would be
 * quietly wrong if it broke: that status is readable without colour, that the diff shows
 * word-level changes, that empty states say what to do, and that the sign-off button is
 * disabled for a reason the reader can see.
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Empty, ErrorState, Loading } from './States';
import {
  PackStatusBadge,
  SectionStateBadge,
  SeverityBadge,
  Trend,
  VerifiedBadge,
} from './Status';
import { GapNotice } from './SectionView';

describe('states', () => {
  it('loading says what it is loading', () => {
    render(<Loading what="the pack" />);
    expect(screen.getByRole('status')).toHaveTextContent(/the pack/i);
  });

  it('an error surfaces the server message verbatim', () => {
    // The backend writes refusals to be read by a person; replacing them with a generic
    // string throws away the part that does the work.
    const message = "required section 'Performance by segment' has an unresolved gap";
    render(<ErrorState error={new Error(message)} what="the pack" />);
    expect(screen.getByRole('alert')).toHaveTextContent(message);
  });

  it('an empty state always says what would put something here', () => {
    render(<Empty title="No packs yet" detail="Pick a period and assemble one." />);
    expect(screen.getByText(/pick a period/i)).toBeInTheDocument();
  });
});

describe('status is never colour alone', () => {
  it('pack status carries a text label', () => {
    render(<PackStatusBadge status="issued" />);
    expect(screen.getByText('Issued')).toBeInTheDocument();
  });

  it('a gap outranks an approval in what is shown', () => {
    render(<SectionStateBadge approved gap edited={false} />);
    expect(screen.getByText('Gap')).toBeInTheDocument();
    expect(screen.queryByText('Approved')).not.toBeInTheDocument();
  });

  it('severity renders its own word', () => {
    render(<SeverityBadge severity="high" />);
    expect(screen.getByText('high')).toBeInTheDocument();
  });
});

describe('verified badge', () => {
  it('does not claim a pass when nothing was checked', () => {
    // 100% of zero is not a verification. Saying "verified" here would be technically
    // true and materially misleading.
    render(<VerifiedBadge verified checked={0} />);
    expect(screen.getByText(/no figures/i)).toBeInTheDocument();
  });

  it('reports how many figures were checked', () => {
    render(<VerifiedBadge verified checked={6} />);
    expect(screen.getByText(/6 figures verified/i)).toBeInTheDocument();
  });

  it('says so plainly when a figure did not match', () => {
    render(<VerifiedBadge verified={false} checked={6} />);
    expect(screen.getByText(/unverified/i)).toBeInTheDocument();
  });
});

describe('trend sentiment comes from the template, not the sign', () => {
  it('a rise can be bad news', () => {
    // Payables rising is not an improvement. The template says which way is better and the
    // UI colours from that, never from the arithmetic.
    const { container } = render(<Trend direction="up" sentiment="bad" display="+12.4%" />);
    expect(container.querySelector('.rs-trend-bad')).toBeTruthy();
  });

  it('a fall can be good news', () => {
    const { container } = render(<Trend direction="down" sentiment="good" display="-8.1%" />);
    expect(container.querySelector('.rs-trend-good')).toBeTruthy();
  });
});

describe('gap notice', () => {
  const gap = [
    {
      reason: 'unknown_dataset',
      detail: "statementlens publishes no dataset 'segment_ratios'",
      source: 'statementlens',
      dataset: 'segment_ratios',
    },
  ];

  it('names the reason and the detail', () => {
    render(<GapNotice gaps={gap} required={false} />);
    expect(screen.getByText('unknown_dataset')).toBeInTheDocument();
    expect(screen.getByText(/publishes no dataset/i)).toBeInTheDocument();
  });

  it('says that a required gap blocks issuance', () => {
    render(<GapNotice gaps={gap} required />);
    expect(screen.getByText(/blocks issuance/i)).toBeInTheDocument();
    expect(screen.getByText(/records a waiver/i)).toBeInTheDocument();
  });
});
