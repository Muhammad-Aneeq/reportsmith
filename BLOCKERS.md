# ReportSmith · BLOCKERS

> Every blocker, stub and **BLOCKED** task, with what it costs and what was done instead.
> Referenced by id from [PLAN.md](PLAN.md). Nothing here is silently worked around.

## STATUS ROLL-UP

| id | Blocker | Severity | Effect on the definition of done | Resolution |
|---|---|---|---|---|
| **B1** | No `make` on this Windows box | low | none — cosmetic | `make.ps1` mirrors every target; the `Makefile` stays authoritative and is what CI runs |
| **B2** | ledgerfab seed absent from `./backend_seed_ledgerfab/` | medium | none — resolved | Vendored from `../ledgerlab/backend/ledgerfab/` (PLAN **D-002**); verified working before anything was planned on it |
| **B3** | `../spendsort` is spec-only — no runnable export | medium | live SpendSort binding **BLOCKED**; the section still renders, as a GAP or from a fixture | Adapter built against spec 11 §6/F6; fixture derived from the same ledgerfab period (PLAN **D-005**, **D-006**) |
| **B4** | `../statementlens` is spec-only — no computations export, **and no `backend/numcheck/`** | high | numcheck cannot be imported or vendored; live StatementLens binding **BLOCKED** | numcheck **originates here**, shaped for lifting upstream (PLAN **D-004**); data adapter fixture-backed as B3 |
| **B5** | No published `aurora-ui` package | low | none | Local `frontend/src/components/aurora/` — the convention in all ten sibling repos (PLAN **D-003**) |

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

## B3 · `../spendsort` is spec-only

**Found:** P0. `../spendsort/` contains exactly two files: `spec_00_shared_foundations.md` and `spec_11_spendsort.md`. There is no `backend/`, no export code, no sample export.

**Cost:** the brief's preferred path — *"fixture-test against real sample exports you generate from them if runnable"* — is unavailable. The live SpendSort binding cannot be tested against reality.

**What was done instead:** the adapter is built against the documented schema (spec 11 §6 tables + F6's *"categorized CSV with per-line {account, confidence, source, reason}"*), carries `SCHEMA_VERSION = "spendsort/v1(spec11-derived)"` — a string that admits its own provenance — and is fixture-tested against a fixture **derived from the same ledgerfab period**, so the pack's category total must reconcile to the ledgerfab expense total to the cent (PLAN **D-006**).

**BLOCKED task:** *replace the fixture reader with the live SpendSort export.* A reader swap behind an unchanged `SourceAdapter` interface; the fixture is retained as the regression test. Unblocks when SpendSort ships an export.

**Not hidden from the user:** with no fixture configured, the section renders as an explicit GAP in the gaps panel — spec 13 F2's required behaviour, demonstrated by the default template rather than by a contrived test.

---

## B4 · `../statementlens` is spec-only — including the numeric cross-check

**Found:** P0. `../statementlens/` contains exactly two files: `spec_00_shared_foundations.md` and `spec_12_statementlens.md`. The brief names *"the numcheck numeric cross-check from `../statementlens` (import or vendor it)"*; there is nothing to import or vendor. A portfolio-wide grep for `numcheck`, `figure_ref`, `cross_check` and `numeric_fidelity` across all fourteen repos returns **spec prose only** — no implementation exists anywhere.

**Severity is high** because this is not a data dependency: spec 13 F4 makes the cross-check the mechanism behind the headline claim, and spec 13 §10 gates CI on it.

**What was done instead:** `numcheck` **originates in this repo**, written to spec 12 F5's rule (*"any numeric token in the narrative must match a figure_ref value… mismatches fail the draft, one retry, else that sentence is dropped"*), as a standalone package with **no ReportSmith imports**, so StatementLens can adopt it as a directory move rather than a rewrite. `backend/app/numcheck/ORIGIN.md` records this and the lift procedure (PLAN **D-004**).

**BLOCKED tasks:** (a) *replace the StatementLens computations fixture with the live export*; (b) *reconcile `numcheck` with StatementLens's own implementation once it exists* — if they diverge, spec 13 §10's *"shared harness with Spec 12"* is no longer true, and one of the two has to move.

---

## B5 · No published `aurora-ui` package

**Found:** P0. Spec 00 A2 describes `aurora-ui` as *"a local workspace package imported by all frontends"*. No such package is published, and all ten sibling repos instead carry `frontend/src/components/aurora/` locally.

**What was done:** the same — a local implementation of the spec 00 A2 tokens (`#0B1E3B`, `#10B981`, frosted glass, Space Grotesk / Inter) and all nine components, rendered by an `/aurora` route, which is spec 00 A2's stated acceptance criterion. Nothing in the directory imports from a screen, so lifting it into a package later is a move, not a rewrite.
