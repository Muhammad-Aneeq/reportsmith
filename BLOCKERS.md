# ReportSmith · BLOCKERS

> Every blocker, stub and **BLOCKED** task, with what it costs and what was done instead.
> Referenced by id from [PLAN.md](PLAN.md). Nothing here is silently worked around.

## STATUS ROLL-UP

| id | Blocker | Severity | Effect on the definition of done | Resolution |
|---|---|---|---|---|
| **B1** | No `make` on this Windows box | low | none — cosmetic | `make.ps1` mirrors every target; the `Makefile` stays authoritative and is what CI runs |
| **B2** | ledgerfab seed absent from `./backend_seed_ledgerfab/` | medium | none — resolved | Vendored from `../ledgerlab/backend/ledgerfab/` (PLAN **D-002**); verified working before anything was planned on it |
| ~~**B3**~~ | ~~`../spendsort` is spec-only~~ | — | **WITHDRAWN 2026-09-22 — this was never true.** See B0 | SpendSort is a complete, runnable repo; the adapter uses its real export schema (PLAN **D-005**) |
| **B4** | StatementLens has **not yet reached P4 (computations), P5 (flags) or P6 (`numcheck`)** — it is through P3 of P11 | medium | none to the definition of done; both are built in-repo | numcheck **originates here**, module-for-module matching their P6 design (PLAN **D-004**); ratios/flags computed in-repo to their P4/P5 shapes (PLAN **D-018**) |
| **B5** | No published `aurora-ui` package | low | none | Local `frontend/src/components/aurora/` — the convention in all ten sibling repos (PLAN **D-003**) |
| **B0** | **A stale directory read made P0 assert both siblings were spec-only** | — | corrected before any code was written | Root cause and correction below |
| **B6** | Chrome extension not connected, so no browser automation | low | none — resolved a better way | Headless Playwright (`make capture`) screenshots **and asserts** all six screens in both themes; the manual script is in `docs/GOVERNANCE.md` |
| **B7** | No API key available to the build | medium | the live LLM path is implemented but **never run** | `.env.example` ships; `make test-live` runs it. Recorded in README STATUS as unproven rather than quietly implied |

---

## B1 · `make` is not installed

**Found:** P0. `make --version` → `command not found`. Python 3.12.10, uv 0.11.23, node 24.14.1, npm 11.11.0 and git 2.53 are all present.

**Why it does not matter much:** spec 00 A1 requires a `Makefile` with `dev/test/eval/up/down` and the brief's definition of done names `make dev` and `make month2`. The `Makefile` is written and is what CI executes on Linux; `make.ps1` mirrors it target-for-target for local Windows work. Both are checked by a test that asserts the two files expose the same target set, so they cannot drift.

---

## B2 · The ledgerfab seed was not at the stated path

**Found:** P0. The brief says *"REUSE: ledgerfab from `./backend_seed_ledgerfab/`"*. That directory does not exist; this repo contained only `spec_00_shared_foundations.md` and `spec_13_reportsmith.md`.

**What was done:** a portfolio-wide search found five copies. `../ledgerlab/backend/ledgerfab/` is upstream — `../finagent-evals`, `../finsight` and `../InvoiceOps` each carry a `VENDORED.md` naming it as their source, and it is the strict superset. It is vendored into `backend/ledgerfab/` with a `VENDORED.md` recording provenance and every local change (PLAN **D-002**).

**Verified before use, not assumed** (P0):

```
generate('realistic', seed=42) → 60 invoices · 120 GL entries · 64 transactions · 28 exceptions
dataset_hash = 38b8930d494d
monthly override 2025-01-01…2025-01-31 → GL dates confined to the window, hash 1ada489322c5
monthly override 2025-02-01…2025-02-28 → GL dates confined to the window, hash 4ba6bfa437bf
```

Two consequences were designed in rather than discovered later: monthly periods are producible (PLAN **D-009**, which `make month2` depends on), and the GL books only `{2000, 5000, 6000, 6100, 6200, 6300}` — no revenue postings — which fixes the default pack's shape (PLAN **D-007**).

---

## B0 · A stale directory read made P0 assert both siblings were spec-only

**What happened:** P0's inspection of `../spendsort/` and `../statementlens/` returned two spec files each and nothing else. That was recorded as fact and three decisions were built on it (**D-001**, **D-005**, **D-007**). The user corrected it. Re-inspection found both repos complete or substantially built — SpendSort with a `FINAL_REPORT.md`, StatementLens through P3 of P11 — and the spec files no longer at the root at all, because each repo had since moved them into its own `docs/`.

**Root cause:** the listing was taken before those repos were populated and was never re-checked. Every later claim inherited its staleness. Phase 0's other external reads were verified by *executing* them — the ledgerfab seed was run, not assumed — and the two that were not executed are exactly the two that were wrong.

**What it cost:** nothing shipped, because the correction landed before any application code. It cost a day of planning aimed at the wrong constraints, and it produced a plan that under-delivered: it had the default pack avoiding revenue entirely (**D-007**) when a working multi-period statement emitter was sitting in `../statementlens`.

**What changed as a result:**

| Was | Is |
|---|---|
| SpendSort adapter against guessed spec prose | Against the real 15-column `COLUMNS` in `services/export.py`, fixture-tested against a really-generated export |
| Pack is spend/payables-only; no revenue | Real P&L, balance sheet and cash flow from the vendored `ledgerfab.statements` emitter |
| `make month2` fakes months by overriding ledgerfab's profile window | The emitter has native `grain="month"` and period ids `2024-01`, `2024-02` |
| Money converted from float at the boundary | The emitter is `Decimal` at source; conversion now applies only to raw ledgerfab and the SpendSort CSV |

