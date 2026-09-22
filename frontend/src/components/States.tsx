/**
 * Loading, empty and error — the three states every screen has to have.
 *
 * They live in one file because the bar in PLAN.md **D-019** is "no screen ships with a
 * spinner-forever, a dead blank page, or a raw JSON dump", and the cheapest way to hold a
 * bar like that is to make the compliant thing the convenient thing.
 *
 * Each says what *this* screen was doing, not "Loading…". A skeleton is shaped like the
 * content it is replacing, so the layout does not jump when data arrives.
 */

import type { ReactNode } from 'react';

export function Loading({ what, rows = 3 }: { what: string; rows?: number }) {
  return (
    <div className="rs-loading" role="status" aria-live="polite">
      <span className="rs-sr-only">Loading {what}</span>
      <div className="rs-skeleton-head" aria-hidden />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="rs-skeleton-row" aria-hidden style={{ opacity: 1 - i * 0.18 }} />
      ))}
      <p className="rs-loading-label" aria-hidden>
        Loading {what}…
      </p>
    </div>
  );
}

export function ErrorState({
  error,
  what,
  onRetry,
}: {
  error: unknown;
  what: string;
  onRetry?: () => void;
}) {
  // The server's own message, verbatim. See lib/api.ts on why.
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="rs-error" role="alert">
      <div className="rs-error-mark" aria-hidden>
        !
      </div>
      <div className="rs-error-body">
        <h3>Could not load {what}</h3>
        <p className="rs-error-message">{message}</p>
        {onRetry && (
          <button type="button" className="rs-btn rs-btn-quiet" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Empty({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="rs-empty">
      <div className="rs-empty-mark" aria-hidden />
      <h3>{title}</h3>
      {/* An empty state that only says "nothing here" leaves the reader stuck. This one
          always says what would put something here. */}
      <p>{detail}</p>
      {action}
    </div>
  );
}
