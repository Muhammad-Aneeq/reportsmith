/**
 * Screen 6 — Month diff. The repeatability demo (spec 13 F7), rendered.
 *
 * The two verdict tiles at the top are the whole argument: **structure identical, numbers
 * changed**. They are not a visual impression — they come from two hashes computed over
 * deliberately disjoint inputs (PLAN.md **D-016**), so each is a claim a test can falsify.
 */

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '../lib/api';
import { Empty, ErrorState, Loading } from '../components/States';

export function MonthDiff() {
  const packs = useQuery({ queryKey: ['packs'], queryFn: api.packs });
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);

  // Default to the two oldest packs — the first two periods run, which is what `make demo`
  // produces and what the launch clip shows.
  useEffect(() => {
    if (packs.data && packs.data.length >= 2 && a === null && b === null) {
      const ordered = [...packs.data].sort((x, y) => x.period.localeCompare(y.period));
      const [first, second] = ordered;
      if (first && second) {
        setA(first.id);
        setB(second.id);
      }
    }
  }, [packs.data, a, b]);

  const diff = useQuery({
    queryKey: ['diff', a, b],
    queryFn: () => api.diff(a!, b!),
    enabled: a !== null && b !== null && a !== b,
  });

  if (packs.isLoading) return <Loading what="packs" />;
  if (packs.isError)
    return <ErrorState error={packs.error} what="packs" onRetry={() => void packs.refetch()} />;

  if ((packs.data?.length ?? 0) < 2)
    return (
      <Empty
        title="Two periods needed"
        detail="The diff compares one period against the next, to show that the structure held while the numbers moved. Assemble a second period and come back."
        action={
          <Link className="rs-btn rs-btn-primary" to="/run">
            Go to Pack run
          </Link>
        }
      />
    );

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Month diff</h2>
          <p>
            Same template, next period. The structure hash covers the template reference and
            each section's key, type and order — no values. The value digest covers the
            figures and nothing about layout. Two hashes, so "identical structure, changed
            numbers" is a testable claim rather than a look.
          </p>
        </div>
        <div className="rs-toolbar">
          <label className="rs-sr-only" htmlFor="pack-a">
            First pack
          </label>
          <select
            id="pack-a"
            className="rs-btn"
            value={a ?? ''}
            onChange={(event) => setA(Number(event.target.value))}
          >
            {packs.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.period} · #{p.id}
              </option>
            ))}
          </select>
          <span aria-hidden>→</span>
          <label className="rs-sr-only" htmlFor="pack-b">
            Second pack
          </label>
          <select
            id="pack-b"
            className="rs-btn"
            value={b ?? ''}
            onChange={(event) => setB(Number(event.target.value))}
          >
            {packs.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.period} · #{p.id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {a === b && (
        <Empty title="Pick two different periods" detail="Comparing a pack with itself proves nothing." />
      )}

      {diff.isLoading && <Loading what="the comparison" rows={4} />}
      {diff.isError && (
        <ErrorState error={diff.error} what="the comparison" onRetry={() => void diff.refetch()} />
      )}

      {diff.data && (
        <>
          <div className="rs-verdict">
            <div className={`rs-verdict-tile${diff.data.structure_identical ? ' is-yes' : ''}`}>
              <h4>Structure</h4>
              <div className="rs-verdict-answer">
                {diff.data.structure_identical ? 'Identical' : 'Changed'}
              </div>
              <p className="rs-hash" style={{ marginTop: 8 }}>
                {diff.data.a.structure_hash.slice(0, 24)}…
              </p>
              <p className="rs-note">
                {diff.data.structure_identical
                  ? 'Every section, its type and its order are the same. The pack was not reassembled by hand.'
                  : 'The template changed between these two runs.'}
              </p>
            </div>

            <div className={`rs-verdict-tile${diff.data.values_differ ? ' is-yes' : ''}`}>
              <h4>Numbers</h4>
              <div className="rs-verdict-answer">
                {diff.data.values_differ ? 'Changed' : 'Identical'}
              </div>
              <p className="rs-hash" style={{ marginTop: 8 }}>
                {diff.data.a.value_digest.slice(0, 12)}… → {diff.data.b.value_digest.slice(0, 12)}…
              </p>
              <p className="rs-note">
                {diff.data.values_differ
                  ? 'New period, new figures — assembled from live data, not copied forward.'
                  : 'The figures did not move, which for two different periods would be suspicious.'}
              </p>
            </div>

            <div className="rs-verdict-tile">
              <h4>Template</h4>
              <div className="rs-verdict-answer" style={{ fontSize: 15 }}>
                <code>{diff.data.a.template_ref}</code>
              </div>
              <p className="rs-note" style={{ marginTop: 8 }}>
                {diff.data.a.period} → {diff.data.b.period}. Defined once; run twice.
              </p>
            </div>
          </div>

          <div className="rs-card">
            <div className="rs-card-head">
              <div>
                <h3>Section by section</h3>
                <p className="rs-card-sub">
                  A marked left edge means this section's figures moved.
                </p>
              </div>
            </div>

            {diff.data.sections.map((section) => (
              <div
                key={section.section_key}
                className={`rs-card${section.values_changed ? ' rs-diffrow-changed' : ''}`}
                style={{ marginTop: 12 }}
              >
                <div className="rs-card-head">
                  <div>
                    <h3 style={{ fontSize: 15 }}>{section.title}</h3>
                    <p className="rs-card-sub">
                      <code>{section.type}</code>
                    </p>
                  </div>
                  <div className="rs-toolbar">
                    {section.structure_same ? (
                      <span className="rs-badge rs-badge-emerald">
                        <span aria-hidden>✓</span>same structure
                      </span>
                    ) : (
                      <span className="rs-badge rs-badge-rose">
                        <span aria-hidden>✕</span>structure differs
                      </span>
                    )}
                    {section.values_changed && (
                      <span className="rs-badge rs-badge-amber">
                        <span aria-hidden>Δ</span>numbers moved
                      </span>
                    )}
                  </div>
                </div>

                <div className="rs-diffgrid">
                  {[
                    { side: section.a, period: diff.data!.a.period },
                    { side: section.b, period: diff.data!.b.period },
                  ].map(({ side, period }) => (
                    <div className="rs-diffside" key={period}>
                      <div className="rs-note" style={{ marginBottom: 8 }}>
                        {period}
                      </div>
                      {!side ? (
                        <em>absent from this pack</em>
                      ) : side.gap ? (
                        <span className="rs-badge rs-badge-amber">
                          <span aria-hidden>▲</span>gap
                        </span>
                      ) : (
                        <dl style={{ margin: 0 }}>
                          {side.summary.map((row, i) => (
                            <div key={i}>
                              <dt>{row.label}</dt>
                              <dd>{row.display}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
