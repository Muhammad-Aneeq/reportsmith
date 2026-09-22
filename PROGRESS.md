# ReportSmith · PROGRESS

> Narrative log, one entry per phase. The tick-list lives in [PLAN.md](PLAN.md); blockers in [BLOCKERS.md](BLOCKERS.md).
> This file records what was *learned*, not what was *typed* — the diff already shows the latter.

---

## P0 · Plan — **DONE**

**Read first, in full:** `docs/spec_00_shared_foundations.md` (the three foundations, the stack lock in §F, the universal definition of done in §E) and `docs/spec_13_reportsmith.md` (F1–F7, the §6 data model, the §9 screens, the §10 gates). Both moved into `docs/` from the repo root; `git init`.

**Then went and looked, before writing a line of plan.** Four findings changed the shape of the build:

1. **Two of the three siblings do not exist as code.** `../spendsort/` and `../statementlens/` each contain exactly two files — `spec_00` and their own spec. No `backend/`, no export, and critically **no `backend/numcheck/`**. A grep for `numcheck` / `figure_ref` / `cross_check` / `numeric_fidelity` across all fourteen portfolio repos returns spec prose and nothing else. So the brief's *"import or vendor it"* has no referent (BLOCKERS **B4**), and its *"fixture-test against real sample exports you generate from them if runnable"* resolves to the documented-schema branch it offers (PLAN **D-005**). Both are logged rather than quietly assumed.

2. **The ledgerfab seed was not at `./backend_seed_ledgerfab/` either** (BLOCKERS **B2**). Five copies exist across the portfolio; `../ledgerlab/backend/ledgerfab/` is upstream — three siblings carry a `VENDORED.md` naming it, and it is the strict superset. Vendoring it follows an established portfolio convention rather than inventing one.

3. **The seed was run, not assumed to work.** `generate('realistic', 42)` → 60 invoices, 120 GL entries, 64 transactions, 28 exceptions, `dataset_hash 38b8930d494d`. More importantly, the thing `make month2` depends on was verified directly: overriding `Profile.period_start`/`period_end` to a calendar month confines every generated date to that window (`generators/invoices.py:66`, `notes.py:87`, `transactions.py:365` all draw from the profile window) and produces a distinct dataset hash. Two months, two hashes, one structure — which is exactly what spec 13 F7's diff demo needs (PLAN **D-009**).

4. **ledgerfab has no revenue.** Its chart of accounts *declares* `4000 Revenue` and `1100 Accounts receivable`, but the GL only ever books `{2000, 5000, 6000, 6100, 6200, 6300}` — two entries per invoice, expense debit and AP credit, the purchase cycle only. Had this not been checked, the default Monthly Management Pack would have shipped with a headline KPI that is structurally always zero. The pack is therefore spend- and payables-shaped (PLAN **D-007**) — and the revenue-facing sections become the *honest* demonstration of spec 13 F2's GAP path (PLAN **D-006**).

**The one piece of luck worth naming:** finding (1) and requirement F2 point the same way. Spec 13 F2 demands that a missing binding render as an explicit GAP, *"never silently omitted"*, and F5 demands that unresolved gaps block issuance unless waived. Two genuinely-absent siblings mean the gaps panel and the waiver flow are exercised by the **default template on the default run**, not by a mock. The dependency that is missing is the feature that gets proven.

**Toolchain verified:** Python 3.12.10 · uv 0.11.23 · node 24.14.1 · npm 11.11.0 · git 2.53 · **no `make`** (BLOCKERS **B1**). `reportlab` was confirmed already proven in the portfolio (`../InvoiceOps/backend/pyproject.toml:23`) before PDF output was committed to as a phase deliverable rather than a risk.

