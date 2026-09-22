/**
 * Screen 3 — Review. The product's argument, made visible.
 *
 * Three things this screen has to get right:
 *
 * **The AI draft sits beside the current text, with a word-level diff.** A line diff on a
 * one-paragraph section reports "the paragraph changed" and shows the reviewer nothing; the
 * question they actually have is *which words did a person change* (PLAN.md **D-019**).
 *
 * **Figure chips show what the section was allowed to say.** Clicking one is how you check a
 * number without leaving the page — and the chips make visible that the model's numeric
 * universe was this list and nothing else.
 *
 * **Tables say plainly that they are not editable, and why.** A disabled control with no
 * explanation reads as a bug; the reason is a real design decision (D-011) and stating it is
 * cheaper than fielding the question.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { api, type Section } from '../lib/api';
import { Empty, ErrorState, Loading } from '../components/States';
import { PackStatusBadge, SectionStateBadge, VerifiedBadge } from '../components/Status';
import { GapNotice, SectionView } from '../components/SectionView';

function WordDiff({ ops }: { ops: Section['word_diff'] }) {
  return (
    <div className="rs-diff">
      {ops.map((op, i) =>
        op.op === 'insert' ? (
          <ins key={i}>{op.text} </ins>
        ) : op.op === 'delete' ? (
          <del key={i}>{op.text} </del>
        ) : (
          <span key={i}>{op.text} </span>
        ),
      )}
    </div>
  );
}

export function Review() {
  const params = useParams();
  const queryClient = useQueryClient();

  const packs = useQuery({ queryKey: ['packs'], queryFn: api.packs });
  const packId = params.packId ? Number(params.packId) : (packs.data?.[0]?.id ?? null);

  const pack = useQuery({
    queryKey: ['pack', packId],
    queryFn: () => api.pack(packId!),
    enabled: packId !== null,
  });

  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  const sections = pack.data?.sections ?? [];
  const active = useMemo(
    () => sections.find((s) => s.section_key === activeKey) ?? sections[0],
    [sections, activeKey],
  );

  // Abandon an in-progress edit when the reviewer moves to a different section, rather than
  // carrying one section's text into another — which would be a data-loss bug with a very
  // bad blast radius in a product that writes signed documents.
  useEffect(() => {
    setDraft(null);
  }, [active?.id]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['pack', packId] });
    void queryClient.invalidateQueries({ queryKey: ['packs'] });
  };

  const save = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => api.editSection(id, text),
    onSuccess: () => {
      setDraft(null);
      invalidate();
    },
  });
  const approve = useMutation({
    mutationFn: (id: number) => api.approveSection(id),
    onSuccess: invalidate,
  });
  const unapprove = useMutation({
    mutationFn: (id: number) => api.unapproveSection(id),
    onSuccess: invalidate,
  });

  const goNext = () => {
    const index = sections.findIndex((s) => s.section_key === active?.section_key);
    const next = sections[index + 1];
    if (next) setActiveKey(next.section_key);
  };

  // Keyboard review flow. A controller approving eleven sections should not need the mouse.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['TEXTAREA', 'INPUT', 'SELECT'].includes(target.tagName)) return;
      if (!active) return;
      if (event.key === 'a' && !active.approved) {
        event.preventDefault();
        approve.mutate(active.id);
      } else if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault();
        goNext();
      } else if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault();
        const index = sections.findIndex((s) => s.section_key === active.section_key);
        const previous = sections[index - 1];
        if (previous) setActiveKey(previous.section_key);
      } else if (event.key === 'e' && active.editable) {
        event.preventDefault();
        setDraft(active.content.text ?? '');
        setTimeout(() => editorRef.current?.focus(), 0);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (packs.isLoading) return <Loading what="packs" />;
  if (packs.isError)
    return <ErrorState error={packs.error} what="packs" onRetry={() => void packs.refetch()} />;
  if (packs.data?.length === 0)
    return (
      <Empty
        title="Nothing to review"
        detail="No pack has been assembled yet. Run a period first — the review queue is built from an assembled pack."
        action={
          <Link className="rs-btn rs-btn-primary" to="/run">
            Go to Pack run
          </Link>
        }
      />
    );

  if (pack.isLoading) return <Loading what="the pack" rows={6} />;
  if (pack.isError)
    return <ErrorState error={pack.error} what="the pack" onRetry={() => void pack.refetch()} />;
  if (!pack.data || !active) return null;

  const locked = pack.data.status === 'issued' || pack.data.status === 'signed';

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Review · {pack.data.period}</h2>
          <p>
            Every AI sentence keeps its draft history. Edit a narrative, and the original stays
            beside it — approvals are recorded per section and an edit after approval revokes
            it, so “all sections approved” can never be true of text nobody approved.
          </p>
        </div>
        <div className="rs-toolbar">
          <PackStatusBadge status={pack.data.status} />
          <span className="rs-badge rs-badge-slate">
            {pack.data.approved_count}/{sections.length} approved
          </span>
          <Link className="rs-btn rs-btn-primary" to={`/signoff/${pack.data.id}`}>
            Sign-off →
          </Link>
        </div>
      </div>

      {locked && (
        <div className="rs-card" style={{ marginBottom: 16 }}>
          <div className="rs-gap-head">
            <span className="rs-badge rs-badge-emerald">
              <span aria-hidden>🔒</span>locked
            </span>
            <span>
              This pack is {pack.data.status}. Editing is closed; reopen it from the sign-off
              screen if something needs to change.
            </span>
          </div>
        </div>
      )}

      <div className="rs-grid-2">
        <div className="rs-card">
          <div className="rs-card-head">
            <div>
              <h3>Sections</h3>
              <p className="rs-card-sub">
                <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>a</kbd> approve · <kbd>e</kbd> edit
              </p>
            </div>
          </div>
          <div className="rs-sectionlist">
            {sections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={`rs-sectionlist-item${section.section_key === active.section_key ? ' is-active' : ''}`}
                onClick={() => setActiveKey(section.section_key)}
              >
                <span className="rs-sectionlist-title">{section.title}</span>
                <span className="rs-sectionlist-meta">
                  <SectionStateBadge
                    approved={section.approved}
                    gap={section.gaps.length > 0}
                    edited={section.has_human_edits}
                  />
                  <code>{section.type}</code>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="rs-card">
            <div className="rs-card-head">
              <div>
                <h3>{active.title}</h3>
                <p className="rs-card-sub">
                  <code>{active.type}</code>
                  {active.required ? ' · required' : ' · optional'}
                  {active.approved_by ? ` · approved by ${active.approved_by}` : ''}
                </p>
              </div>
              <div className="rs-toolbar">
                {active.approved ? (
                  <button
                    type="button"
                    className="rs-btn rs-btn-sm rs-btn-quiet"
                    onClick={() => unapprove.mutate(active.id)}
                    disabled={locked}
                  >
                    Un-approve
                  </button>
                ) : (
                  <button
                    type="button"
                    className="rs-btn rs-btn-sm rs-btn-primary"
                    onClick={() => {
                      approve.mutate(active.id);
                      goNext();
                    }}
                    disabled={locked}
                  >
                    Approve
                  </button>
                )}
              </div>
            </div>

            {save.isError && <ErrorState error={save.error} what="your edit" />}
            {approve.isError && <ErrorState error={approve.error} what="the approval" />}

            {active.gaps.length > 0 ? (
              <GapNotice gaps={active.gaps} required={active.required} />
            ) : active.editable ? (
              <>
                {draft === null ? (
                  <>
                    <SectionView section={active} />
                    <div className="rs-toolbar" style={{ marginTop: 14 }}>
                      <button
                        type="button"
                        className="rs-btn rs-btn-sm"
                        onClick={() => {
                          setDraft(active.content.text ?? '');
                          setTimeout(() => editorRef.current?.focus(), 0);
                        }}
                        disabled={locked}
                      >
                        Edit narrative
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <label className="rs-sr-only" htmlFor="editor">
                      Edit {active.title}
                    </label>
                    <textarea
                      id="editor"
                      ref={editorRef}
                      className="rs-editor"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                    />
                    <div className="rs-toolbar" style={{ marginTop: 10 }}>
                      <button
                        type="button"
                        className="rs-btn rs-btn-sm rs-btn-primary"
                        onClick={() => save.mutate({ id: active.id, text: draft })}
                        disabled={save.isPending}
                      >
                        {save.isPending ? 'Saving…' : 'Save edit'}
                      </button>
                      <button
                        type="button"
                        className="rs-btn rs-btn-sm rs-btn-quiet"
                        onClick={() => setDraft(null)}
                      >
                        Cancel
                      </button>
                      <span className="rs-note">
                        Saving records a tracked diff and revokes this section's approval.
                      </span>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <SectionView section={active} />
                <p className="rs-note" style={{ marginTop: 12 }}>
                  This section is computed from the bound data, so it is not editable — the
                  same data and template must always produce the same table, which is what the
                  archive's hash attests to. To change it, change the template and re-run.
                </p>
              </>
            )}
          </div>

          {active.ai_draft && (
            <div className="rs-card">
              <div className="rs-card-head">
                <div>
                  <h3>AI draft vs current</h3>
                  <p className="rs-card-sub">
                    Drafted by <code>{active.ai_draft.model}</code> · prompt{' '}
                    <code>{active.content.prompt_version}</code>
                  </p>
                </div>
                <VerifiedBadge
                  verified={active.ai_draft.verified}
                  checked={active.ai_draft.figures_checked}
                />
              </div>

              {active.has_human_edits ? (
                <>
                  <WordDiff ops={active.word_diff} />
                  <p className="rs-note">
                    <ins>Green</ins> was added by a person, <del>red</del> was removed. The
                    original draft is preserved and is what this diff is against.
                  </p>
                </>
              ) : (
                <>
                  <p className="rs-prose">{active.ai_draft.text}</p>
                  <p className="rs-note">
                    Unedited — the current text is exactly what the composer produced.
                  </p>
                </>
              )}
            </div>
          )}

          {(active.content.figure_refs?.length ?? 0) > 0 && (
            <div className="rs-card">
              <div className="rs-card-head">
                <div>
                  <h3>Figures this section could cite</h3>
                  <p className="rs-card-sub">
                    The composer's entire numeric universe. Any number in the prose that is not
                    supported by one of these does not survive the cross-check.
                  </p>
                </div>
              </div>
              <div className="rs-chips">
                {active.content.figure_refs?.map((ref) => (
                  <span className="rs-chip" key={ref.ref_id} title={`${ref.label} = ${ref.value}`}>
                    {ref.label} <strong>{ref.display}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}

          {active.edits.length > 0 && (
            <div className="rs-card">
              <div className="rs-card-head">
                <h3>Edit history</h3>
              </div>
              <ul className="rs-list-reset">
                {active.edits.map((edit) => (
                  <li key={edit.id} className="rs-note">
                    {new Date(edit.at).toLocaleString()} · {edit.editor} · +{edit.lines_added}/−
                    {edit.lines_removed} lines
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
