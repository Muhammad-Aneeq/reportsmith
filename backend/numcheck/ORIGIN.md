# numcheck — why it lives here, and how to lift it

## The short version

This package **belongs to StatementLens** (spec 12 F5, its PLAN **P6**). It is written here
because StatementLens has not reached P6 yet, and ReportSmith's headline CI gate depends on
it. It is built as a standalone package so that adopting it upstream is a **directory
move**, not a port.

## Why not import it from `../statementlens`

Because it is not there. StatementLens is a real, working repo — through **P3 of P11** —
and its `backend/numcheck/` is three phases out. Its own brief is explicit about who should
own this:

> *"must be built as a REUSABLE package (`backend/numcheck/`) with its own tests: project
> 13 will import this pattern."*

ReportSmith **is** project 13. The brief for this repo says *"import or vendor it"*, and
neither is possible against code that does not exist. Confirmed with the user on
2026-09-22: build it here, shaped for lifting. See PLAN.md **D-004**, BLOCKERS **B4**.

## What makes it liftable

| Property | Why it matters |
|---|---|
| **Zero imports from `app`** | `grep -r "from app" numcheck/` returns nothing, asserted by `test_numcheck.py`. The dependency runs one way only. |
| **`pydantic` is the entire third-party surface** | No FastAPI, no SQLAlchemy, no ledgerfab. It has its own `pyproject.toml`. |
| **Its own tests, runnable alone** | `pytest numcheck/tests` — 46 tests, application not installed, verified in an empty directory. |
| **Module-for-module match with their P6 design** | `models · tokens · match · exempt · verify · surgery` — one deliberate rename, below. |

## The lift procedure

```bash
cp -r reportsmith/backend/numcheck  statementlens/backend/numcheck
cd statementlens/backend && pytest numcheck/tests     # 46 passed
```

**Verified, not assumed.** The package was copied into an empty directory with no ReportSmith
code present and its suite run from the parent: 46 tests, all passing, with `pydantic` and
`pytest` the only things installed. CI runs the same check on every push (the
`numcheck-standalone` job), so the one-way dependency cannot rot as this repo grows around it.

Then delete this file and tick P6. Nothing else should need to change.

## The one deliberate deviation from the P6 design — please take this one

Their P6 names the tokeniser module **`tokenize.py`**. That name cannot be used:

```
numcheck/tokenize.py  shadows the stdlib `tokenize`
  → linecache imports tokenize
  → inspect imports linecache
  → typing_extensions calls inspect.signature() at import time
  → AttributeError: partially initialized module 'inspect' has no attribute 'signature'
```

It is not hypothetical — it crashed on first run here. It bites whenever `numcheck/` itself
is on `sys.path`, which is exactly what StatementLens's own `pyproject.toml` does today:

```toml
pythonpath = ["src", ".", "numcheck"]     # ← this line is the trigger
```

and also what their P6 acceptance criterion describes (*"CI runs its tests from inside
`numcheck/`"*), since pytest puts the rootdir on the path.

**Two changes fix it, and both are here already:**

1. the module is **`tokens.py`**, not `tokenize.py`;
2. `pythonpath` is `["."]` — the package is imported package-qualified (`numcheck.tokens`),
   so its directory is never itself a path root.

Recorded in ReportSmith's SIBLING_NOTES as the highest-value thing to fix upstream before
P6 is written, precisely because it costs nothing to avoid and an afternoon to diagnose.

## Two design rules inherited verbatim, because both are load-bearing

**No tolerance parameter.** A token is checked at *its own* declared precision: a model
that writes `£3.8m` claims one decimal place and is checked to one; one that writes
`£3,815,070.61` claims two. There is no epsilon to tune, because an epsilon is a knob, and
a knob gets widened the first time a build goes red at 5pm.

**The exemption list is closed at two entries**, and `test_numcheck.py` asserts its
exact contents. Exemption creep is how this class of checker quietly dies: every exemption
is a hole, each arrives individually reasonable, and eventually the gate is green because it
stopped looking. Anything a narrative may legitimately cite is supplied as a `FigureRef` —
a figure someone vouches for — rather than exempted.

## If StatementLens writes its own instead

Then spec 13 §10's *"shared harness with Spec 12"* stops being true, and one of the two has
to go. That is an open item in BLOCKERS **B4**, not something to discover later from two
subtly different fidelity scores.
