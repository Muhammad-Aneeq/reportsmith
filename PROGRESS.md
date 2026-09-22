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

---

## P1–P8 · built — **DONE**

`make demo` runs the product end to end. 377 backend tests, 38 frontend tests, lint clean,
mypy strict clean, all three eval gates green, golden files unchanged.

### What the seed gave, and what it cost

Vendoring `../statementlens/backend/ledgerfab/` brought the engine **and** the statement
emitter in one move, byte-identical, with its own 169 tests running here before anything was
built on top. Those tests are the reason the copy is trustworthy rather than merely present —
including the strong one, where the operating cash-flow section rebuilt from cash postings
must equal the indirect build-up from the statements. Two independent routes, same number.

The cost was one honest fork: the vendored manifest test excluded `statements/`, commented
*"THIS project's extension, not vendored code."* True upstream, false here. Left alone it
would have put the code every figure comes from outside the drift check — so the exclusion is
removed, marked `LOCAL CHANGE`, and explained in `VENDORED.md`. That assumption being true in
exactly one repo is also the argument for the emitter graduating into the shared engine, which
is now SIBLING_NOTES #7.

### The SpendSort fixture took three attempts, and the third is the interesting one

The brief prefers *"real sample exports you generate from them if runnable."* SpendSort is
runnable, so:

1. **Import it and call its services.** Failed immediately — both repos name their package
   `app`, so importing SpendSort permanently shadows ours. Moved to a subprocess, which also
   means it runs against *its own* installed dependencies, which is what "we ran the real
   thing" has to mean.
2. **Feed it our GL lines.** It ran, and every row came back blank and queued. Its
   `MockCategorizer` matches a fixed table of consumer and SaaS descriptors — Amazon, Uber,
   Zoom — and the shared engine's counterparties are synthetic B2B names. Two portfolio
   projects on the same data engine could not be composed offline.
3. **Use the product as designed.** SpendSort's signature feature is memory-first: a mapping
   a human has confirmed bypasses the model entirely. The GL already records which account
   each vendor's invoices were booked to — that *is* the trained state. Seeding
   `vendor_memory` from it, and passing a chart of accounts built from the same world (its
   `6000` is *Advertising & Marketing*; the shared engine's is *Professional fees*), gives
   100% memory-hit, **zero LLM calls**, deterministic output that reconciles to the pack's
   expense total to the cent.

The third attempt is the one worth keeping, because the property it produces — the category
table adding up to the P&L cost line — is the one that still matters after the fixture is
replaced by live data.

### Four bugs the test suite caught that review would not have

- Signing an already-issued pack surfaced as a **SQLite UNIQUE violation**: the signoff row
  was inserted before the transition guard ran, so a database constraint was standing in for a
  governance decision.
- `edit_section` returned a **stale edits collection** under `expire_on_commit=False`, so a
  section reported zero edits immediately after recording one — and the edit history is the
  feature.
- The no-recommendations lint rule matched **one exact phrase** and silently did nothing for
  the shipped pack's actual wording. A rule that quietly never fires is worse than no rule.
- Per-test archive isolation: pack ids restart at 1, so a shared archive directory made the
  second test collide with the first — and the collision *looked like the immutability guard
  working*.

### numcheck: one rename, verified liftable

`numcheck/tokenize.py` shadows the stdlib `tokenize`, which `linecache` imports, which
`inspect` imports — crashing at import with `partially initialized module 'inspect' has no
attribute 'signature'`. StatementLens's P6 design specifies that filename and its current
`pythonpath` would trigger it. Renamed to `tokens.py`, and a test now asserts no module in the
package collides with `sys.stdlib_module_names`.

The lift was then **tested rather than claimed**: the package was copied into an empty
directory with no ReportSmith code present, and its 46 tests run from the parent with only
`pydantic` and `pytest` installed. CI does the same on every push.

### The UI bar

Held as an acceptance criterion rather than a polish pass (**D-019**): real loading, empty and
error states on every screen; the AI-draft diff is word-level because a line diff on a
one-paragraph section shows a reviewer nothing; status is colour **plus** icon **plus** text
everywhere; `j`/`k`/`a`/`e` drive the review without a mouse; both themes are designed rather
than one inherited. Thirteen component tests hold the claims that would otherwise quietly rot
— including that a "verified" badge refuses to claim a pass when nothing was checked.

### Not done

- **Demo video** — the only outstanding launch requirement (spec 00 E).
- **The live model path** — implemented and `live`-marked, never run. No API key was used, so
  "it works with a real model" is an argument this repo makes but does not evidence.
- **Browser-driven UI verification** — the Chrome extension was not connected, so the screens
  were verified through the API and a manual script is written up in `docs/GOVERNANCE.md`.