**Decisions locked before any code**, so that Phase 1 is execution and not design: the template model and its **closed selector grammar** (**D-008** — the fence spec 13 §14 asks for against YAML complexity creep, and the reason golden-file determinism is achievable at all), `Decimal` money at one boundary (**D-010**), narrative-only editing (**D-011**), approval revoked by editing (**D-012**), the pipeline order `draft → numcheck → retry → lint → numcheck re-verify` (**D-015**, since the linter's formatting fixes touch how figures render), two disjoint hashes so "same structure, different numbers" is falsifiable rather than impressionistic (**D-016**), and a deliberately faulty mock so the 100% fidelity gate is observed failing before it is trusted green (**D-014**).

**Acceptance:** PLAN.md carries the constraint→mechanism→test table, the locked template model, the full file map, per-phase spec-quoted acceptance criteria and test plans, the external-dependency table with the sibling-schema fixture strategy spelled out, and a 16-entry decisions log. **No application code exists yet.**

**Next:** P1 — skeleton, vendored ledgerfab with `VENDORED.md`, the closed template schema, the versioned store, the shipped default Monthly Management Pack, and the six spec 13 §6 tables.

---

## P0 · correction — **finding (1) above was wrong**

The user pushed back: *"no spendsort and statementlens has code working."* They were right.

**Both siblings are real repos.** SpendSort is complete — backend, LangGraph categorizer, frontend, evals, `FINAL_REPORT.md`, a demo video, and shipped `examples/month_01…`, `month_02…` files. StatementLens is through **P3 of P11**, with a working statement emitter, intake, alignment and an API. The listing P0 relied on was taken before those trees were populated and was never re-checked; every claim built on it inherited the staleness. Root cause and cost are written up in BLOCKERS **B0**; the wrong decisions are struck through in PLAN.md's log rather than deleted, because a decision that shaped a day of planning should stay visible after it is reversed.

**The instructive part:** P0 verified the ledgerfab seed by *running* it, and that finding held. The two findings that were wrong are precisely the two taken from a directory listing instead of an execution. The standing rule now is to re-check a sibling's tree immediately before depending on it, and to prefer running it over listing it — which is why `fixtures/gen_fixtures.py` executes SpendSort rather than reading about it.

**What the correction gained, beyond accuracy:**

1. **The pack becomes a real management pack.** `../statementlens/backend/ledgerfab/statements/` is a built, working multi-period statement emitter whose own README designates it for reuse: *"lifting this directory into the shared engine is a directory move."* Run here at monthly grain it returns `Period(id='2024-01' …)`, `revenue 3,631,007.40`, `net_income -104,377.55`, `total_assets 19,391,654.47` — `Decimal` throughout, hash-stable, with seeded anomalies and a ground-truth key. It derives all three statements from a trial balance rather than authoring them, so `assets = liabilities + equity` holds by construction. **D-007** — the decision to avoid revenue entirely — is retired.
2. **`make month2` loses its hack.** The emitter has a native `grain="month"`; the earlier plan faked months by overriding ledgerfab's profile window.
3. **SpendSort moves to the brief's preferred branch.** Its real export schema is 15 columns in `services/export.py`, not the four spec 11 mentions. Reading the code surfaced three quirks prose never would: UTF-8 **with BOM**, anti-formula-injection `'` prefixes that are *in the data*, and no period column — so the adapter slices by `date`. All three are bound for SIBLING_NOTES.

**What is still genuinely missing:** StatementLens's computations (P4), flags (P5) and **`numcheck` (P6)**. Decided with the user: build `numcheck` here as a standalone package matching their P6 design module-for-module so adoption is a directory move (**D-004**), and compute ratios/flags in-repo to their P4/P5 shapes so the eventual swap touches only a reader (**D-018**). Per the user's instruction, **the repo is self-contained** — vendored code and committed fixtures, never a runtime path dependency on a sibling (**D-017**).

**Also added:** the UI is now held to an explicit *modern and pleasant* bar as a P6 acceptance criterion rather than a polish pass (**D-019**) — real empty/loading/error states on every screen, a word-level draft-vs-current diff, glanceable approval and gap state, keyboard-navigable review, light and dark both deliberate. This repo's screenshots carry the governance argument, so the Review screen is the pitch.

Still no application code. PLAN.md, BLOCKERS.md and this file now say what is actually on disk.
