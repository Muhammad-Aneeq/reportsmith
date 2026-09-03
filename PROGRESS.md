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