**The standing correction:** re-check a sibling's tree immediately before depending on it, and prefer *running* it to *listing* it. `fixtures/gen_fixtures.py` does exactly that — it executes SpendSort rather than reading about it.

---

## B4 · StatementLens has not yet reached computations, flags or `numcheck`

**Found:** P0, confirmed on re-inspection 2026-09-22. StatementLens is a real repo, through **P3 of P11**. Built and working: the vendored engine, the **statement emitter** (`backend/ledgerfab/statements/` — multi-period P&L/BS/CF, double-entry derived, seeded anomalies, `statement_hash`), intake, alignment, persistence and an API skeleton. **Not yet built:** P4 computations, P5 flags, **P6 `numcheck/`**.

So the brief's *"the numcheck numeric cross-check from `../statementlens` (import or vendor it)"* still has no referent — not because the project is absent, but because that package is three phases out. StatementLens's own PLAN designs it in full and its brief says *"must be built as a REUSABLE package (backend/numcheck/) with its own tests: **project 13 will import this pattern**."*

**Decided with the user (2026-09-22):** build it **here**, shaped for lifting upstream.

**What was done:**

- **`numcheck`** originates in `backend/numcheck/` as a standalone package — own `pyproject.toml`, own tests, `pydantic` as the only third-party surface, zero ReportSmith imports, CI running its tests with the backend uninstalled. Modules match StatementLens P6 one-for-one (`models · tokenize · match · exempt · verify · surgery`), including its two hard rules: a **closed** two-entry exemption list, and **no tolerance knob**. `ORIGIN.md` records the lift procedure (PLAN **D-004**).
- **Ratios and flags** are computed in `backend/app/analysis/`, emitting the exact shapes StatementLens's PLAN pins for P4/P5, so the swap when they land touches only the adapter's reader (PLAN **D-018**).

**Effect on the definition of done: none.** Both are built here; the pack assembles, narrates and gates on real numbers.

**Open tasks (not blocking):** (a) repoint the statementlens adapter at live P4/P5 when they exist; (b) **reconcile `numcheck` with StatementLens's implementation when it arrives** — if the two diverge, spec 13 §10's *"shared harness with Spec 12"* stops being true and one of them has to move. Offering this one upstream is the intended resolution and is flagged in SIBLING_NOTES.

---

## B5 · No published `aurora-ui` package

**Found:** P0. Spec 00 A2 describes `aurora-ui` as *"a local workspace package imported by all frontends"*. No such package is published, and all ten sibling repos instead carry `frontend/src/components/aurora/` locally.

**What was done:** the same — a local implementation of the spec 00 A2 tokens (`#0B1E3B`, `#10B981`, frosted glass, Space Grotesk / Inter) and all nine components, rendered by an `/aurora` route, which is spec 00 A2's stated acceptance criterion. Nothing in the directory imports from a screen, so lifting it into a package later is a move, not a rewrite.


---

## B6 · No browser automation on the build machine

**Found:** P6. The Chrome extension reported *"Browser extension is not connected"* on every
attempt, so the UI could not be driven the way the rest of the portfolio's projects are.

**Resolved, and arguably better.** `frontend/capture.mjs` drives headless Chromium through
Playwright and is wired to `make capture`. It is not a screenshot script: it **fails the
build** if a screen renders under 120 characters, shows an error state, scrolls horizontally
at 1440px or 1280px, logs a console error, or is missing a phrase the README claims is on it.

It earned its keep immediately, finding three real defects a screenshot alone would have
photographed and shipped:

1. **A duplicate React key** on the Sign-off blockers list. A pack with three unresolved gaps
   produces three blockers that all share the code `gap_unresolved`, and React silently
   collapses same-keyed siblings — so a reviewer would have seen **one** blocker and believed
   they had one problem.
2. **An absolute path leaking into published output.** The gap detail read
   `...no SpendSort export for 2024-06 at C:\Users\<name>\Desktop\...`. Gap details are
   rendered in the UI *and written into the issued markdown and PDF*, so that put a directory
   layout and a username into a document meant to be distributed. Fixed, with
   `tests/test_no_path_leaks.py` asserting it across gaps, the issued document and the
   archive manifest.
3. **The month-diff comparing the wrong column.** The summary took each table's *last*
   column; the ratio pack's last column is `status`, so every row read "ok -> ok" and the
   diff view reported that nothing had moved.

The first screenshots also showed both demo packs already issued, so the Sign-off screen
rendered its archive panel instead of the checklist — the screen's whole argument. Fixed by
seeding a third pack mid-review, which is now what `docs/DEMO_SCRIPT.md` sets up.

**Not a substitute for a human looking.** Playwright asserts what it was told to assert. The
screens were also read by eye, which is how the mock composer's prose got fixed — it opened
on *last* month's revenue and never stated a movement, despite the tone rules asking for
exactly that.

---

## B7 · No API key, so the live model path is unproven

**Found:** P8. `OPENAI_API_KEY` is not set in this environment. Keys exist in four sibling
repos' `.env` files; the user was asked and chose to supply their own key to this project
rather than have a sibling's borrowed, so nothing was taken.

**What this means, stated plainly:** `OpenAIComposer` is implemented, `live`-marked and
excluded from CI. **It has never been executed.** The claim "a real model, given only a
figure list, passes the numeric-fidelity gate" is an argument this repo makes from its
architecture — it is not a measurement this repo contains. README STATUS says so.

**To close it:** put a key in `.env` (see `.env.example`) and run

```bash
make test-live                        # the live-marked tests
REPORTSMITH_LLM=live make evals       # the fidelity gate against the real model
```

A full pack is three narrative sections and costs well under a cent (`MODEL_COSTS.md`). The
interesting outcome is not "it passed" — it is whatever the cross-check catches if it does
not.
