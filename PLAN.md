# ReportSmith · PLAN

> Living document. Phases are ticked in place as they land; anything that cannot be finished is marked
> **BLOCKED** here rather than left ambiguous. Every acceptance criterion quotes the spec it comes from.
> Companion docs: [PROGRESS.md](PROGRESS.md) · [BLOCKERS.md](BLOCKERS.md)

---

## SUMMARY (5 lines)

1. **ReportSmith** turns a monthly finance pack into a *versioned YAML template* — sections, data bindings, tone rules — that is defined once and re-run every period: *"define the pack once. Review forever after: never assemble again."* (spec 13 §15).
2. Tables and KPIs are computed **deterministically** from bound data; narratives are drafted by a LangGraph composer that sees **only that section's bound frame + its tone rules**, and every number it writes is verified in code by `numcheck` before the draft survives.
3. Nothing is "issued" without a human: per-section approval, tracked edits with the AI draft preserved beside the final text, a pack-level sign-off, and **unresolved gaps that block issuance unless explicitly waived** — the waiver itself recorded.
4. It **composes siblings rather than rebuilding them**: `ledgerfab` (vendored, spec 00 A3) is the live data; SpendSort and StatementLens are reached through versioned `SourceAdapter`s. A missing or failed binding becomes an explicit **GAP section**, never a silent omission — which is also how this repo stays honest while those two siblings are still unbuilt.
5. The money shot is `make month2`: the same template on the next ledgerfab period, and a diff view proving **identical structure, changed numbers**.

---

## THE CENTRAL ADAPTATION · vendor the real code, build the rest here

> **Corrected 2026-09-22.** The first pass of this section was written against a stale read of the
> sibling directories and claimed SpendSort and StatementLens were spec-only. **They are not.**
> Both are real, working repos. The re-inspection and what it changed is logged in PROGRESS.md
> under *P0 · correction*; the superseded decisions are struck through in the DECISIONS LOG rather
> than deleted.

The brief says *"It COMPOSES sibling projects: reuse, never rebuild"*. Phase 0 went and looked — twice. What is actually on disk:

| To reuse | Status on disk | Consequence |
|---|---|---|
| **ledgerfab** | not at `./backend_seed_ledgerfab/`; five portfolio copies, `../ledgerlab/backend/ledgerfab/` upstream | **Vendor it** with provenance — **D-002** |
| **`ledgerfab.statements`** — the multi-period statement emitter | ✅ **built and working** in `../statementlens/backend/ledgerfab/statements/`. Its own README: *"Written to be reused. Nothing here imports from `statementlens`, so lifting this directory into the shared engine is a directory move."* | **Vendor it too.** This is the single biggest find of Phase 0 — see below — **D-017** |
| **SpendSort export** | ✅ **complete repo**, `FINAL_REPORT.md` and all. A real 15-column export in `backend/app/services/export.py`, and shipped `examples/month_01…`, `month_02…` intake files | Adapter built against the **real schema**, fixture-tested against a **really-generated export** — the brief's preferred branch — **D-005** |
| **StatementLens computations (P4) + flags (P5)** | ⚠️ **not built yet** — StatementLens is through P3 of P11 | ReportSmith computes what it needs **in-repo**, emitting the shape StatementLens's own PLAN defines — **D-018** |
| **numcheck** | ⚠️ **not built yet** — StatementLens P6, designed in detail, unwritten. Their brief: *"must be built as a REUSABLE package… project 13 will import this pattern"* | **Originates here**, matching their P6 design so adoption is a directory move — **D-004** |

**The repo is self-contained.** Per the standing instruction — *"create everything needed for ReportSmith in this repo"* — nothing here imports across a sibling path at runtime. Reuse means **vendored code with provenance** and **schemas read from real sibling source**, never a path dependency that would make this repo unclonable (**D-017**).

### What the statement emitter changes

The first plan made the default pack spend- and payables-shaped, because raw ledgerfab books only the purchase cycle — no revenue. The emitter retires that constraint. Verified by running it in Phase 0:

```python
emit_statements("squeeze", seed=42, periods=3, grain="month")
# periods: Period(id='2024-01' …), '2024-02', '2024-03'   ← monthly grain, native
# revenue      3,631,007.40      net_income  -104,377.55
# total_assets 19,391,654.47     Decimal throughout, statement_hash stable
# ground_truth.anomalies: margin_compression · ar_days_balloon · inventory_build
```

Three consequences, each of which deletes a workaround:

1. **The Monthly Management Pack gets real financials** — P&L, balance sheet and cash flow, with `assets = liabilities + equity` guaranteed by construction (the emitter derives statements from a trial balance rather than authoring them). **D-007 is retired.**
2. **`make month2` needs no hack.** The emitter has a native `grain="month"` and period ids `2024-01`, `2024-02`. The earlier plan overrode ledgerfab's profile window to fake a month. **D-009 is simplified.**
3. **Money is already `Decimal`** at the source, and `statement_hash` gives the data-snapshot hash the archive needs for free.

### The GAP path is still exercised — deliberately

Spec 13 F2 requires that a *"missing/failed binding → section renders as an explicit GAP (never silently omitted), listed in a gaps panel"*, and F5 requires unresolved gaps to block issuance unless waived. With the siblings working, that path has to be proven on purpose rather than by accident: `test_no_silent_omission.py` drives twelve adversarial adapter behaviours, and the default template ships one section bound to a dataset that is deliberately unavailable in the demo profile, so the gaps panel and the waiver flow are live on the default run.

---

## NON-NEGOTIABLE CONSTRAINTS · and the mechanism that makes each true

Restated from the brief. Each row names the mechanism, not the intention, and the test that would catch its absence.

