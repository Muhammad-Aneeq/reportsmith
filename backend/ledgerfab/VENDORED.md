# ledgerfab — VENDORED COPY (engine + statement emitter)

**Nothing in this directory except this file is original code.** It is a vendored copy of two
things that travel together: the shared `ledgerfab` synthetic finance engine (spec 00 A3) and the
`statements/` multi-period statement emitter built on top of it.

## Provenance

| | |
|---|---|
| **Vendored from** | `../statementlens/backend/ledgerfab/` |
| **Vendored at** | 2026-09-22 |
| **Upstream version** | `__version__ = "0.1.0"` |
| **Local changes** | **none** — every file is byte-identical to source |

### Why this copy, and not one of the other five

`ledgerfab` exists in six places across the portfolio. The engine half is identical in all of them
— verified, not assumed:

```
diff ../ledgerlab/backend/ledgerfab/{models,profiles,rng,hashing}.py  ← identical
```

`../ledgerlab/backend/ledgerfab/` is upstream for the engine, and three siblings (`finagent-evals`,
`finsight`, `InvoiceOps`) carry a `VENDORED.md` naming it. But **only the StatementLens copy carries
`statements/`**, and that extension is what makes a management pack possible here at all. Taking the
StatementLens copy gets the identical engine *and* the emitter in one move, with one provenance
story instead of two.

The brief pointed at `./backend_seed_ledgerfab/`. That directory did not exist (BLOCKERS **B2**).

## What `statements/` adds, and why ReportSmith needs it

The base engine generates a **purchase cycle**: invoices arrive, two GL entries are booked per
invoice (expense debit, payables credit), and the bank side is deliberately unposted. Measured
directly — the GL only ever touches `{2000, 5000, 6000, 6100, 6200, 6300}`. There is no revenue, no
inventory, no fixed asset, no debt and no retained earnings.

A "Monthly Management Pack" built on that alone would have a headline KPI that is structurally
always zero (PLAN.md **D-007**, now retired). `statements/` closes the gap:

```python
from ledgerfab.statements import emit_statements, statement_hash

st = emit_statements("squeeze", seed=42, periods=2, grain="month")
st.periods          # Period(id='2024-01', label='Jan 2024', start, end, index, grain), …
st.amount("2024-01", "revenue")       # Decimal('3631007.40')
st.amount("2024-01", "total_assets")  # Decimal('19391654.47')
st.ground_truth.anomalies             # what was injected, and what should catch it
statement_hash(st)                    # same inputs → same hash, always
```

Three properties ReportSmith depends on, all of which come free:

1. **Native monthly grain** with stable period ids (`2024-01`). `make month2` is two calls to the
   same function, not a hand-rolled date-window override (PLAN.md **D-009**).
2. **`Decimal` at source**, so the numeric-fidelity gate is not fighting float dust (**D-010**).
3. **Internal consistency by construction.** The emitter derives all three statements from a trial
   balance rather than authoring them separately, so `assets = liabilities + equity` and
   `cf_net_change_in_cash = cash_t − cash_{t−1}` hold per period. For a product whose entire claim
   is *every number is checkable*, demoing on data that could disagree with itself would be
   self-defeating.

Upstream's own reuse contract (`statements/README.md`) anticipates exactly this use:

> *"Written to be reused. Nothing here imports from `statementlens`, so lifting this directory into
> the shared engine is a directory move."*

## Verified before adoption

The seed was **run**, not assumed to work — and its own suites were run *in this repo*, which is
what makes the copy trustworthy rather than merely present:

```
169 passed
  test_emitter_invariants   — journals balance; A = L + E; RE roll-forward; the cash-flow identity;
                              and the strong one: the operating section rebuilt from cash postings
                              equals the indirect build-up. Two routes, same number.
  test_emitter_determinism  — same inputs → same statement_hash, at all three grains
  test_emitter_periods      — month / quarter / year period construction
  test_emitter_anomalies    — the seeded anomalies and their ground truth
  test_emitter_export       — CSV + XLSX round-trip
  test_vendored_ledgerfab   — upstream engine determinism and ground truth
```

These suites are vendored alongside the code and run in CI, so the copy cannot rot quietly as this
repo grows around it.

## File manifest

SHA-256 (first 12 hex) of every vendored `.py`. `tests/test_vendored_ledgerfab.py` recomputes these and fails if a file here changed without this table changing with it — which is what keeps "no local changes" a fact rather than an intention.

```
2FF4617F77CE  __init__.py
6A1F1C42AEFE  __main__.py
EE0162A70281  cli.py
A83120B6BA93  export.py
8482EA7B8011  generators/__init__.py
D02D5088CABF  generators/accruals.py
70484036A6A8  generators/companies.py
577BA52BB419  generators/counterparties.py
B759F3B55F1F  generators/gl.py
A61271AF1F14  generators/invoices.py
C47CDC51905E  generators/notes.py
8F768109C7AE  generators/transactions.py
3AE1D89EC55F  ground_truth.py
8E028F14161C  hashing.py
85E6AC2232C0  messiness.py
B28571D36909  models.py
5E91F731FF63  profiles.py
5ACB0CD5F3B4  rng.py
E53D1F3BB5EF  statements/__init__.py
A78EFB6B7441  statements/anomalies.py
80B9A813228A  statements/chart.py
70EDBACF78EB  statements/derive.py
A0FE308E9C03  statements/export.py
E7BF5786985A  statements/hashing.py
7CE1B347ECD5  statements/models.py
6541351958F3  statements/money.py
2E519D658741  statements/plan.py
272B51494139  statements/postings.py
2FD219BDDFEF  statements/profiles.py
```

## Local changes

**None to the code.** Every `.py` in this directory is byte-identical to
`../statementlens/backend/ledgerfab/`, and the manifest above is what proves it.

That is deliberate (PLAN.md **D-017**): a zero-width fork means an upstream fix is `cp -r`, never a
merge. Two adjustments that *could* have been made to vendored files were made on this side of the
line instead, in `backend/pyproject.toml`:

- `ruff` per-file ignores for `RUF022` / `RUF100`, because upstream's `__all__` grouping and its
  `# noqa: C901` are correct upstream and only look wrong under our config.
- `openpyxl` added to **dev** extras — not runtime — purely so the vendored XLSX export test runs
  unmodified. ReportSmith consumes the emitter in-process and never writes a workbook.

### One change to a vendored *test*, and why

`tests/test_vendored_ledgerfab.py::test_vendored_manifest_covers_every_vendored_file` excluded
`statements/` from the manifest, with the comment *"`statements/` is THIS project's extension, not
vendored code."* True upstream. **False here** — in this repo both halves are vendored.

Left as written, the exclusion would leave the emitter — the code every figure in the pack comes
from — outside the drift check, which is the exact opposite of what that test exists to do. So the
exclusion is removed and the manifest covers all 29 files. The change is marked `LOCAL CHANGE
(ReportSmith)` in the test itself, so it cannot be mistaken for upstream's intent when this is
re-vendored.

It is worth noticing *why* this happened: the assumption "statements is ours" is true in exactly one
repo and false in every repo that reuses it — which is a small argument for the emitter graduating
into the shared `ledgerfab` rather than living in a consumer. Recorded in SIBLING_NOTES.

## Contributing changes back

Nothing here is a fix to upstream, so there is nothing to contribute back. If a genuine bug is
found, fix it in `../statementlens` (or `../ledgerlab` for the engine half) and re-vendor, rather
than patching here — that is what keeps the fork surface at zero.
