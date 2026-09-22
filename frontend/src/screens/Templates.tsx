/**
 * Screen 1 — Templates: the YAML editor with schema validation and a section preview.
 *
 * Validation runs as you type, against the real backend schema rather than a copy of it in
 * the browser — a second definition of "valid" is a second thing to keep in step, and the
 * one that drifts is always the one the user sees.
 *
 * A version that a pack already cites is **locked**, and the editor says so before you start
 * typing rather than after you press save. That rule is what makes `template_version` on an
 * issued archive mean anything.
 */

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { ErrorState, Loading } from '../components/States';

const TYPE_TONE: Record<string, string> = {
  table: 'rs-badge-slate',
  kpi_grid: 'rs-badge-emerald',
  narrative: 'rs-badge-amber',
  flags: 'rs-badge-rose',
};

export function Templates() {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ['templates'], queryFn: api.templates });
  const [selected, setSelected] = useState<string | null>(null);

  const templateId = selected ?? list.data?.[0]?.template_id ?? null;
  const detail = useQuery({
    queryKey: ['template', templateId],
    queryFn: () => api.template(templateId!),
    enabled: templateId !== null,
  });

  const [yaml, setYaml] = useState('');
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (detail.data && !dirty) setYaml(detail.data.yaml);
  }, [detail.data, dirty]);

  const [validation, setValidation] = useState<Awaited<ReturnType<typeof api.validateTemplate>> | null>(
    null,
  );

  // Debounced so a fast typist does not generate a request per keystroke.
  useEffect(() => {
    if (!yaml.trim()) return;
    const timer = setTimeout(() => {
      api
        .validateTemplate(yaml)
        .then(setValidation)
        .catch(() => setValidation(null));
    }, 400);
    return () => clearTimeout(timer);
  }, [yaml]);

  const save = useMutation({
    mutationFn: () => api.saveTemplate(yaml),
    onSuccess: () => {
      setDirty(false);
      void queryClient.invalidateQueries({ queryKey: ['templates'] });
      void queryClient.invalidateQueries({ queryKey: ['template', templateId] });
    },
  });

  const sections = useMemo(
    () => validation?.sections ?? detail.data?.sections ?? [],
    [validation, detail.data],
  );

  if (list.isLoading) return <Loading what="templates" />;
  if (list.isError)
    return <ErrorState error={list.error} what="templates" onRetry={() => void list.refetch()} />;

  return (
    <>
      <div className="rs-page-head">
        <div>
          <h2>Templates</h2>
          <p>
            The pack, defined once. Four section types, a closed selector grammar for the data
            bindings, and pack-level style rules the tone linter enforces. Changing the style
            rules is a versioned, tracked event — not a prompt tweak somebody made on a
            Tuesday.
          </p>
        </div>
        <div className="rs-toolbar">
          {list.data?.map((template) => (
            <button
              key={template.ref}
              type="button"
              className={`rs-btn rs-btn-sm${template.template_id === templateId ? ' rs-btn-primary' : ''}`}
              onClick={() => {
                setSelected(template.template_id);
                setDirty(false);
              }}
            >
              {template.name} v{template.version}
            </button>
          ))}
        </div>
      </div>

      {detail.isLoading && <Loading what="the template" rows={8} />}
      {detail.isError && (
        <ErrorState error={detail.error} what="the template" onRetry={() => void detail.refetch()} />
      )}

      {detail.data && (
        <div className="rs-grid-2" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 420px)' }}>
          <div className="rs-card">
            <div className="rs-card-head">
              <div>
                <h3>{detail.data.name}</h3>
                <p className="rs-card-sub">
                  <code>{detail.data.ref}</code>
                  {detail.data.locked && ' · locked'}
                </p>
              </div>
              <div className="rs-toolbar">
                {validation && (
                  <span className={`rs-badge ${validation.valid ? 'rs-badge-emerald' : 'rs-badge-rose'}`}>
                    <span aria-hidden>{validation.valid ? '✓' : '✕'}</span>
                    {validation.valid ? 'valid' : 'invalid'}
                  </span>
                )}
                <button
                  type="button"
                  className="rs-btn rs-btn-sm rs-btn-primary"
                  onClick={() => save.mutate()}
                  disabled={!dirty || save.isPending || validation?.valid === false}
                >
                  {save.isPending ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>

            {detail.data.locked && (
              <div className="rs-gap" style={{ marginBottom: 12 }}>
                <div className="rs-gap-head">
                  <span className="rs-badge rs-badge-amber">
                    <span aria-hidden>🔒</span>locked
                  </span>
                  <strong>A pack has already been built from this version.</strong>
                </div>
                <p className="rs-gap-detail">
                  Editing it would change what an issued archive's <code>template_version</code>{' '}
                  refers to. Increment <code>version</code> in the YAML to create v
                  {detail.data.version + 1} instead — that is what keeps a signed pack's template
                  reference meaningful.
                </p>
              </div>
            )}

            {save.isError && <ErrorState error={save.error} what="the save" />}

            {validation && !validation.valid && (
              <div className="rs-gap" style={{ marginBottom: 12 }}>
                <div className="rs-gap-head">
                  <span className="rs-badge rs-badge-rose">
                    <span aria-hidden>✕</span>schema
                  </span>
                </div>
                {/* The backend's own error, which names the path and the problem. */}
                <pre className="rs-gap-detail" style={{ whiteSpace: 'pre-wrap', margin: '7px 0 0' }}>
                  {validation.error}
                </pre>
              </div>
            )}

            <label className="rs-sr-only" htmlFor="yaml">
              Template YAML
            </label>
            <textarea
              id="yaml"
              className="rs-yaml"
              spellCheck={false}
              value={yaml}
              onChange={(event) => {
                setYaml(event.target.value);
                setDirty(true);
              }}
            />
          </div>

          <div>
            <div className="rs-card">
              <div className="rs-card-head">
                <div>
                  <h3>Section preview</h3>
                  <p className="rs-card-sub">
                    {sections.length} sections · updates as you type
                  </p>
                </div>
              </div>
              <ul className="rs-list-reset" style={{ display: 'grid', gap: 8 }}>
                {sections.map((section) => (
                  <li key={section.id} className="rs-sectionlist-item" style={{ cursor: 'default' }}>
                    <span className="rs-sectionlist-title">{section.title}</span>
                    <span className="rs-sectionlist-meta">
                      <span className={`rs-badge ${TYPE_TONE[section.type] ?? 'rs-badge-slate'}`}>
                        {section.type}
                      </span>
                      <code>
                        {section.source}.{section.select}
                      </code>
                      {section.required && <span className="rs-note">required</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rs-card">
              <div className="rs-card-head">
                <h3>The four types</h3>
              </div>
              <ul className="rs-list-reset rs-note" style={{ display: 'grid', gap: 7 }}>
                <li>
                  <code>table</code> — rows from a binding, with optional totals. Computed;
                  not editable by a reviewer.
                </li>
                <li>
                  <code>kpi_grid</code> — named metrics with prior-period comparatives.
                </li>
                <li>
                  <code>narrative</code> — drafted from that section's figures and tone rules
                  only. The one type a human can edit.
                </li>
                <li>
                  <code>flags</code> — rule firings with their evidence.
                </li>
              </ul>
              <p className="rs-note" style={{ marginTop: 10 }}>
                There is no fifth type, and a template declaring one fails validation. The
                fence is deliberate: an open-ended template language is how a reporting tool
                becomes a programming language nobody can audit.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
