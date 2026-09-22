/**
 * Screen 4 — Sign-off: the checklist, the waiver flow, and the button that issues.
 *
 * The checklist mirrors the server's guards rather than re-implementing them. Everything it
 * shows comes from `pack.blockers`, which is `check_guards()` output — so the screen cannot
 * drift into permitting something the API would refuse, or into refusing something it would
 * allow. The button being disabled is a courtesy; the guard is the control.
 */

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { api } from '../lib/api';
import { Empty, ErrorState, Loading } from '../components/States';
import { PackStatusBadge } from '../components/Status';

export function SignOff() {
  const params = useParams();
  const queryClient = useQueryClient();

  const packs = useQuery({ queryKey: ['packs'], queryFn: api.packs });
  const packId = params.packId ? Number(params.packId) : (packs.data?.[0]?.id ?? null);
  const pack = useQuery({
    queryKey: ['pack', packId],
    queryFn: () => api.pack(packId!),
    enabled: packId !== null,
  });

  const [signer, setSigner] = useState('A. Controller');
  const [waivers, setWaivers] = useState<Record<string, string>>({});

  const sign = useMutation({
    mutationFn: () =>
      api.signoff(
        packId!,
        signer,
        Object.entries(waivers)
          .filter(([, reason]) => reason.trim())
          .map(([section_key, reason]) => ({ section_key, reason: reason.trim() })),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pack', packId] });
      void queryClient.invalidateQueries({ queryKey: ['packs'] });
      void queryClient.invalidateQueries({ queryKey: ['archive'] });
    },
  });

  const reopen = useMutation({
    mutationFn: () => api.reopen(packId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pack', packId] });
      void queryClient.invalidateQueries({ queryKey: ['packs'] });
    },
  });

  const requiredGaps = useMemo(
    () => (pack.data?.gaps ?? []).filter((gap) => gap.required),
    [pack.data],
  );
  const unapproved = useMemo(
    () => (pack.data?.sections ?? []).filter((s) => !s.approved),
    [pack.data],
  );
  const allGapsWaived = requiredGaps.every((gap) => (waivers[gap.section_key] ?? '').trim());
  const ready = unapproved.length === 0 && allGapsWaived && pack.data?.status === 'in_review';

  if (packs.isLoading) return <Loading what="packs" />;
  if (packs.data?.length === 0)
    return (
      <Empty
        title="Nothing to sign"
        detail="No pack has been assembled yet. Assemble one, review it, and this is where it gets signed and issued."
        action={
          <Link className="rs-btn rs-btn-primary" to="/run">
            Go to Pack run
          </Link>
        }
      />
    );
  if (pack.isLoading) return <Loading what="the pack" rows={4} />;
  if (pack.isError)
    return <ErrorState error={pack.error} what="the pack" onRetry={() => void pack.refetch()} />;
  if (!pack.data) return null;

  const issued = pack.data.status === 'issued';

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Sign-off · {pack.data.period}</h2>
          <p>
            Nothing is issued without a person. Every section approved, every unresolved gap
            either fixed or explicitly waived with a recorded reason — then the pack is
            archived with a hash covering the document, the data snapshot and the template
            version.
          </p>
        </div>
        <PackStatusBadge status={pack.data.status} />
      </div>

      {issued ? (
        <div className="rs-card">
          <div className="rs-card-head">
            <div>
              <h3>Issued</h3>
              <p className="rs-card-sub">
                Signed by <strong>{pack.data.signoff?.signer}</strong> on{' '}
                {new Date(pack.data.signoff?.at ?? '').toLocaleString()}
              </p>
            </div>
            <Link className="rs-btn rs-btn-sm" to="/archive">
              Open archive →
            </Link>
          </div>
          <p className="rs-hash">content hash {pack.data.archive?.content_hash}</p>
          {(pack.data.signoff?.waivers.length ?? 0) > 0 && (
            <>
              <h4 style={{ marginTop: 16, fontSize: 14 }}>Waivers recorded</h4>
              {pack.data.signoff?.waivers.map((waiver) => (
                <div className="rs-gap" key={waiver.section_key}>
                  <div className="rs-gap-head">
                    <strong>{waiver.section_key}</strong>
                    <span className="rs-badge rs-badge-slate">{waiver.signer}</span>
                  </div>
                  <p className="rs-gap-detail">{waiver.reason}</p>
                </div>
              ))}
            </>
          )}
          <div className="rs-toolbar" style={{ marginTop: 16 }}>
            <span className="rs-note">
              Issued packs are immutable. Re-issuing is refused, and the archive verifier
              detects any change to the files on disk.
            </span>
          </div>
        </div>
      ) : (
        <>
          <div className="rs-card">
            <div className="rs-card-head">
              <h3>Checklist</h3>
              <span className="rs-badge rs-badge-slate">
                {pack.data.approved_count}/{pack.data.sections.length} sections approved
              </span>
            </div>

            <div className={`rs-check ${unapproved.length === 0 ? 'is-ok' : 'is-blocked'}`}>
              <span className="rs-check-mark" aria-hidden>
                {unapproved.length === 0 ? '✓' : '!'}
              </span>
              <div className="rs-check-body">
                <h4>All sections approved</h4>
                <p>
                  {unapproved.length === 0
                    ? 'Every section has been approved by a reviewer.'
                    : `${unapproved.length} still to approve: ${unapproved.map((s) => s.title).join(', ')}.`}
                </p>
                {unapproved.length > 0 && (
                  <Link className="rs-btn rs-btn-sm" to={`/review/${pack.data.id}`} style={{ marginTop: 10 }}>
                    Go to review
                  </Link>
                )}
              </div>
            </div>

            <div className={`rs-check ${allGapsWaived ? 'is-ok' : 'is-blocked'}`}>
              <span className="rs-check-mark" aria-hidden>
                {allGapsWaived ? '✓' : '!'}
              </span>
              <div className="rs-check-body">
                <h4>Gaps resolved or waived</h4>
                {requiredGaps.length === 0 ? (
                  <p>No required section has an unresolved gap.</p>
                ) : (
                  <>
                    <p>
                      {requiredGaps.length} required section(s) could not bind. Issuing anyway
                      needs a reason, and the reason is recorded in the archive under your name.
                    </p>
                    {requiredGaps.map((gap) => (
                      <div key={gap.section_key} style={{ marginTop: 12 }}>
                        <div className="rs-gap-head">
                          <strong>{gap.title}</strong>
                          <code>{gap.reason}</code>
                        </div>
                        <p className="rs-gap-detail">{gap.detail}</p>
                        <label className="rs-sr-only" htmlFor={`waiver-${gap.section_key}`}>
                          Waiver reason for {gap.title}
                        </label>
                        <input
                          id={`waiver-${gap.section_key}`}
                          className="rs-waiver"
                          placeholder="Why is this pack being issued without this section?"
                          value={waivers[gap.section_key] ?? ''}
                          onChange={(event) =>
                            setWaivers((current) => ({
                              ...current,
                              [gap.section_key]: event.target.value,
                            }))
                          }
                        />
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="rs-card">
            <div className="rs-card-head">
              <div>
                <h3>Sign and issue</h3>
                <p className="rs-card-sub">
                  Writes the markdown, the PDF and the data snapshot, then records a hash over
                  all of it plus the template version.
                </p>
              </div>
            </div>

            {sign.isError && <ErrorState error={sign.error} what="the sign-off" />}
            {pack.data.blockers.length > 0 && (
              <ul className="rs-list-reset" style={{ marginBottom: 14 }}>
                {/* Keyed on code AND message: a pack with three unresolved gaps produces
                    three blockers that all share the code `gap_unresolved`, and React
                    silently collapses same-keyed siblings — so the reviewer would have
                    seen one blocker and believed they had one problem. */}
                {pack.data.blockers.map((blocker) => (
                  <li key={`${blocker.code}:${blocker.message}`} className="rs-note">
                    <code>{blocker.code}</code> — {blocker.message}
                  </li>
                ))}
              </ul>
            )}

            <div className="rs-toolbar">
              <label className="rs-sr-only" htmlFor="signer">
                Signer
              </label>
              <input
                id="signer"
                className="rs-waiver"
                style={{ maxWidth: 260, marginTop: 0 }}
                value={signer}
                onChange={(event) => setSigner(event.target.value)}
              />
              <button
                type="button"
                className="rs-btn rs-btn-primary"
                onClick={() => sign.mutate()}
                disabled={!ready || sign.isPending || !signer.trim()}
                title={ready ? 'Sign and issue this pack' : 'Resolve the checklist above first'}
              >
                {sign.isPending ? 'Issuing…' : 'Sign off and issue'}
              </button>
              {pack.data.status === 'signed' && (
                <button type="button" className="rs-btn rs-btn-quiet" onClick={() => reopen.mutate()}>
                  Reopen
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}
