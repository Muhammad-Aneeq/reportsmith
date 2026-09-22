/**
 * The API client and its types.
 *
 * One rule: a failed request surfaces the server's own message. The backend's refusals are
 * written to be read by a person — "required section 'Performance by segment' has an
 * unresolved gap… record a waiver saying why" — and replacing that with "Request failed"
 * would throw away the part that does the work.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    // A network failure is the one case the server cannot explain, so the message has to
    // name the likely cause rather than the symptom.
    throw new ApiError('Cannot reach the API. Is `make dev` running on port 8000?', 0);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* the body was not JSON; the status line is all we have */
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

// ------------------------------------------------------------------- types --

export type SectionType = 'table' | 'kpi_grid' | 'narrative' | 'flags';
export type PackStatus = 'draft' | 'in_review' | 'signed' | 'issued';

export interface Gap {
  reason: string;
  detail: string;
  source: string;
  dataset: string;
  section_key: string;
  title: string;
  required: boolean;
  waived?: boolean;
}

export interface Cell {
  value: string | number | boolean | null;
  display: string;
}

export interface TableContent {
  columns: { field: string; label: string; align: string; format: string }[];
  rows: Record<string, Cell>[];
  total: Record<string, Cell> | null;
  row_count: number;
  truncated_from?: number | null;
  source: string;
  schema_version: string;
}

export interface Kpi {
  id: string;
  label: string;
  metric: string;
  missing: boolean;
  value?: string | null;
  display: string;
  prior_display?: string;
  delta_display?: string;
  direction?: 'up' | 'down' | 'flat';
  sentiment?: 'good' | 'bad' | 'neutral';
  note?: string;
}

export interface FlagItem {
  rule_id: string;
  label: string;
  severity: string;
  severity_rank: number;
  message: string;
  evidence: string | null;
  amount_display: string | null;
  reference: string | null;
}

export interface FigureRef {
  ref_id: string;
  label: string;
  value: string;
  display: string;
  unit: string;
}

export interface NarrativeContent {
  text: string;
  figure_refs: FigureRef[];
  tone_rules: string[];
  drafted: boolean;
  verified?: boolean;
  figures_checked?: number;
  model?: string;
  prompt_version?: string;
  violations?: { rule: string; severity: string; message: string; excerpt: string; fixed: boolean }[];
  dropped_sentences?: string[];
  retried?: boolean;
  edited?: boolean;
}

export interface Section {
  id: number;
  section_key: string;
  title: string;
  type: SectionType;
  order_index: number;
  required: boolean;
  binding_status: 'bound' | 'gap';
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
  editable: boolean;
  content: Partial<TableContent & NarrativeContent> & { kpis?: Kpi[]; items?: FlagItem[]; counts?: Record<string, number> };
  ai_draft: { text: string; model: string; verified: boolean; figures_checked: number } | null;
  gaps: Omit<Gap, 'section_key' | 'title' | 'required'>[];
  edit_count: number;
  has_human_edits: boolean;
  word_diff: { op: 'equal' | 'insert' | 'delete'; text: string }[];
  edits: { id: number; editor: string; at: string; lines_added: number; lines_removed: number }[];
}

export interface Pack {
  id: number;
  period: string;
  status: PackStatus;
  template_ref: string;
  template_id: string;
  template_version: number;
  structure_hash: string;
  value_digest: string;
  snapshot_hash: string;
  model: string;
  created_at: string;
  cover: { title: string; period: string; template_ref: string; section_count: number; gap_count: number };
  sections: Section[];
  gaps: Gap[];
  blockers: { code: string; message: string }[];
  can_sign: boolean;
  approved_count: number;
  signoff: { signer: string; at: string; waivers: { section_key: string; reason: string; signer: string }[] } | null;
  archive: { content_hash: string; md_ref: string; pdf_ref: string | null; issued_at: string } | null;
}

export interface PackSummary {
  id: number;
  period: string;
  status: PackStatus;
  template_ref: string;
  created_at: string;
  gap_count: number;
  section_count: number;
  approved_count: number;
  issued: boolean;
}

export interface TemplateSummary {
  id: number;
  template_id: string;
  name: string;
  version: number;
  ref: string;
  locked: boolean;
  created_at: string;
}

export interface TemplateDetail extends Omit<TemplateSummary, 'id'> {
  yaml: string;
  sections: { id: string; title: string; type: SectionType; required: boolean; source: string; select: string }[];
}

export interface ArchiveEntry {
  pack_id: number;
  period: string;
  template_ref: string;
  content_hash: string;
  data_snapshot_hash: string;
  md_ref: string;
  pdf_ref: string | null;
  pdf_available: boolean;
  issued_at: string;
  verified: boolean;
}

export interface DiffResult {
  a: { id: number; period: string; template_ref: string; structure_hash: string; value_digest: string };
  b: { id: number; period: string; template_ref: string; structure_hash: string; value_digest: string };
  structure_identical: boolean;
  values_differ: boolean;
  sections: {
    section_key: string;
    title: string;
    type: SectionType;
    in_a: boolean;
    in_b: boolean;
    structure_same: boolean;
    values_changed: boolean;
    a: { gap: boolean; summary: { label: string; display: string }[] } | null;
    b: { gap: boolean; summary: { label: string; display: string }[] } | null;
  }[];
}

// ----------------------------------------------------------------- endpoints --

export const api = {
  health: () => request<{ ok: boolean; llm: string; model: string }>('/api/health'),
  periods: () => request<{ periods: { id: string; label: string; index: number }[]; default: string; next: string }>('/api/periods'),

  templates: () => request<TemplateSummary[]>('/api/templates'),
  template: (id: string) => request<TemplateDetail>(`/api/templates/${id}`),
  validateTemplate: (yaml: string) =>
    request<{ valid: boolean; error?: string; ref?: string; sections?: TemplateDetail['sections'] }>(
      '/api/templates/validate',
      { method: 'POST', body: JSON.stringify({ yaml }) },
    ),
  saveTemplate: (yaml: string) =>
    request<{ template_id: string; version: number; ref: string }>('/api/templates', {
      method: 'POST',
      body: JSON.stringify({ yaml }),
    }),

  packs: () => request<PackSummary[]>('/api/packs'),
  pack: (id: number) => request<Pack>(`/api/packs/${id}`),
  createPack: (template: string, period?: string) =>
    request<Pack>('/api/packs', { method: 'POST', body: JSON.stringify({ template, period }) }),
  signoff: (id: number, signer: string, waivers: { section_key: string; reason: string }[]) =>
    request<Pack>(`/api/packs/${id}/signoff`, { method: 'POST', body: JSON.stringify({ signer, waivers }) }),
  reopen: (id: number) => request<Pack>(`/api/packs/${id}/reopen`, { method: 'POST' }),
  exportPack: (id: number) => request<string>(`/api/packs/${id}/export`),
  diff: (a: number, b: number) => request<DiffResult>(`/api/packs/diff?a=${a}&b=${b}`),

  editSection: (id: number, text: string, editor = 'reviewer') =>
    request<Section>(`/api/sections/${id}/edit`, { method: 'POST', body: JSON.stringify({ text, editor }) }),
  approveSection: (id: number, approver = 'A. Controller') =>
    request<Section>(`/api/sections/${id}/approve`, { method: 'POST', body: JSON.stringify({ approver }) }),
  unapproveSection: (id: number) => request<Section>(`/api/sections/${id}/unapprove`, { method: 'POST' }),

  archive: () => request<ArchiveEntry[]>('/api/archive'),
  verifyArchive: (id: number) => request<{ ok: boolean; problems: string[] }>(`/api/archive/${id}/verify`),
};