| Constraint | Mechanism | Verified by |
|---|---|---|
| **Template model exactly per spec 13 F1** — versioned YAML, **4 section types only**, pack-level style rules, default Monthly Management Pack shipped | `template/schema.py` is a closed Pydantic model: `type: Literal["table","kpi_grid","narrative","flags"]`, `extra="forbid"` at every level. Versioning is content-addressed: `(name, version)` unique, YAML immutable once a pack references it | `test_template_schema.py`: a 5th type fails validation; an unknown key fails; editing a referenced version raises. `test_default_template.py`: the shipped pack parses, covers all four types, and round-trips YAML→model→YAML byte-identically |
| **SourceAdapters per F2**; missing/failed binding → **explicit GAP**, never silent omission; gaps listed in a panel | `adapters/base.py` `SourceAdapter` protocol returns `BindingResult = Bound(frame) | Gap(reason, detail)` — a **sum type with no third arm and no exception path**: `resolve_binding` catches `Exception` and converts to `Gap`. The assembler emits a section for **every** template section, always | `test_gaps.py`: adapter raising / returning empty / wrong schema → three distinct `GapReason`s, section still present, `pack.gaps` non-empty. `test_no_silent_omission.py`: for 12 adversarial adapter behaviours, `len(pack.sections) == len(template.sections)` **always** |
| **Tables/KPIs deterministic** (golden-file tested: same data + template = identical output) | Zero LLM in `assemble/`. Money is `Decimal`, quantised once, in one place (`money.py`). Frame ops are a **closed declarative selector grammar** (D-008) — no `eval`, no user expressions. Ordering is total: every sort carries a tiebreak key | `test_golden_assembly.py`: assemble twice → identical JSON; assemble → compare to committed `evals/golden/*.json`; a byte-diff fails CI. `test_no_llm_in_assemble.py` greps `assemble/` for model SDK imports |
| **Narrative composer sees per-section bound data + tone rules ONLY** | Structural, not prompted: `compose_section(frame, tone_rules, style)` — the function has **no parameter** through which the world, the other sections, or the raw ledger could arrive. The prompt is built from its arguments alone | `test_composer_isolation.py`: introspects the call signature and asserts the rendered prompt contains no token from a withheld-secret canary planted in the world outside the frame |
| **Numeric cross-check via numcheck** | Every numeric token in the draft is extracted and must match a declared `figure_ref` value within the style's rounding tolerance. Mismatch → one retry → offending sentence dropped (spec 12 F5) | `test_numcheck.py` (the shared harness): 40+ fixtures — thousands separators, currency symbols, negatives in parens, percentages, ordinals-that-are-not-figures, dates-that-are-not-figures. **`MockComposer(faulty=True)` deliberately emits a wrong number so the gate is proven to fire, not merely to pass** — D-014 |
| **Deterministic tone linter first, judge-scored style second** (pinned + cached) | `narrate/lint.py` runs with no model: rounding conformance, currency rendering, banned phrases, sentence length. Auto-fix is **formatting-only and never touches a digit's value**; numcheck re-runs after the fix. The judge is evals-only, pinned model, response-cached to `evals/cache/` | `test_tone_lint.py` rule matrix. `test_lint_preserves_figures.py`: for every fixture, numcheck passes both before *and* after auto-fix. Judge cache committed → CI needs no key |
| **Review & sign-off state machine per F5** — AI draft preserved beside human edits, diffs tracked, per-section approval, pack-level sign-off, **gaps block issuance unless waived**, waiver recorded | `issue/states.py` is an explicit transition table `(status, event) → status` with named guards. `sections.ai_draft_json` is written once at assembly and **never** written again (asserted). Every human save appends an `edits` row holding a unified diff | `test_state_machine.py`: exhaustive — every (state × event) pair, legal and illegal. Named cases: cannot sign with an unapproved section; cannot sign with an unwaived gap on a `required` section; a waiver records signer + reason + gap ids; approving a section then editing it **revokes** approval (D-012) |
| **Issued archives immutable** (md + PDF + data snapshot + template version + hash) | `archives` is INSERT-only: no UPDATE/DELETE statement against it exists in `app/`. Files land under `archive/<pack_id>/` and the recorded hash covers **all four artefacts plus the template version**, canonicalised then SHA-256 | `test_archive_immutable.py`: greps for write paths; re-issuing a pack → 409; mutating any artefact on disk → verification fails and says which one |
| **`make month2` re-runs the default template on the next ledgerfab period; diff shows identical structure / changed numbers** | `structure_hash(pack)` = SHA-256 over `(template_id, template_version, [(section_key, type, order)])` — deliberately excludes all values. `value_digest(pack)` covers only the numbers | `test_month2_diff.py`: `structure_hash(p1) == structure_hash(p2)` and `value_digest(p1) != value_digest(p2)`. E2E issues both periods |
| **Evals: numeric-fidelity 100% gate, state-machine suite, E2E two-period issuance** | Three CI jobs. The fidelity gate is a **hard 100%** — any unverified number is a build failure, not a score | `.github/workflows/ci.yml`: `evals-gate` job runs all three; mock mode marked in the job name and in the published report |
| **aurora per spec 00 A2; stack per spec 00 F** | `frontend/src/components/aurora/` — all nine components, rendered by an `/aurora` route (spec 00 A2's acceptance criterion). FastAPI + Pydantic v2 + SQLAlchemy + uv; Vite + React + TS + Tailwind + TanStack Query; **LangGraph** for the composer, no LCEL chains | `aurora.test.tsx` renders all nine; `test_stack_lock.py` asserts no `langchain.chains` import |
| **LLM mocked by default; live behind a `live` marker** | `MockComposer` is the default resolution of the `Composer` protocol. `OpenAIComposer` is constructed only when `REPORTSMITH_LLM=live`. `pytest.ini` registers `live`; CI runs `-m "not live"` | `test_mock_default.py`: importing and running a full pack with no `OPENAI_API_KEY` set succeeds and the pack records `model: "mock"` |

---

## THE TEMPLATE MODEL (locked before Phase 1)

Spec 13 F1 fixes the shape: `sections[{id, title, type[table|kpi_grid|narrative|flags], binding (source + query/selector), tone_rules, required[bool]}]` **+ pack-level style rules (voice, rounding, currency display, taboo phrases)**. What follows fills in only what the spec leaves open. Spec 13 §14 names *"template YAML complexity creep"* as risk #1, so the fence is: **four section types, one closed selector grammar, nothing Turing-complete**.

```yaml
id: monthly_management_pack
name: Monthly Management Pack
version: 3                       # integer; (id, version) is immutable once a pack cites it

style:                           # pack-level style rules — spec F1
  voice: "Third person, past tense, factual. No recommendations."
  rounding: { money: 0, percent: 1 }        # decimal places, enforced by the linter
  currency: { code: GBP, symbol: "£", position: prefix, thousands: "," , negative: parens }
  taboo_phrases: ["significant", "robust", "leverage", "world-class", "utilise"]
  max_sentence_words: 30

sections:
  - id: spend_by_account
    title: "Spend by account"
    type: table
    required: true
    binding:
      source: ledgerfab                     # ledgerfab | spendsort | statementlens
      select: gl_expense_lines              # a dataset the adapter publishes in its catalog
      where:    { account_type: expense }
      group_by: [account_code, account_name]
      aggregate: { amount: sum, invoice_id: count_distinct }
      order_by: ["-amount"]                 # total order; ties broken by the group key
      limit: 10
    columns:                                # presentation only; never changes the numbers
      - { field: account_name, label: "Account",  align: left }
      - { field: amount,       label: "Spend",    align: right, format: money }

  - id: headline_kpis
    type: kpi_grid
    required: true
    binding: { source: ledgerfab, select: period_metrics }
    kpis:
      - { id: total_spend,   label: "Total spend",     metric: total_spend,   format: money, compare: prior_period }
      - { id: open_ap,       label: "Open payables",   metric: open_ap,       format: money }
      - { id: exception_rate,label: "Exception rate",  metric: exception_rate,format: percent, direction: lower_is_better }

  - id: spend_commentary
    title: "Spend commentary"
    type: narrative
    required: true
    binding: { source: ledgerfab, select: gl_expense_lines, group_by: [account_code], aggregate: { amount: sum } }
    tone_rules:
      - "Open with the period total, then the two largest movements."
      - "Name the account, never the vendor."
      - "State movements in both absolute and percentage terms."
      - "Do not speculate about cause; the ledger does not contain one."

  - id: exceptions
    title: "Exceptions requiring attention"
    type: flags
    required: false
    binding: { source: ledgerfab, select: exceptions, order_by: ["-severity", "txn_id"] }
```

**Selector grammar (closed, declarative — D-008).** Exactly these keys, all optional except `source` and `select`: `where` (equality / `in` / numeric comparison on a named field), `group_by`, `aggregate` (`sum|count|count_distinct|mean|min|max`), `order_by` (field, `-` prefix for descending), `limit`. No expressions, no formulas, no `eval`. Anything a template cannot express is a **code** change in an adapter's published dataset, which is reviewable and testable — not a string in a YAML file. This is what makes golden-file determinism achievable and the YAML safe to accept from a user.

**Versioning.** A template edit that changes anything a reader would notice mints a new `version`; packs record `template_version` and archives hash it. Spec 13 §8: *"Prompts versioned per template version: changing a template's tone rules is a tracked, evaluable event"* — so the composer's prompt id is `(template_id, version, section_id)` and the eval report keys on it.

---

## DOMAIN DECISIONS (locked before Phase 1)

- **The default pack is spend- and payables-shaped, because that is what ledgerfab actually contains.** Measured, not assumed: the chart of accounts declares `4000 Revenue` and `1100 Accounts receivable`, but `generate('realistic', 42)` books GL only to `{2000, 5000, 6000, 6100, 6200, 6300}` — purchase side only, two entries per invoice (expense debit, AP credit). A pack promising revenue analysis would be a pack whose headline KPI is structurally always zero. **D-007.**
- **Which makes the revenue-facing sections the honest GAP demo.** The default template's *Margin & ratio commentary* binds to `statementlens`, and its *Category breakdown* binds to `spendsort`. Unbound, they render as GAPs on a real run — spec 13 F2's requirement demonstrated by the default path rather than by a mock. With fixtures present they fill. **D-006.**
- **A "period" is a calendar month, produced by overriding ledgerfab's period window.** Verified in Phase 0: `get_profile('realistic').with_overrides(period_start=date(2025,2,1), period_end=date(2025,2,28))` confines every generated date to that month (`generators/invoices.py:66`, `notes.py:87`, `transactions.py:365` all draw from the profile window) and yields a distinct `dataset_hash`. Period 1 = **2025-01**, period 2 = **2025-02** — `make month2`. **D-009.**
- **Money is `Decimal`, quantised to cents once, in `money.py`.** Float sums drift below the cent and would make golden files and numeric fidelity flaky for a reason unrelated to what is being tested. ledgerfab hands out `float`; the boundary converts once, at adapter read, via `Decimal(str(x))`. **D-010.**
- **Only `narrative` sections are human-editable.** A table or KPI is a deterministic function of (data, template); editing its cells would silently break the golden-file contract and make the archive's hash a claim about nothing. Disagreeing with a table is a *template* change, which is versioned and re-runnable. The UI says so where the edit affordance would otherwise be. **D-011.**
- **Editing an approved section revokes its approval.** Otherwise "all sections approved" at sign-off could be true of text nobody approved. **D-012.**

---

## FILE MAP

Complete intended tree. `[gen]` = generated but committed (portfolio artifacts must render on a fresh clone). `[P#]` = the phase that creates it.

```
reportsmith/
├── PLAN.md                                  [P0] this file
├── PROGRESS.md                              [P0] phase-by-phase narrative log
├── BLOCKERS.md                              [P0] blockers, stubs, BLOCKED tasks, STATUS roll-up
├── README.md                                [P8] pitch · "define once, review forever" · governance · composition diagram · synthetic banner · STATUS
├── FINAL_REPORT.md                          [P8] what's built · what's blocked · SIBLING_NOTES · next three
├── MODEL_COSTS.md                           [P8] per-pack and monthly cost, mock vs live (spec 00 D)
├── LICENSE                                  [P1] MIT (spec 00 A1)
├── Makefile                                 [P1] authoritative targets: dev test eval month1 month2 diff demo
├── make.ps1                                 [P1] Windows parity — no `make` on this box (BLOCKERS B1)
├── docker-compose.yml                       [P8] spec 13 §12
├── .github/workflows/ci.yml                 [P8] lint · typecheck · tests · eval-gate (spec 00 A1)
│
├── docs/
│   ├── spec_00_shared_foundations.md            ground truth (moved here in P0)
│   ├── spec_13_reportsmith.md                   ground truth
│   ├── TEMPLATE_GUIDE.md                    [P1] the YAML reference: 4 types, selector grammar, style rules
│   ├── ADAPTER_CONTRACTS.md                 [P2] what each adapter publishes; sibling schema versions + provenance
│   └── GOVERNANCE.md                        [P5] the state machine, drawn; what a waiver means; what a hash covers
│
├── backend/
│   ├── pyproject.toml                       [P1] uv · ruff · mypy · pytest markers (live, integration)
│   ├── ledgerfab/                           [P1] VENDORED — engine from ../ledgerlab + statements/ from ../statementlens
│   │   ├── VENDORED.md                          provenance for BOTH halves + every local change (D-017)
│   │   └── statements/                          ★ the multi-period P&L/BS/CF emitter, monthly grain, Decimal
│   ├── app/
│   │   ├── main.py  settings.py  db.py  models.py     [P1] FastAPI, pydantic-settings, SQLAlchemy (spec 13 §6 tables)
│   │   ├── api/  templates.py packs.py sections.py signoff.py archive.py diff.py   [P1,P2,P5,P7]
│   │   ├── money.py                         [P1] the one rounding rule (Decimal)
│   │   ├── template/
│   │   │   ├── schema.py                    [P1] closed Pydantic model — 4 types, extra="forbid"
│   │   │   ├── store.py                     [P1] YAML store + versioning + immutability guard
│   │   │   └── default/monthly_management_pack.yaml  [P1] the shipped default (spec 13 F1)
│   │   ├── adapters/
│   │   │   ├── base.py                      [P2] SourceAdapter protocol · BindingResult = Bound | Gap · GapReason
│   │   │   ├── selector.py                  [P2] the closed declarative grammar → Frame
│   │   │   ├── frame.py                     [P2] typed frame (columns, dtypes, Decimal money)
│   │   │   ├── ledgerfab_adapter.py         [P2] pnl/bs/cf_lines (vendored emitter) + gl_expense_lines · exceptions · invoices
│   │   │   ├── spendsort_adapter.py         [P2] the REAL 15-col export: utf-8-sig, strip `'` prefix, slice by date
│   │   │   └── statementlens_adapter.py     [P2] computations + flags; in-repo today, live P4/P5 later (B4)
│   │   ├── analysis/                        [P2] ratios + YAML flag rules, to StatementLens's P4/P5 shapes (D-018)
│   │   │   ├── formula.py  engine.py            Computation(formula_id, period, value, status, inputs)
│   │   │   └── flags/rules/*.yaml  engine.py    Flag(rule_id, period, severity, evidence); closed predicate DSL
│   │   ├── assemble/
│   │   │   ├── engine.py                    [P3] template order → sections; cover + contents generated (F3)
│   │   │   ├── tables.py  kpis.py  flags.py [P3] deterministic renderers
│   │   │   └── hashes.py                    [P3] structure_hash · value_digest · snapshot_hash
│   │   └── (numcheck is NOT under app/ — it is a standalone package, below)
│   ├── numcheck/                            ★ [P4] ORIGIN HERE — standalone; lifts into StatementLens P6 (D-004)
│   │   ├── ORIGIN.md  pyproject.toml  README.md  tests/     own everything; zero ReportSmith imports
│   │   ├── models.py                            FigureRef · NumericToken · TokenVerdict · CheckResult
│   │   ├── tokenize.py  match.py  exempt.py     spans + precision · exact Decimal, no tolerance · closed 2-entry list
│   │   ├── verify.py  surgery.py                verdict per token · abbreviation-aware sentence surgery
│   │   └── harness.py                           the shared numeric-fidelity metric (spec 12 §10 / spec 13 §10)
│   │   ├── narrate/
│   │   │   ├── graph.py                     [P4] LangGraph: plan → draft → numcheck → [retry once] → lint → finalize
│   │   │   ├── composer.py                  [P4] Composer protocol · MockComposer(faulty=…) · OpenAIComposer (live)
│   │   │   ├── prompts.py                   [P4] versioned by (template_id, version, section_id)
│   │   │   └── lint.py                      [P4] deterministic tone linter; formatting-only auto-fix
│   │   ├── issue/
│   │   │   ├── states.py                    [P5] transition table + named guards
│   │   │   ├── edits.py                     [P5] unified diffs; ai_draft written once, never again
│   │   │   ├── archive.py                   [P5] md + PDF + snapshot + template version → hash; INSERT-only
│   │   │   └── render_md.py  render_pdf.py  [P5] markdown, then reportlab (proven in ../InvoiceOps)
│   │   └── periods.py                       [P1] month window → ledgerfab profile override + seed (D-009)
│   └── tests/                               [P1→P7] mirrors the constraint table above
│
├── fixtures/                                [P2] [gen] the sibling-schema strategy — see EXTERNAL DEPENDENCIES
│   ├── README.md                                what each fixture is, which spec clause it is derived from
│   ├── gen_fixtures.py                          derives them FROM the same ledgerfab period, so totals tie out
│   ├── spendsort/export_v1.csv                  spec 11 F6 + §6 shape
│   └── statementlens/computations_v1.json · flags_v1.json    spec 12 §6/§7 shape
│
├── evals/                                   the signature folder (spec 00 A1: "EVERY repo has this")
│   ├── cases.jsonl                          [P7] narrative cases: bound frame + tone rules + expected figure set
│   ├── golden/                              [P3] [gen] committed assembled packs — a byte-diff fails CI
│   ├── cache/                               [P7] pinned judge responses, committed → CI needs no key
│   ├── run_fidelity.py  run_style.py  run_state.py   [P7] the three gates
│   └── results/report.sample.{json,md}      [P7] [gen] rendered by the SPA
│
├── frontend/                                [P6] Vite + React + TS + Tailwind + TanStack Query
│   ├── src/components/aurora/                   all nine spec 00 A2 components + /aurora demo route
│   └── src/screens/  Templates · PackRun · Review · SignOff · Archive · MonthDiff   (spec 13 §9)
│
└── archive/                                 [P5] [gen] issued packs — append-only, one dir per pack
```

---

## PHASES

Spec 13 §13 gives four weeks: W1 template model + adapters + assembly · W2 composer + linter + gaps · W3 review/sign-off + edits + archive · W4 sibling adapters + month-2 diff + evals + polish. P1–P8 below are that plan at working granularity.

### ☑ P0 · Plan — **DONE**

- [x] Read `docs/spec_00_shared_foundations.md` and `docs/spec_13_reportsmith.md` in full
- [x] Inspect both siblings: `../spendsort/` and `../statementlens/` are **spec-only** — no export schema, no `backend/numcheck/`, nothing runnable (BLOCKERS **B3**, **B4**)
- [x] Locate the ledgerfab seed — **not** at `./backend_seed_ledgerfab/`; five portfolio copies found, `../ledgerlab/backend/ledgerfab/` identified as upstream (BLOCKERS **B2**)
- [x] **Run the seed before planning on it**: `generate('realistic', 42)` → 60 invoices / 120 GL / 64 txns / 28 exceptions, `dataset_hash 38b8930d494d`; monthly override confined GL dates to `2025-01-01…2025-01-31` and `2025-02-01…2025-02-28` with distinct hashes — so `make month2` is buildable (**D-009**)
- [x] Measure what the GL actually books: `{2000, 5000, 6000, 6100, 6200, 6300}` — no revenue postings, which fixes the default pack's shape (**D-007**)
- [x] Verify toolchain: Python 3.12.10 · uv 0.11.23 · node 24.14.1 · npm 11.11.0 · git 2.53 · **no `make`** (BLOCKERS **B1**); confirm `reportlab` is proven in the portfolio (`../InvoiceOps`) before committing to PDF output
- [x] Move both specs into `docs/`; `git init`
- [x] Write PLAN.md: constraint→mechanism→test table, locked template model, file map, phases, dependency table with the sibling-fixture strategy, decisions log
- [x] Write PROGRESS.md + BLOCKERS.md (B1–B5 + STATUS roll-up); commit Phase 0

**Acceptance:** PLAN.md contains a complete file map, per-phase spec-quoted acceptance criteria and test plans, an external-dependency table that explicitly states the sibling-schema fixture strategy, and a decisions log. **No application code exists yet.**

---

### ☐ P1 · Skeleton · template model · versioned store · the default pack · periods

Spec 13 F1: *"Template model (YAML, versioned): sections[{id, title, type[table|kpi_grid|narrative|flags], binding, tone_rules, required}] + pack-level style rules… Ships with a default Monthly Management Pack template."*

- [ ] `backend/pyproject.toml` (uv, ruff, mypy, pytest markers `live` + `integration`), `Makefile`, `make.ps1`, `.gitignore`, `LICENSE`
- [ ] Vendor **both** halves and write one **`VENDORED.md`** covering them: `../ledgerlab/backend/ledgerfab/` (the engine) and `../statementlens/backend/ledgerfab/statements/` (the multi-period statement emitter — **D-017**). Provenance, every local change, why-not-the-other-copies. **Run their own test suites here before building on them** — the emitter ships `test_emitter_invariants/determinism/periods/export/anomalies`, and those passing in *this* repo is what makes the vendored copy trustworthy
- [ ] `app/money.py` — the single `Decimal` rounding rule (the emitter is already `Decimal`; this covers raw-ledgerfab floats and SpendSort's CSV strings)
- [ ] `app/periods.py` — periods come from `emit_statements(..., grain="month")`; adopt the emitter's own `Period.id` (`2024-01`) verbatim (**D-009**)
- [ ] `app/template/schema.py` — closed Pydantic v2 model, `extra="forbid"`, 4 section types, selector grammar, style rules
- [ ] `app/template/store.py` — YAML store, `(id, version)` immutable once referenced, validation errors that point at the YAML line
- [ ] `app/template/default/monthly_management_pack.yaml` — all four types; the two sibling-bound sections that become the GAP demo
- [ ] `app/db.py`, `app/models.py` — the six spec 13 §6 tables exactly: `templates · packs · sections · edits · signoffs · archives`
- [ ] `app/main.py` + `api/templates.py` — CRUD `/api/templates` (spec 13 §7)
- [ ] `docs/TEMPLATE_GUIDE.md`

**Acceptance:** spec 13 F1 satisfied — the default template parses, exercises all four section types, and round-trips byte-identically; a fifth section type is a validation error; `(id, version)` cannot be mutated once a pack cites it. `make dev` serves the API.
**Test plan:** `test_template_schema.py` (closed-type matrix, unknown-key rejection, selector grammar validation); `test_template_store.py` (versioning, immutability, YAML round-trip); `test_default_template.py`; vendored `test_ledgerfab_determinism.py`.
**Risks:** *YAML complexity creep* (spec 13 §14 risk #1) → the grammar is closed and its test asserts the exact permitted key set, so widening it is a deliberate, visible diff. *Vendored-seed drift* → `VENDORED.md` records provenance and every local change.

---

### ☐ P2 · SourceAdapters · binding · gaps

Spec 13 F2: *"pluggable SourceAdapters: ledgerfab world (direct), SpendSort export (category breakdowns), StatementLens computations (ratios/flags): each returning typed frames; missing/failed binding → section renders as an explicit GAP (never silently omitted), listed in a gaps panel."*

- [ ] `adapters/frame.py` — typed frame; money columns are `Decimal`, converted once at the boundary (**D-010**)
- [ ] `adapters/base.py` — `SourceAdapter` protocol (`catalog()`, `fetch(select, period)`, `SCHEMA_VERSION`); `BindingResult = Bound | Gap`; `GapReason ∈ {adapter_unavailable, binding_failed, empty_result, schema_mismatch, unknown_dataset}`
- [ ] `adapters/selector.py` — the closed grammar → frame ops; total ordering with tiebreaks
- [ ] `adapters/ledgerfab_adapter.py` — publishes `pnl_lines`, `bs_lines`, `cf_lines` (from the vendored emitter, monthly grain) plus `gl_expense_lines`, `exceptions`, `invoices`, `counterparties` from the base engine
- [ ] `app/analysis/` — the ratio pack and the YAML flag rules, **in-repo, to StatementLens's P4/P5 shapes** (**D-018**): `Computation(formula_id, period, value, status[ok|undefined|caveat], inputs)`, `Flag(rule_id, period, severity, evidence)`. A zero denominator is `undefined` with the zero input named — never `0`, never NaN, never a raised exception; an undefined metric never fires a flag
- [ ] `fixtures/gen_fixtures.py` — run SpendSort to produce a **real** export for the same period and commit it (**D-005**, **D-017**)
- [ ] `adapters/spendsort_adapter.py` — the real 15-column schema; `utf-8-sig`; **strip the anti-injection `'` prefix**; slice by `date` since the export carries no period column; `SCHEMA_VERSION="spendsort/v1(export.py COLUMNS @2026-09-22)"`; Pydantic-validated per row
- [ ] `adapters/statementlens_adapter.py` — reads the in-repo analysis output today, the live P4/P5 endpoints later; `SCHEMA_VERSION="statementlens/v1(spec12+their-PLAN-P4/P5 shape)"`
- [ ] `docs/ADAPTER_CONTRACTS.md` — what each publishes, where each schema was read from, exactly what changes when upstream ships
- [ ] **BLOCKED** · repoint the statementlens adapter at live P4/P5 once StatementLens reaches them (BLOCKERS **B4**)

**Acceptance:** spec 13 F2 satisfied — every template section yields a section object; a missing adapter yields a `Gap` with a reason and a human-readable detail; the gaps panel payload lists them; **no adapter failure can raise out of the assembler**. The spendsort fixture's category total equals the ledgerfab expense total for the period, to the cent.
**Test plan:** `test_adapters.py` (catalog contracts, schema validation, per-row rejection); `test_gaps.py` (each `GapReason` reachable); `test_no_silent_omission.py` (12 adversarial adapter behaviours — raises, returns `None`, returns wrong columns, returns wrong dtypes, hangs-then-fails, returns empty — section count invariant holds for all); `test_fixture_reconciliation.py`.
**Risks:** *adapter coupling to siblings' formats* (spec 13 §14) → adapters are versioned against the schema, fixture-tested, and a schema mismatch is a **GAP with a named reason**, not a crash — so the day StatementLens ships a different shape, ReportSmith degrades visibly instead of breaking.

---

### ☐ P3 · Assembly engine · tables · KPIs · golden files

Spec 13 F3: *"tables/KPIs computed deterministically from bindings; … pack assembled in template order with a generated cover + contents."* Spec 13 §10: *"assemble/: deterministic golden-file tests (same data + template = identical tables)."*

- [ ] `assemble/tables.py`, `kpis.py` (incl. `compare: prior_period`), `flags.py`
- [ ] `assemble/engine.py` — template order, generated cover + contents, binding status per section
- [ ] `assemble/hashes.py` — `structure_hash` (structure only), `value_digest` (numbers only), `snapshot_hash` (the bound data)
- [ ] `api/packs.py` — `POST /api/packs {template, period}`, `GET /api/packs/{id}`
- [ ] `evals/golden/` — committed assembled packs for period 1 and period 2

**Acceptance:** *definition of done* — "run a period → binding statuses + gaps panel → tables/KPIs assembled". Assembling twice produces byte-identical JSON; assembling in CI reproduces the committed golden files exactly.
**Test plan:** `test_golden_assembly.py` (double-assemble equality + committed-golden equality); `test_kpi_math.py` (hand-computed fixtures incl. zero denominators, missing prior period, negative deltas); `test_no_llm_in_assemble.py`; `test_ordering_total.py` (equal-value rows keep a stable order under input permutation).
**Risks:** *golden files that lock in a bug* → each golden is accompanied by the hand-computed KPI fixtures in `test_kpi_math.py`, so the numbers are asserted independently of the snapshot. *Dict ordering / float formatting drift* → canonical JSON with sorted keys and `Decimal`-as-string.

---

### ☐ P4 · numcheck · narrative composer · tone linter

Spec 13 F4: *"input = that section's bound data + tone rules ONLY; structured output with figure_refs; numeric cross-check identical to StatementLens (reuse the module); style linter enforces tone rules deterministically where possible (rounding, taboo phrases) with violations auto-fixed or flagged."*

- [ ] `backend/numcheck/` as a **standalone package** — own `pyproject.toml`, own `README.md`, own `tests/`, `pydantic` as the only third-party surface, **zero ReportSmith imports**; CI runs its tests with the backend not installed. Modules match StatementLens P6 one-for-one so adoption is a directory move: `models.py` (`FigureRef`, `NumericToken`, `TokenVerdict`, `CheckResult`) · `tokenize.py` (spans + declared precision; currency, separators, `k`/`m`/`bn`, parenthesised negatives, percentages, `1.4x`) · `match.py` (units agree **and** the ref rounded to the token's own precision equals the token — exact `Decimal`, **no tolerance knob**) · `exempt.py` (the **closed** two-entry list, its exact contents asserted by a test) · `verify.py` · `surgery.py` (decimal- and abbreviation-aware sentence splitting + `drop_failing_sentences`) · **`ORIGIN.md`** (**D-004**)
- [ ] `numcheck/harness.py` — the shared numeric-fidelity metric (spec 12 §10 / spec 13 §10)
- [ ] `narrate/composer.py` — `Composer` protocol; `MockComposer` (deterministic, and a `faulty=True` mode that emits a wrong number — **D-014**); `OpenAIComposer` behind `live`
- [ ] `narrate/prompts.py` — versioned by `(template_id, template_version, section_id)` (spec 13 §8)
- [ ] `narrate/lint.py` — rounding, currency rendering, banned phrases, sentence length; **formatting-only auto-fix**
- [ ] `narrate/graph.py` — LangGraph: `plan → draft → numcheck → [retry once] → lint → numcheck re-verify → finalize`; on second failure the offending sentence is **dropped** and the drop is recorded on the section

**Acceptance:** spec 13 §10's *"numeric-fidelity 100% gate"* holds on the eval set; the composer's isolation is structural, not prompted; a taboo phrase is flagged and a mis-rounded figure is auto-fixed **without changing its value**; `MockComposer(faulty=True)` makes the gate fail, proving it is live.
**Test plan:** `test_numcheck.py` (40+ extraction fixtures: `£1,234`, `(1,234)`, `12.3%`, `1.2m`, `Q1`, `2025`, ordinals, section numbers); `test_composer_isolation.py` (canary); `test_tone_lint.py` (rule matrix); `test_lint_preserves_figures.py`; `test_narrate_graph.py` (retry path, sentence-drop path, both recorded).
**Risks:** *the mock makes the fidelity gate vacuous* → the faulty mode is a required test, not an option. *Auto-fix silently changes a number* → the linter may not modify a digit's value, asserted by re-running numcheck after every fix. *Number extraction false positives* (a year read as a figure) → an explicit non-figure fixture set, and figures must be **claimed** via `figure_refs` rather than inferred.

---

### ☐ P5 · Review · sign-off state machine · tracked edits · archive

Spec 13 F5 and F6, quoted in full in the constraint table above.

- [ ] `issue/states.py` — transition table + guards: `all_sections_approved`, `no_unwaived_gaps`, `not_already_issued`
- [ ] `issue/edits.py` — unified diffs; `ai_draft_json` written once at assembly and never again; editing an approved section revokes approval (**D-012**)
- [ ] `api/sections.py` — `POST /api/sections/{id}/edit`, `POST /api/sections/{id}/approve`
- [ ] `api/signoff.py` — `POST /api/packs/{id}/signoff` with `waivers[]`; guards run **server-side**; signer + timestamp + waiver reason recorded
- [ ] `issue/render_md.py` → markdown; `issue/render_pdf.py` → reportlab
- [ ] `issue/archive.py` — md + PDF + data snapshot + template version → canonical hash; INSERT-only; `GET /api/archive`, `GET /api/packs/{id}/export`
- [ ] `docs/GOVERNANCE.md`

**Acceptance:** *definition of done* — "review with tracked edits → approvals → sign-off (gap waiver flow tested) → archived with hash". An unapproved or unwaived-gapped pack **cannot** reach `issued` through any API path; the AI draft is retrievable beside the final text for every edited section; re-issuing returns 409.
**Test plan:** `test_state_machine.py` (exhaustive state × event; the four named negative cases); `test_edits.py` (diff round-trip, ai_draft immutability, approval revocation); `test_waivers.py` (waiver records signer + reason + gap ids; a waiver for a gap that does not exist is rejected); `test_archive_immutable.py` (write-path grep, 409 on re-issue, tamper detection names the artefact).
**Risks:** *guards enforced only in the UI* → every guard is tested through the API with the UI bypassed. *PDF rendering as a hard dependency* → `render_pdf` degrades to a recorded `pdf: unavailable` gap rather than failing issuance, and BLOCKERS gets an entry (fallback per the P0 reportlab check).

---

### ☐ P6 · Frontend · the six screens

Spec 13 §9: Templates · Pack Run · Review · Sign-off · Archive shelf · Month-diff.

- [ ] `components/aurora/` — all nine spec 00 A2 components + `/aurora` demo route (spec 00 A2 acceptance)
- [ ] **Templates** — YAML editor with schema validation (errors point at the line) + section preview
- [ ] **Pack Run** — per-section binding status, **gaps panel**, progress
- [ ] **Review** — section list with approve state; narrative editor showing **AI draft vs current with diff**; figure chips → data panel; tables/KPIs visibly read-only with the reason (**D-011**)
- [ ] **Sign-off** — checklist: all sections approved · gaps waived-or-resolved · sign
- [ ] **Archive shelf** — issued packs, hash, open PDF
- [ ] **Month-diff** — structure vs numbers, side by side

**The UI is held to a "modern and pleasant" bar as an acceptance criterion, not a polish pass (D-019).** This repo's screenshots carry the portfolio's governance argument — the Review screen *is* the pitch — so the bar is explicit and checkable:

- [ ] aurora tokens throughout (`#0B1E3B` / `#10B981`, frosted surfaces, Space Grotesk / Inter); **no ad-hoc colours or one-off spacing**
- [ ] **every** screen has real loading, empty and error states — no spinner-forever, no dead blank page, no raw JSON dump, no unstyled `<table>`
- [ ] the AI-draft-vs-current diff is a **proper** diff: word-level highlighting, not two paragraphs side by side
- [ ] gaps and approval state are legible **at a glance** — colour plus an icon plus text, never colour alone (which is also the accessibility floor)
- [ ] keyboard-navigable review flow (approve / next / edit), visible focus rings, `prefers-reduced-motion` respected
- [ ] responsive down to a 1280px laptop; light **and** dark both deliberate, not one inherited by accident
- [ ] transitions are quick and purposeful — state changes animate, nothing decorative

**Acceptance:** *definition of done* — `make dev` → default template renders in the editor → run a period → statuses + gaps → review → approve → sign → archive → diff. `/aurora` renders every component. Plus the seven bullets above, checked screen by screen and recorded in PROGRESS.md.
**Test plan:** `aurora.test.tsx`; component tests for the diff view and the sign-off checklist's disabled states; an axe-core pass for contrast and focus order; a Playwright-or-equivalent smoke over the happy path if the runtime allows, else a documented manual script in `docs/GOVERNANCE.md`. Screenshots of all six screens committed for the README.
**Risks:** *screen count vs remaining time* → build order is Pack Run → Review → Sign-off first (they carry the governance story); Templates editor and Month-diff last; anything unfinished is marked **BLOCKED** rather than half-shipped. *"Modern" drifting into decorative* → the bar above is a list of behaviours, not a mood; each item is individually checkable.

---

### ☐ P7 · month2 · diff view · evals · CI gates

Spec 13 F7 and §10.

- [ ] `make month1` / `make month2` — the default template on `2025-01` then `2025-02`
- [ ] `api/diff.py` + `GET /api/packs/diff?a=&b=` — structure identical / numbers changed
- [ ] `evals/cases.jsonl` — narrative cases: bound frame + tone rules + the exact figure set that must appear
- [ ] `evals/run_fidelity.py` — **100% or fail**; `run_state.py` — the state-machine suite; `run_style.py` — pinned + cached judge (`evals/cache/` committed)
- [ ] `.github/workflows/ci.yml` — lint · typecheck · tests · eval-gate; mock mode named in the job title and in the report

**Acceptance:** spec 13 F7 — `make month2` produces a structurally identical pack with different numbers, and the diff view says so; spec 13 §10 CI gates green; E2E issues **both** periods.
**Test plan:** `test_month2_diff.py` (`structure_hash` equal, `value_digest` different); `test_e2e_two_periods.py` (assemble → narrate → approve → sign → issue, twice, both archived with distinct hashes); `test_evals_gate.py` (a seeded failure makes the gate red).
**Risks:** *a green gate that measures nothing* → each gate has a paired negative test that must make it fail.

---

### ☐ P8 · README · MODEL_COSTS · FINAL_REPORT · docker-compose · polish

- [ ] `README.md` — screenshot → pitch → **"define once, review forever"** → composition diagram (what each sibling provides) → **tracked-edits + sign-off governance section** → ⚠️ synthetic banner → quickstart → honest **STATUS** (spec 00 A1 mandatory order)
- [ ] `MODEL_COSTS.md` — per-pack and monthly, mock vs live, "keep it cheap" (spec 00 D)
- [ ] `FINAL_REPORT.md` — what is ready · what is BLOCKED and why · **SIBLING_NOTES** (schema friction in spendsort/statementlens worth fixing upstream) · next three
- [ ] `docker-compose.yml`; final PLAN.md tick-through; every unfinished item marked **BLOCKED** with its BLOCKERS id

**Acceptance:** spec 00 E — screenshot-first README ✓ · architecture diagram ✓ · `evals/` with a CI gate ✓ · synthetic banner ✓ · `MODEL_COSTS.md` ✓. PLAN.md fully ticked or BLOCKED-marked.

---

## EXTERNAL DEPENDENCIES + FALLBACKS

| Dependency | Needed for | Status | Fallback if unavailable |
|---|---|---|---|
| **`ledgerfab` seed** | live monthly data | ⚠️ **not at `./backend_seed_ledgerfab/`** — BLOCKERS **B2**; vendored from `../ledgerlab` (**D-002**) | Resolved by vendoring. Verified working in P0 before anything was planned on it |
| **`ledgerfab.statements` emitter** | the pack's actual P&L / BS / CF, at monthly grain | ✅ **built and verified running** in `../statementlens`; vendored in (**D-017**) | None needed. Its own README designates it for reuse |
| **`../spendsort` export** | category-breakdown sections | ✅ **complete repo, runnable** — real 15-column schema in `services/export.py` | Generate a real export, commit it under `fixtures/` (**D-005**). No blocker |
| **`../statementlens` computations (P4) + flags (P5)** | ratio and flag sections | ⚠️ **not built upstream yet** — BLOCKERS **B4** | Computed **in-repo** to the upstream shape (**D-018**); the adapter's reader is the only thing that changes when they land |
| **`numcheck`** | the numeric cross-check — the headline gate | ⚠️ **not built upstream yet** (StatementLens P6) — BLOCKERS **B4** | **Originates here** as a standalone package, module-for-module matching their P6 design (**D-004**) |
| `reportlab` | archive PDF | ✅ proven in `../InvoiceOps` (`pyproject.toml:23`) | Markdown-only archive; PDF recorded as an artefact gap, issuance still proceeds |
| `langgraph` / `langchain-openai` | the composer (spec 00 F) | ✅ used across the portfolio | Composer graph is a small state machine; a hand-rolled fallback keeps mock mode working with zero LLM deps |
| OpenAI API key | `live` narratives only | ⚠️ optional by design | **Mock is the default.** CI runs `-m "not live"`; the judge runs from a committed response cache |
| `make` | documented commands | ❌ **absent on Windows** — BLOCKERS **B1** | `make.ps1` mirrors every target (portfolio convention); the Makefile stays authoritative and is what CI runs |
| Node 24 / npm 11 | the SPA | ✅ verified present | — |
| `aurora-ui` package | shared look (spec 00 A2) | 🚫 no published package exists | Local `frontend/src/components/aurora/` — the portfolio convention in all ten sibling repos (**D-003**) |

### The sibling-schema fixture strategy (required by the brief; this is it)

The brief allows either path: *"fixture-test against real sample exports you generate from them if runnable, else from their documented schemas: log which in DECISIONS LOG."* **Corrected 2026-09-22** — the answer differs per sibling, so both branches are in use and each is logged:

**SpendSort → the preferred branch: real generated exports (D-005).** SpendSort is a complete, runnable repo. The schema is read from `backend/app/services/export.py`'s `COLUMNS` tuple — 15 columns: `date, vendor_raw, vendor_norm, amount, currency, account, account_name, confidence, source, reason, status, learned, coa_valid, cost_usd, memo` — and an export is **really generated** by running SpendSort, then committed under `fixtures/spendsort/` so this repo stays clonable and CI never reaches across a path (**D-017**). Three quirks the adapter must handle, all discovered by reading the real code rather than the spec, all bound for SIBLING_NOTES:
- **UTF-8 *with BOM*** (`utf-8-sig`) — read with the wrong codec and the first column name carries a `﻿`.
- **Anti-formula-injection apostrophes are in the data.** Text cells beginning `= + - @` are prefixed with `'` on export. A vendor called `-EDF Energy` arrives as `'-EDF Energy`; the adapter must strip that prefix or every such vendor renders wrong in the pack.
- **No period column and no `schema_version`.** The export is every transaction, so ReportSmith slices by `date` and cannot detect a schema change from the file itself.

**StatementLens computations/flags → built in-repo to the upstream shape (D-018).** Not a fixture-vs-real choice: P4 and P5 are simply not written upstream yet. ReportSmith computes them in `backend/app/analysis/`, emitting the shapes StatementLens's own PLAN pins, so the eventual swap touches only the adapter's reader.

**Common to both:**
1. Each adapter carries a `SCHEMA_VERSION` that admits its own provenance — `"spendsort/v1(export.py COLUMNS @2026-09-22)"`, `"statementlens/v1(spec12+their-PLAN-P4/P5 shape)"`.
2. **Fixtures are derived from the same period as the pack, never hand-written** (`fixtures/gen_fixtures.py`) — so `test_fixture_reconciliation.py` can assert the SpendSort category total equals the period's expense total to the cent, and period 2's data comes free.
3. **Every read is validated, and a mismatch is a GAP, not a crash.** Rows go through Pydantic; a mismatch yields `GapReason.schema_mismatch` naming the offending field. When a sibling changes shape, ReportSmith shows a labelled gap — the F2 behaviour under test — instead of silently mis-parsing.
4. **The live swaps are named tasks** (B4), each a reader change behind an unchanged `SourceAdapter`, with the fixture retained as the regression test.
5. **Friction is recorded** in `FINAL_REPORT.md` → **SIBLING_NOTES**: the three SpendSort export quirks above; StatementLens having no export *envelope* (no `schema_version`, no period-set metadata) for a pair of endpoints a sibling is expected to consume; and — the one worth raising loudest — **`numcheck` being scheduled at P6 of a project that two downstream repos depend on**, which is why it is being written here instead.

---

## DECISIONS LOG

| # | Decision | Reasoning |
|---|---|---|
> **Entries marked ~~superseded~~ were written against a stale read of the sibling repos and are kept, struck through, with what replaced them.** Deleting them would hide a wrong call that shaped a day of planning.

| **D-001** | "Compose, never rebuild" is honoured as **vendored code + schemas read from real sibling source**, behind versioned `SourceAdapter`s | ~~Two of the three named siblings are spec-only~~ — **wrong, corrected 2026-09-22**: both are real. The principle survives the correction but its content improves: reuse now means vendoring `ledgerfab` and the working `ledgerfab.statements` emitter, and reading SpendSort's actual export schema out of its actual code, rather than composing against prose. What genuinely does not exist yet (numcheck, StatementLens P4/P5) is built here — **D-004**, **D-018**. |
| **D-002** | `ledgerfab` **vendored** into `backend/ledgerfab/`, from `../ledgerlab/backend/ledgerfab/`, not imported | The stated seed path `./backend_seed_ledgerfab/` does not exist (**B2**). Of the five portfolio copies, `ledgerlab`'s is upstream — `finagent-evals`, `finsight` and `InvoiceOps` all carry a `VENDORED.md` naming it, and it is the strict superset. A path dependency on a sibling repo would make this repo unclonable. `VENDORED.md` records provenance and every local change. |
| **D-003** | aurora implemented locally under `frontend/src/components/aurora/` | No published `aurora-ui` package exists; all ten sibling repos carry a local copy. Consistent with spec 00 A2's intent that *"one import line in any project yields the shared look"*. |
| **D-004** | **`numcheck` originates in this repo** (`backend/numcheck/`) as a standalone package — own `pyproject.toml`, own tests, `pydantic` as its only third-party surface, **no ReportSmith imports** — with an `ORIGIN.md` lift procedure. Its module layout matches StatementLens P6 exactly: `models · tokenize · match · exempt · verify · surgery` | The brief says *"import or vendor it"*; StatementLens is at P3 of P11 and P6 is where numcheck lives, so there is still nothing to import. Confirmed with the user 2026-09-22: build it here, shaped for lifting upstream. Matching their P6 module split and its two hard rules — a **closed** two-entry exemption list, and **no tolerance knob** (precision comes from the token the model itself wrote) — is what makes adoption a directory move instead of a merge. Spec 13 §10 calls it *"a shared harness with Spec 12"*; that can only stay true if there is exactly one implementation. |
| **D-005** | The **SpendSort** adapter is built against the **real export schema**, read from `../spendsort/backend/app/services/export.py`, and fixture-tested against an export **really generated** by running SpendSort | ~~Neither sibling is runnable.~~ — **wrong, corrected 2026-09-22**. SpendSort is a complete repo. This takes the brief's *preferred* branch: *"fixture-test against real sample exports you generate from them if runnable."* The schema is the 15 columns `COLUMNS` declares, not a guess from spec 11 prose. The generated export is committed under `fixtures/` so the repo stays self-contained (**D-017**). |
| **D-006** | Fixtures are **derived from the same period** as the pack, never hand-written | A hand-written fixture only proves the parser runs. A derived one proves the assembled pack *reconciles* — SpendSort's category total must equal the period's expense total to the cent — which is the property that still matters once the data is live. It also makes period 2's data free. |
| **D-007** | ~~The default Monthly Management Pack is **spend- and payables-shaped**~~ — **SUPERSEDED by D-017** | The reasoning was sound for the data I thought existed: raw ledgerfab books only the purchase cycle, so a revenue KPI would have been a structural zero. It is moot now — the vendored `ledgerfab.statements` emitter produces real P&L, balance sheet and cash flow at monthly grain. The pack is a genuine management pack. Kept here because "check what the data actually contains before designing the artefact around it" was the right instinct even though the first answer was wrong. |
| **D-008** | Bindings use a **closed declarative selector grammar** (`where/group_by/aggregate/order_by/limit`), never an expression language | Three properties fall out at once: golden-file determinism (no arbitrary code path), safety (a template is user input; `eval` in a YAML file is a remote-code-execution hole), and schema-validatability (the Templates screen can point at the offending line). Spec 13 §14 names YAML complexity creep as risk #1 and prescribes *"hard v1 scope"*; this is where the fence goes. |
| **D-009** | A period is a **calendar month**, taken from the emitter's native `grain="month"`; period ids are the emitter's own (`2024-01`, `2024-02`, …) | ~~Produced by overriding ledgerfab's profile window~~ — **simplified 2026-09-22**. `emit_statements(profile, seed, periods=N, grain="month")` returns `Period(id='2024-01', label='Jan 2024', start, end, index, grain)` directly, so the month concept is upstream's and not this repo's invention. Adopting the emitter's period id verbatim also means a ReportSmith period and a StatementLens period are the same string, which is what makes the two repos' figures joinable at all. |
| **D-010** | Money is `Decimal` end to end; the one conversion point is raw-ledgerfab data, via `Decimal(str(x))`, quantised in `money.py` | The statement emitter already emits `Decimal`, so the statement path needs no conversion at all. Raw ledgerfab (invoices, exceptions, counterparties) still hands out `float`, and SpendSort's CSV hands out formatted strings — both cross the boundary in exactly one place. Float sums drift below the cent, which would make golden files and the numeric-fidelity gate flaky for a reason unrelated to what they test. |
| **D-011** | Only `narrative` sections are human-editable | A table is a deterministic function of (data, template). Editing a cell would break the golden-file contract and reduce the archive hash to a claim about nothing. Disagreement with a table is a *template* change — versioned, re-runnable, and visible in the month-diff. The Review screen states this where the edit affordance would otherwise sit. |
| **D-012** | Editing an approved section **revokes** its approval | Otherwise the sign-off guard "all sections approved" can be true of text that nobody approved — which would make the central governance claim of the product false in the one case where it matters. |
| **D-013** | `signoff` performs sign-and-issue in one endpoint (spec 13 §7's surface is unchanged), but `issue/states.py` models `signed → issued` as a **separate guarded transition** | The spec's API surface lists no `issue` endpoint, so adding one would be a gratuitous divergence. Keeping the edge in the state machine is what lets `test_state_machine.py` assert that issuance cannot be reached from `in_review` — the property the brief actually cares about. |
| **D-014** | `MockComposer` ships a **`faulty=True`** mode that deliberately emits an unverifiable number | A mock that always satisfies numcheck makes a 100% fidelity gate vacuous — it would be green on an empty check. The faulty mode is a required test: the gate must be *observed failing* before it is trusted when green. |
| **D-015** | Narrative pipeline order is `draft → numcheck → [retry once] → lint → numcheck re-verify → finalize` | Spec 13 §8's *"deterministic linter first, LLM style adherence second"* orders the linter before the **judge**, not before the cross-check. The linter auto-fixes formatting, and formatting touches how figures are *rendered* — so the cross-check has to run again afterwards, or a fix could invalidate the guarantee it just established. |
| **D-016** | `structure_hash` and `value_digest` are **two** hashes over disjoint inputs | F7's claim is "identical structure, changed numbers". One combined hash can only say "different". Two hashes make the claim falsifiable — and make the month-diff view a rendering of a tested fact rather than a visual impression. |
| **D-017** | **The repo is self-contained.** `ledgerfab` *and* `ledgerfab.statements` are vendored in; SpendSort's generated export is committed under `fixtures/`; nothing imports across a sibling path at runtime | The user's standing instruction — *"create everything needed for ReportSmith in this repo"* — and the portfolio's own reason for vendoring: a path dependency on `../statementlens` would make this repo unclonable, and would make ReportSmith's CI depend on a sibling's working tree. The emitter is explicitly built for this (*"lifting this directory into the shared engine is a directory move"*). `VENDORED.md` records provenance and every local change, so re-vendoring stays a copy rather than a merge. |
| **D-018** | The ratios and flags that StatementLens P4/P5 will eventually own are **computed in-repo**, in `backend/app/analysis/`, emitting the exact shapes StatementLens's own PLAN defines — `Computation(formula_id, period, value, status[ok\|undefined\|caveat], inputs)` and `Flag(rule_id, period, severity, evidence)` | They do not exist yet upstream, and the pack needs them. Writing them to the upstream shape rather than an ad-hoc one means the `statementlens` adapter's reader is the *only* thing that changes when P4/P5 land — the assembler, the templates, the golden files and the narrative prompts all stay put. Two rules are inherited verbatim because they are load-bearing: a zero denominator yields `status="undefined"` with the zero input named — **never `0`, never NaN, never an exception** — and an undefined metric never fires a flag. |
| **D-019** | The UI is held to a **modern, pleasant** standard as an acceptance criterion, not a finishing touch: aurora tokens, real empty/loading/error states on every screen, keyboard-navigable review, responsive down to a laptop, and light/dark both correct | The user asked for it directly, and this is the repo whose screenshots carry the portfolio's governance story — the Review screen *is* the product argument. A functional-but-ugly sign-off screen would undersell the one thing spec 13 §14 says to lead with. Concretely gated in P6: no screen ships with a raw JSON dump, an unstyled table, or a dead-end blank state. |

---

## PROGRESS

Ticked in place above; narrative log in [PROGRESS.md](PROGRESS.md); anything blocked is recorded in [BLOCKERS.md](BLOCKERS.md) and marked **BLOCKED** here rather than left ambiguous.
