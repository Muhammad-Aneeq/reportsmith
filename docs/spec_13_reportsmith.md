# SPEC 13 · REPORTSMITH — THE GOVERNED REPORTING ASSISTANT
### Finance AI Lab episode project · Track 1 · 4 weeks · Python + LangChain/LangGraph + OpenAI + FastAPI + Vite/React
> **Prereq:** read `spec_00_shared_foundations.md` first. Composes SpendSort (11) outputs, StatementLens (12) computations, and ledgerfab data; reuses the approval-inbox pattern. This is the "AI Reporting Assistants" promise from the Finance AI Lab series, delivered.

## 1. Overview & Positioning
Every finance team assembles the same monthly pack: KPIs, statements summary, variance notes, category breakdowns, exceptions: by hand, from the same sources, in the same format, every month. ReportSmith is a template-driven reporting assistant: define the pack ONCE (sections, data bindings, tone rules: your "teach it once" carousel made executable), then each month it assembles the pack from live data, drafts the narrative sections with structural grounding, and routes the draft through a human sign-off gate before anything is "issued." The rules-file philosophy (Post 7 carousel) as a working product.

## 2. Goals / Non-goals
GOALS: report templates as versioned YAML (sections, bindings, tone/style rules); one-command monthly pack assembly; narrative sections grounded in bound data only; human review + sign-off gate with tracked edits; issued reports archived immutably; the month-2 demo: same template, new data, identical structure.
NON-GOALS: BI dashboarding (it assembles documents, not explorers); real ERP connectors (data arrives from sibling projects/ledgerfab); email distribution (v2); slide output (v2: markdown + PDF first).

## 3. Users & Stories
- Controller: "define our management pack once; every month I review and sign, not assemble."
- Junior: "run the pack, resolve the queue, send for sign-off."
- Lab viewer: "how do saved instructions + grounding + human gates combine into a real workflow? This repo."
US1 define template (or start from the shipped Management Pack default). US2 `run month` → pack assembles: tables computed, narratives drafted, gaps flagged. US3 review screen: edit narrative (edits tracked), approve sections, sign off. US4 issued pack archived with data snapshot + hash. US5 next month: one command, same structure, new numbers.

## 4. Feature Specification
### MVP
F1 Template model (YAML, versioned): sections[{id, title, type[table|kpi_grid|narrative|flags], binding (source + query/selector), tone_rules, required[bool]}] + pack-level style rules (voice, rounding, currency display, taboo phrases). Ships with a default Monthly Management Pack template.
F2 Data bindings: pluggable SourceAdapters: ledgerfab world (direct), SpendSort export (category breakdowns), StatementLens computations (ratios/flags): each returning typed frames; missing/failed binding → section renders as an explicit GAP (never silently omitted), listed in a gaps panel.
F3 Assembly engine: tables/KPIs computed deterministically from bindings; narrative sections drafted by the composer (F4); pack assembled in template order with a generated cover + contents.
F4 Narrative composer (LangGraph, per narrative section): input = that section's bound data + tone rules ONLY; structured output with figure_refs; numeric cross-check identical to StatementLens (reuse the module); style linter enforces tone rules deterministically where possible (rounding, taboo phrases) with violations auto-fixed or flagged.
F5 Review & sign-off: section-by-section review UI; human edits tracked as diffs (AI draft preserved alongside final); per-section approve; pack-level SIGN-OFF required before status=issued; unresolved gaps block issuance unless explicitly waived (waiver recorded).
F6 Archive: issued packs immutable: rendered markdown + PDF + data snapshot + template version + hash; a Reports shelf UI.
F7 The repeatability demo: `make month2` re-runs on the next ledgerfab period; a diff view shows structure identical / numbers changed: the money shot for the launch video.
### v2
Slide (pptx) output; email distribution with sign-off enforcement; scheduled runs (loop-engineering tie-in); template marketplace (community packs); commentary learning from tracked edits.

## 5. System Architecture
```
[SPA] ⇄ [FastAPI] ⇄ [SQLite]
             ├── templates/ (YAML store + versioning)
             ├── adapters/ (ledgerfab | spendsort | statementlens)
             ├── assemble/ (deterministic tables/KPIs)
             ├── narrate/ (LangGraph + numeric cross-check [shared module w/ Spec 12])
             └── issue/ (sign-off state machine, archive, hashing)
```

## 6. Data Model
- templates(id, name, version, yaml, created_at)
- packs(id, template_id, template_version, period, status[draft|in_review|signed|issued], created_at)
- sections(id, pack_id, section_key, type, content_json, ai_draft_json, gaps_json, approved[bool])
- edits(id, section_id, diff_json, editor, at)
- signoffs(pack_id, signer, waivers_json, at)
- archives(pack_id, md_ref, pdf_ref, data_snapshot_hash, issued_at)

## 7. API Surface
CRUD /api/templates · POST /api/packs {template, period} · GET /api/packs/{id} · POST /api/sections/{id}/edit · POST /api/sections/{id}/approve · POST /api/packs/{id}/signoff · GET /api/packs/{id}/export · GET /api/archive.

## 8. Agent/LLM Design
Composer identical philosophy to StatementLens: narrates bound data, never free-reads, numbers verified in code. Tone rules split: deterministic linter first (rounding, currency, banned phrases), LLM style adherence second (judge-scored in evals, pinned+cached). Prompts versioned per template version: changing a template's tone rules is a tracked, evaluable event.

## 9. Frontend Spec (aurora components)
Screens: (1) Templates (YAML editor with schema validation + section preview) · (2) Pack Run (binding status per section, gaps panel, progress) · (3) Review (section list with approve state; narrative editor showing AI draft vs current with diff; figure chips → data panel) · (4) Sign-off (checklist: all sections approved, gaps waived-or-resolved; sign button) · (5) Archive shelf (issued packs, hash, open PDF) · (6) Month-diff view (structure vs numbers).

## 10. Evals & Testing
- assemble/: deterministic golden-file tests (same data + template = identical tables)
- narrate/: numeric-fidelity 100% gate (shared harness with Spec 12); tone-linter unit tests; style adherence judge (pinned+cached)
- workflow: state-machine tests (cannot issue unapproved/gapped packs; waivers recorded; archives immutable)
- E2E: default template on 2 ledgerfab periods → both packs issue; diff view correct
- CI gates: numeric-fidelity + state-machine suite

## 11. Security & Privacy
Synthetic banner; archives append-only + hashed; sign-off identity recorded (simulated auth v1); no LLM access beyond per-section bound data (structural).

## 12. Deployment & Costs
docker-compose; a full pack ≈ tens of cents (few narrative sections, compact inputs). MODEL_COSTS.md.

## 13. Milestones (4 weeks @10h)
W1 template model + adapters (ledgerfab first) + assembly of tables/KPIs
W2 composer (reuse Spec 12 cross-check) + tone linter + gaps handling
W3 review/sign-off state machine + edits tracking + archive
W4 SpendSort/StatementLens adapters + month-2 diff demo + evals + UI polish + README + demo video

## 14. Risks
Template YAML complexity creep → schema-validated, examples-first, hard v1 scope (4 section types); adapter coupling to siblings' formats → adapters versioned against their export schemas, fixture-tested; "AI wrote our board pack" discomfort → the tracked-edits + sign-off design IS the answer; lead the README with it.

## 15. Launch Content Hooks
"Define the pack once. Review forever after: never assemble again." · month-1 vs month-2 diff clip (identical structure, new numbers) · "every AI sentence keeps its draft history: what governed reporting looks like" · tie-back post: "the rules-file carousel, now running my monthly reports".
