/**
 * Screen 5 — Archive shelf: issued packs, their hashes, and a live integrity check.
 *
 * The verify column is the point of the screen. An archive nobody can check is a filing
 * cabinet; this one re-hashes the files on disk against the manifest written at issuance and
 * names which artefact changed if one did.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '../lib/api';
import { Empty, ErrorState, Loading } from '../components/States';

type Verdict = { ok: boolean; problems: string[] };

export function Archive() {
  const archive = useQuery({ queryKey: ['archive'], queryFn: api.archive });
  const [verdicts, setVerdicts] = useState<Record<number, Verdict | 'checking'>>({});

  const check = async (packId: number) => {
    setVerdicts((current) => ({ ...current, [packId]: 'checking' }));
    try {
      const result = await api.verifyArchive(packId);
      setVerdicts((current) => ({ ...current, [packId]: result }));
    } catch (error) {
      setVerdicts((current) => ({
        ...current,
        [packId]: { ok: false, problems: [error instanceof Error ? error.message : 'check failed'] },
      }));
    }
  };

  if (archive.isLoading) return <Loading what="the archive" />;
  if (archive.isError)
    return (
      <ErrorState error={archive.error} what="the archive" onRetry={() => void archive.refetch()} />
    );

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Archive</h2>
          <p>
            Issued packs, append-only. Each carries a hash over its markdown, its PDF, the data
            snapshot it was built from and the template version that produced it — so a reader
            a year from now can prove the document is the one that was signed.
          </p>
        </div>
      </div>

      {archive.data?.length === 0 ? (
        <Empty
          title="No issued packs yet"
          detail="Packs land here once they have been signed off. Assemble a period, review it, resolve or waive its gaps, and sign."
          action={
            <Link className="rs-btn rs-btn-primary" to="/run">
              Go to Pack run
            </Link>
          }
        />
      ) : (
        <div className="rs-card">
          <div className="rs-table-wrap">
            <table className="rs-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Template</th>
                  <th>Issued</th>
                  <th>Content hash</th>
                  <th>PDF</th>
                  <th>Integrity</th>
                </tr>
              </thead>
              <tbody>
                {archive.data?.map((entry) => {
                  const verdict = verdicts[entry.pack_id];
                  return (
                    <tr key={entry.pack_id}>
                      <td>
                        <strong>{entry.period}</strong>
                        <div className="rs-note">pack #{entry.pack_id}</div>
                      </td>
                      <td>
                        <code>{entry.template_ref}</code>
                      </td>
                      <td>{new Date(entry.issued_at).toLocaleString()}</td>
                      <td>
                        <span className="rs-hash" title={entry.content_hash}>
                          {entry.content_hash.slice(0, 20)}…
                        </span>
                      </td>
                      <td>
                        {entry.pdf_available ? (
                          <span className="rs-badge rs-badge-emerald">
                            <span aria-hidden>✓</span>written
                          </span>
                        ) : (
                          <span
                            className="rs-badge rs-badge-slate"
                            title="Issuance proceeded without it; the markdown and the hash are the record"
                          >
                            <span aria-hidden>–</span>unavailable
                          </span>
                        )}
                      </td>
                      <td>
                        {verdict === 'checking' ? (
                          <span className="rs-note">checking…</span>
                        ) : verdict ? (
                          verdict.ok ? (
                            <span className="rs-badge rs-badge-emerald">
                              <span aria-hidden>✓</span>intact
                            </span>
                          ) : (
                            <span
                              className="rs-badge rs-badge-rose"
                              title={verdict.problems.join('; ')}
                            >
                              <span aria-hidden>✕</span>
                              {verdict.problems[0]}
                            </span>
                          )
                        ) : (
                          <button
                            type="button"
                            className="rs-btn rs-btn-sm rs-btn-quiet"
                            onClick={() => void check(entry.pack_id)}
                          >
                            Verify now
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="rs-note" style={{ marginTop: 12 }}>
            Files live under <code>archive/pack-NNNNN/</code> beside a{' '}
            <code>MANIFEST.json</code>, so an archive can be verified by someone holding the
            directory and not this application.
          </p>
        </div>
      )}
    </>
  );
}
