# ReportSmith · FINAL REPORT

## What is built

`make demo` runs the whole product: the default Monthly Management Pack assembled on two
consecutive periods, narrated, reviewed, approved, one gap waived with a recorded reason,
signed, archived with a hash, verified, and diffed. Both packs issue. The structure hash is
identical and the value digest is not.

| | |
|---|---|
| Backend tests | **383 passing** (169 of them the vendored engine's own suites, run here) |
| Frontend tests | **38 passing** |
| Eval gates | numeric fidelity **100%** · gate self-test · state machine · E2E · golden files |
| Screens verified | **7 × 2 themes**, headless, asserted — not just photographed |
| Live model calls made | **zero** — mock is the default and the only path CI runs |
| Cost to build and run | **$0.00** |

Against the definition of done, item by item:

| Required | State |
|---|---|
| `make dev` → default template renders in the editor | ✅ |
| run a period → binding statuses + gaps panel | ✅ |
| tables/KPIs assembled deterministically | ✅ golden-file tested, both periods |
| narratives drafted and cross-checked | ✅ 36/36 figures verified across 6 sections |
| review with tracked edits | ✅ word-level diff, AI draft written once and never again |
| approvals | ✅ per section; editing revokes approval |
| sign-off with the gap-waiver flow tested | ✅ on the default path, not in a fixture |
| archived with hash | ✅ md + PDF + snapshot + template ref under one hash; tamper-detecting verifier |
| `make month2` + diff view | ✅ |
| CI gates green, mock mode marked | ✅ named in the job titles |
| README, MODEL_COSTS, PLAN ticked | ✅ |
| Screens verified headless, both themes | ✅ `make capture` |
| Demo video | ❌ not recorded — shot list in `docs/DEMO_SCRIPT.md` |

---

## The three decisions worth defending

**1 · The gate that has to be seen failing.** A 100% numeric-fidelity gate is trivially
satisfiable by a composer that writes no numbers, and a gate nobody has watched go red is not
evidence of anything. So `MockComposer(faulty=True)` deliberately emits an unsupportable
figure, and CI runs `run_fidelity.py --self-test` beside the real gate and **requires the
cross-check to fire**. The metric also refuses to pass on a zero denominator. Both together
are what make a green badge mean something (**D-014**).

**2 · A closed selector grammar instead of an expression language.** Bindings are
`where / group_by / aggregate / order_by / limit` and nothing else. Three properties fall
out at once: assembly is deterministic and therefore golden-file testable; a template is
user input and `eval` in user input is a remote-code-execution hole; and the editor can
point at the offending line because the grammar has a schema. Spec 13 §14 names template
complexity creep as risk #1 — this is where the fence went (**D-008**).

**3 · The default pack ships a real, unresolvable gap.** `segment_performance` binds to a
dataset that genuinely does not exist, because the data has no segment dimension. It is
marked `required`, so the default pack **cannot be issued** until a human waives it with a
reason. The gaps panel, the blocking guard and the waiver flow are therefore exercised on
the default path by the default run, rather than by a test fixture nobody looks at
(**D-006**).

---

## The mistake, and what it cost

Phase 0 inspected the sibling repos with a directory listing and concluded that SpendSort
and StatementLens were spec-only. **They are not.** The listing was stale and was never
re-checked; every claim built on it inherited that. The user corrected it.

It cost a day of planning aimed at the wrong constraints, and it produced a worse product
design: the pack was shaped to avoid revenue entirely, because raw ledgerfab books none —
while a working multi-period statement emitter sat in `../statementlens`. No code had been
written, so the correction was a documentation change (BLOCKERS **B0**), and the superseded
decisions are struck through in PLAN.md rather than deleted.

The instructive part: Phase 0 verified the ledgerfab seed by **running** it, and that
finding held. The two findings that were wrong are precisely the two taken from a listing
instead of an execution. `fixtures/gen_fixtures.py` now executes SpendSort rather than
reading about it, which is the same lesson applied.

---

## What is blocked, and what is not

| | |
|---|---|
| **Not blocked** | Everything in the definition of done. The product runs end to end. |
| **B4 · StatementLens P4/P5** | Its computations and flags are not built upstream (it is at P3 of P11). Computed in-repo to its own PLAN's shapes, so the swap is one reader change. |
| **B4 · `numcheck` upstream** | It belongs in StatementLens (its P6) and is written here because that phase has not arrived. If upstream writes its own, spec 13 §10's *"shared harness with Spec 12"* stops being true and one of the two has to go. |
| **Live LLM** | Implemented and `live`-marked, but never run — no API key was used. The claim "it works with a real model" is **not** evidenced by this repo. |
| **Demo video** | Not recorded — needs a person and a screen recorder. Everything it must *show* is built; the shot list, with exact commands and clicks, is `docs/DEMO_SCRIPT.md`. |
| **Browser automation** | The Chrome extension never connected (B6). Resolved with headless Playwright, which turned out better — it **asserts** rather than photographs, and caught three real defects. |

---

## What headless capture found that the test suite did not

`make capture` was written because the Chrome extension would not connect (B6). It renders
each screen, asserts what must be on it, and fails on a console error or a horizontal
scrollbar. Three defects surfaced in the first two runs, none of which any unit test would
have caught, and all three would have shipped:

- **A duplicate React key** on the Sign-off blockers list. Three unresolved gaps produce three
  blockers sharing the code `gap_unresolved`; React silently collapses same-keyed siblings, so
  a reviewer would have seen **one** blocker and believed they had one problem to fix.
- **An absolute path in published output** — a Windows user directory in a gap detail, which is
  rendered in the UI *and written into the issued markdown and PDF*. A document meant to be
  distributed was carrying a directory layout and a username. `tests/test_no_path_leaks.py`
  now asserts this across gaps, the issued document and the archive manifest.
- **The month-diff comparing the wrong column** — it took each table's last column, and the
  ratio pack's last column is `status`, so every row read "ok -> ok" and the money-shot screen
  reported that nothing had moved.

And one thing only a person reading the screen would have caught: the mock composer opened on
*last* month's revenue and never stated a movement, despite the section's tone rules asking
for exactly that. It now reads *"For 2024-07, revenue totalled £3,815,071, up 2.9% on the
prior month."* That text is in every screenshot and the demo, so it was worth the fix.

The general lesson matches the one from the Phase 0 mistake: **run it, look at it, and assert
on what you see.** Listing a directory, and rendering a page without checking it, fail the
same way.

---

## SIBLING_NOTES

Friction found by actually consuming these projects, ordered by how much it would cost
someone else. Each is a concrete change, not a complaint.

### 1 · `numcheck` is scheduled at P6 of a project two repos depend on — **highest value**

StatementLens's own brief says *"must be built as a REUSABLE package… project 13 will import
this pattern."* Project 13 is this one, and it needed the package before StatementLens
reached the phase that creates it. That ordering guarantees either a duplicate
implementation or a blocked downstream project.

**Suggested:** pull `numcheck/` forward. It has no dependency on the computation engine — it
takes text and a list of figures — so nothing in P4/P5 blocks it. This repo's copy is
written to the P6 design and is a directory move away from being upstream's.

### 2 · `numcheck/tokenize.py` cannot be that filename — **costs an afternoon to diagnose**

```
numcheck/tokenize.py  shadows the stdlib `tokenize`
  → linecache imports tokenize → inspect imports linecache
  → typing_extensions calls inspect.signature() at import
  → AttributeError: partially initialized module 'inspect' has no attribute 'signature'
```

Not hypothetical — it crashed on first run here. It triggers whenever `numcheck/` itself is
on `sys.path`, which is what StatementLens's current `pyproject.toml` does
(`pythonpath = ["src", ".", "numcheck"]`) and what its P6 acceptance criterion describes
(*"CI runs its tests from inside `numcheck/`"*).

**Suggested:** name it `tokens.py`, and drop `"numcheck"` from `pythonpath` so the package is
imported package-qualified. Both changes are in this repo already. A test
(`test_numcheck_does_not_shadow_a_stdlib_module`) asserts no module in the package collides
with `sys.stdlib_module_names`, which is cheap insurance for the next one.

### 3 · Two different things are called `ledgerfab`, with overlapping account codes

`../spendsort/backend/ledgerfab/` is **not** the shared engine. It is a separate
card-transaction generator with its own `coa.py`, `vendors.py` and `generate.py` — no `rng`,
no `profiles`, no `generators/`. And the two charts of accounts collide: `6000` is
*Advertising & Marketing* in SpendSort's and *Professional fees* in the shared engine's.

Consuming both, that is a live foot-gun: categorising shared-engine data against SpendSort's
default CoA silently files real money under wrong headings. This repo works around it by
passing a CoA built from the same world (`SPENDSORT_COA_PATH`), which SpendSort supports
cleanly — but the collision is worth removing.

**Suggested:** rename SpendSort's to something like `cardfab`, or namespace the codes.

### 4 · SpendSort's mock categorizer cannot categorise shared-engine data

`MockCategorizer` matches a fixed table of consumer and SaaS descriptors — Amazon, Uber,
Zoom, Notion. The shared engine's counterparties are synthetic B2B names ("Northgate Systems
Limited"), so **every row comes back blank and queued** in mock mode. Two portfolio projects
that both sit on `ledgerfab` cannot be composed offline without a workaround.

This repo's is legitimate and uses the product as designed: seed `vendor_memory` from the GL
(which records what each vendor's invoices were actually booked to) so every row takes the
memory-first path. Result: 100% memory-hit, zero LLM calls, deterministic, reconciles to the
cent. But it is a workaround a consumer had to discover.

**Suggested:** either add the shared engine's counterparty names to `_MOCK_RULES`, or ship a
documented "seed memory from a mapping" entry point — the second is more useful and is
already most of what `remember()` does.

### 5 · Three things in the export that only reading the code reveals

Spec 11 F6 says *"categorized CSV with per-line {account, confidence, source, reason}"*. The
real export is **15 columns**, and three of its behaviours are load-bearing for a consumer:

- **UTF-8 with a BOM.** Read as plain UTF-8, the first column name is `﻿date` and every
  lookup of `date` misses.
- **Anti-formula-injection apostrophes are in the data.** A vendor named `-EDF Energy`
  exports as `'-EDF Energy`. Rendered unstripped, the pack shows a stray apostrophe on
  exactly the vendors whose names are already unusual. (The export-side hardening is
  *correct*; it just needs to be documented as part of the format.)
- **No period column and no `schema_version`.** The export is every transaction, so a
  consumer slices by `date` — and cannot detect a schema change from the file itself.

**Suggested:** a short "consuming this export" section in SpendSort's README covering the
BOM and the quoting, plus a `schema_version` header cell. The version cell in particular
turns a silent mis-parse into a named error.

### 6 · StatementLens's export endpoints have no envelope

Spec 12 §7 defines `GET /api/sets/{id}/computations` and `/flags`, and §6 gives the table
columns — but no response envelope: no `schema_version`, no period-set metadata, no
statement of the money type. For a repo whose headline gate is numeric fidelity, the money
type is the most consequential omission; this repo assumed `Decimal`-as-string and would
have been wrong in a hard-to-see way if it were float.

**Suggested:** `{"schema_version": "...", "periods": [...], "money": "decimal-string", "data": [...]}`.

### 7 · `ledgerfab.statements` should graduate into the shared engine

The emitter is the best thing this project consumed — multi-period P&L, balance sheet and
cash flow, `Decimal`, hash-stable, all three derived from one trial balance so they cannot
disagree. It already declares itself reusable and imports nothing from its host.

The tell that it should move: its own vendored test excludes `statements/` from the drift
manifest, commented *"`statements/` is THIS project's extension, not vendored code."* True in
exactly one repo and false in every repo that reuses it — this one had to change that line
(recorded in `backend/ledgerfab/VENDORED.md`).

**Suggested:** move `statements/` into `../ledgerlab/backend/ledgerfab/`, where the
assumption is true for everyone.

### 8 · The 8-period cap reads differently at monthly grain

`build_periods` raises above `MAX_PERIODS = 8`, per spec 12 F1's *"multi-period (up to 8)"*.
Eight periods is generous for statement *analysis*. For a monthly reporting cadence it is
two-thirds of a year, and a pack cannot show a prior-year comparative at all.

**Suggested:** make the cap grain-aware, or raise it for `grain="month"`. Nothing in the
derivation depends on the bound.

---

## The next three things

1. **Record the demo video.** Every other launch requirement is met; this is the gap between
   "done" and "launch-ready" (spec 00 E). `docs/DEMO_SCRIPT.md` is the 80-second shot list,
   and `make capture`'s seeding produces exactly the state it assumes.
2. **Offer `numcheck` upstream** before StatementLens reaches P6, together with notes 1 and 2
   above. This is time-sensitive in a way the others are not — once a second implementation
   exists, the "shared harness" claim is already false.
3. **Run the live path once and publish the result.** The architecture's claim is that a real
   model, given only a figure list, passes the fidelity gate. That is currently an argument,
   not a measurement (B7). Drop a key into `.env` and run `make test-live`; it costs under a
   cent. The interesting outcome is not "it passed" — it is whatever the cross-check catches
   if it does not.
