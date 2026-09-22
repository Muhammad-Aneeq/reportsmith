/**
 * Screen 2 — Pack Run: binding status per section, the gaps panel, and the assembled pack.
 *
 * Spec 13 §9. The gaps panel is not a footnote here; it sits above the content, because a
 * reviewer's first question about a freshly assembled pack is "what is missing".
 */

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '../lib/api';
import { Empty, ErrorState, Loading } from '../components/States';
import { PackStatusBadge, SectionStateBadge } from '../components/Status';
import { SectionView } from '../components/SectionView';

export function PackRun() {
  const queryClient = useQueryClient();
  const [packId, setPackId] = useState<number | null>(null);
  const [period, setPeriod] = useState<string>('');

  const periods = useQuery({ queryKey: ['periods'], queryFn: api.periods });
  const packs = useQuery({ queryKey: ['packs'], queryFn: api.packs });

  const selectedId = packId ?? packs.data?.[0]?.id ?? null;
  const pack = useQuery({
    queryKey: ['pack', selectedId],
    queryFn: () => api.pack(selectedId!),
    enabled: selectedId !== null,
  });

  const run = useMutation({
    mutationFn: (p: string) => api.createPack('monthly_management_pack', p),
    onSuccess: (created) => {
      setPackId(created.id);
      void queryClient.invalidateQueries({ queryKey: ['packs'] });
      void queryClient.invalidateQueries({ queryKey: ['archive'] });
    },
  });

  const defaultPeriod = period || periods.data?.default || '';
  const alreadyRun = useMemo(
    () => new Set((packs.data ?? []).map((p) => p.period)),
    [packs.data],
  );

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Run a period</h2>
          <p>
            The template is already defined. Choose a period and assemble it: tables and KPIs
            are computed from the bound data, narrative sections are drafted from that
            section's figures only, and anything that could not bind is reported rather than
            quietly dropped.
          </p>
        </div>
        <div className="rs-toolbar">
          <label className="rs-sr-only" htmlFor="period">
            Period
          </label>
          <select
            id="period"
            className="rs-btn"
            value={defaultPeriod}
            onChange={(event) => setPeriod(event.target.value)}
            disabled={periods.isLoading}
          >
            {(periods.data?.periods ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {alreadyRun.has(p.id) ? ' · already run' : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rs-btn rs-btn-primary"
            onClick={() => run.mutate(defaultPeriod)}
            disabled={!defaultPeriod || run.isPending}
          >
            {run.isPending ? 'Assembling…' : 'Assemble pack'}
          </button>
        </div>
      </div>

      {run.isError && <ErrorState error={run.error} what="the pack run" />}

      {packs.isLoading && <Loading what="previous runs" />}
      {packs.isError && (
        <ErrorState error={packs.error} what="previous runs" onRetry={() => void packs.refetch()} />
      )}

      {packs.data?.length === 0 && !run.isPending && (
        <Empty
          title="No packs yet"
          detail="Pick a period above and assemble one. The default Monthly Management Pack is already installed, so there is nothing to configure first."
          action={
            <button
              type="button"
              className="rs-btn rs-btn-primary"
              onClick={() => run.mutate(defaultPeriod)}
              disabled={!defaultPeriod}
            >
              Assemble {defaultPeriod}
            </button>
          }
        />
      )}

      {selectedId !== null && (
        <>
          {(packs.data?.length ?? 0) > 1 && (
            <div className="rs-toolbar" style={{ marginBottom: 16 }}>
              {packs.data?.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`rs-btn rs-btn-sm${p.id === selectedId ? ' rs-btn-primary' : ''}`}
                  onClick={() => setPackId(p.id)}
                >
                  {p.period} · #{p.id}
                </button>
              ))}
            </div>
          )}

          {pack.isLoading && <Loading what="the pack" rows={5} />}
          {pack.isError && (
            <ErrorState error={pack.error} what="the pack" onRetry={() => void pack.refetch()} />
          )}

          {pack.data && (
            <>
              <div className="rs-card">
                <div className="rs-card-head">
                  <div>
                    <h3>
                      {pack.data.cover.title} · {pack.data.period}
                    </h3>
                    <p className="rs-card-sub">
                      Template <code>{pack.data.template_ref}</code> · {pack.data.cover.section_count}{' '}
                      sections · drafted by <code>{pack.data.model}</code>
                    </p>
                  </div>
                  <div className="rs-toolbar">
                    <PackStatusBadge status={pack.data.status} />
                    <Link className="rs-btn rs-btn-sm" to={`/review/${pack.data.id}`}>
                      Review →
                    </Link>
                  </div>
                </div>

                <div className="rs-table-wrap">
                  <table className="rs-table">
                    <thead>
                      <tr>
                        <th>Section</th>
                        <th>Type</th>
                        <th>Source</th>
                        <th>Binding</th>
                        <th>State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pack.data.sections.map((section) => (
                        <tr key={section.id}>
                          <td>
                            {section.title}
                            {section.required && (
                              <span className="rs-note" style={{ marginLeft: 6 }}>
                                required
                              </span>
                            )}
                          </td>
                          <td>
                            <code>{section.type}</code>
                          </td>
                          <td>
                            <code>{section.content.source ?? section.gaps[0]?.source ?? '—'}</code>
                          </td>
                          <td>
                            {section.binding_status === 'bound' ? (
                              <span className="rs-badge rs-badge-emerald">
                                <span aria-hidden>✓</span>bound
                              </span>
                            ) : (
                              <span className="rs-badge rs-badge-amber">
                                <span aria-hidden>▲</span>gap
                              </span>
                            )}
                          </td>
                          <td>
                            <SectionStateBadge
                              approved={section.approved}
                              gap={section.gaps.length > 0}
                              edited={section.has_human_edits}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rs-card">
                <div className="rs-card-head">
                  <div>
                    <h3>Gaps</h3>
                    <p className="rs-card-sub">
                      Every binding that did not resolve. Required ones block issuance until
                      resolved or waived.
                    </p>
                  </div>
                  <span
                    className={`rs-badge ${pack.data.gaps.length ? 'rs-badge-amber' : 'rs-badge-emerald'}`}
                  >
                    <span aria-hidden>{pack.data.gaps.length ? '▲' : '✓'}</span>
                    {pack.data.gaps.length} gap{pack.data.gaps.length === 1 ? '' : 's'}
                  </span>
                </div>

                {pack.data.gaps.length === 0 ? (
                  <p className="rs-prose" style={{ color: 'var(--aurora-text-dim)' }}>
                    Every section bound to live data.
                  </p>
                ) : (
                  pack.data.gaps.map((gap) => (
                    <div className="rs-gap" key={gap.section_key}>
                      <div className="rs-gap-head">
                        <strong>{gap.title}</strong>
                        <code>{gap.reason}</code>
                        {gap.required && (
                          <span className="rs-badge rs-badge-rose">
                            <span aria-hidden>✕</span>blocks issuance
                          </span>
                        )}
                      </div>
                      <p className="rs-gap-detail">{gap.detail}</p>
                    </div>
                  ))
                )}
              </div>

              {pack.data.sections.map((section) => (
                <div className="rs-card" key={section.id}>
                  <div className="rs-card-head">
                    <div>
                      <h3>{section.title}</h3>
                      <p className="rs-card-sub">
                        <code>{section.type}</code>
                        {section.content.schema_version ? (
                          <> · schema <code>{section.content.schema_version}</code></>
                        ) : null}
                      </p>
                    </div>
                    <SectionStateBadge
                      approved={section.approved}
                      gap={section.gaps.length > 0}
                      edited={section.has_human_edits}
                    />
                  </div>
                  <SectionView section={section} />
                </div>
              ))}
            </>
          )}
        </>
      )}
    </>
  );
}
