# Adapter contracts

What each source publishes, **where its schema was read from**, and exactly what changes when
upstream ships. Every adapter declares a `SCHEMA_VERSION` that admits its own provenance, and
that string travels into the pack and into the archive hash — so a pack records not just its
numbers but what shape of upstream data produced them.

## The contract

```python
class SourceAdapter(Protocol):
    name: str
    SCHEMA_VERSION: str
    def catalog(self) -> tuple[str, ...]: ...
    def fetch(self, dataset: str, period: str) -> Frame: ...
```

`fetch` may raise. The caller (`resolve_binding`) converts **every** failure into a `Gap` with
a named reason. There is no third outcome: the return type is `Bound | Gap`, and a bare
`except Exception` sits between an adapter and the assembler on purpose. A crash gets noticed;
a missing section in a board pack gets *signed*.

| `GapReason` | Means |
|---|---|
| `adapter_unavailable` | the source is not registered, or could not list its datasets |
| `unknown_dataset` | the source has no such dataset (the detail lists what it does have) |
| `binding_failed` | it raised while fetching |
| `empty_result` | it ran and there was nothing there |
| `schema_mismatch` | the data was not the shape the version string promised |
| `selector_invalid` | the template asked for a field the dataset does not publish |

---

## `ledgerfab`

`SCHEMA_VERSION = "ledgerfab/0.1.0+statements(vendored 2026-09-22)"`

Vendored in-process, so there is no file format in between that could drift. Two upstream
halves, one adapter: the **statement emitter** gives the reported position, the **base
engine** gives the operational detail behind the payables line.

| dataset | grain | columns |
|---|---|---|
| `pnl_lines` | statement line | `line_code label statement amount prior_amount delta delta_pct is_subtotal` |
| `bs_lines` | statement line | as above |
| `cf_lines` | statement line | as above |
| `period_metrics` | **one row per metric** | `metric label value prior_value delta delta_pct` |
| `exceptions` | transaction | `txn_id rule_id label message severity severity_rank amount counterparty evidence` |
| `invoices` | invoice | `invoice_id number counterparty issue_date due_date amount currency status` |
| `gl_expense_lines` | GL entry | `account_code account_name date amount invoice_id memo` |

`period_metrics` is **long, not wide** — one row per metric rather than one row of many
columns. A KPI grid selects metrics by name, so this makes adding a KPI a lookup, and makes a
template naming a metric that does not exist produce a clean "unknown metric" rather than a
silently absent column.

Every dataset carries its prior-period comparative alongside the current figure, computed
once. Computing it twice, in two places, is how a table and its narrative end up disagreeing.

**Severity for exceptions is assigned here**, not upstream — the taxonomy is a *cause*, not a
rank. `duplicate` and `dispute` are high (real money, or a counterparty contesting);
`unknown` is medium rather than low, because unknown means nobody has looked yet.

---

## `spendsort`

`SCHEMA_VERSION = "spendsort/v1(services/export.py COLUMNS @2026-09-22)"`

**Read from the real code, not from the spec.** The schema is the `COLUMNS` tuple in
`../spendsort/backend/app/services/export.py` — 15 columns, where spec 11 F6 names four. The
fixtures under `fixtures/spendsort/` are files SpendSort itself wrote; regenerate with
`make fixtures`.

| dataset | columns |
|---|---|
| `categories` | `account account_name amount txn_count queued_count auto_rate avg_confidence` |
| `transactions` | the full 15-column export, per period |
| `review_queue` | rows SpendSort could not decide |

`auto_rate` travels with the money on purpose. A category total assembled from rows a human
never confirmed is a different fact from one that was fully reviewed, and a pack showing the
first without saying so overstates its own reliability. Only decided rows (`auto`,
`resolved`) count toward the total.

### Three quirks reading the code revealed that reading the spec would not

1. **UTF-8 with a BOM.** SpendSort writes `utf-8-sig` so Excel renders the em-dash in account
   names. Read as plain UTF-8, the first column is `﻿date` and every lookup of `date`
   misses.
2. **Anti-formula-injection apostrophes are in the data.** Cells beginning `= + - @` are
   prefixed with `'` on export, so `-EDF Energy` arrives as `'-EDF Energy`. Stripped here,
   narrowly: the quote is only removed when what follows would have triggered the guard, so a
   vendor genuinely called `'Round Table Ltd` keeps its own.
3. **No period column and no schema version.** The export is every transaction, so the period
   slice happens on `date` — and a schema change is only detectable by required columns going
   missing, which is why they are checked explicitly rather than accessed hopefully.

All three are in SIBLING_NOTES as upstream suggestions.

### How the fixtures are made

`fixtures/gen_fixtures.py` runs **real SpendSort**, in its own interpreter (both repos name
their package `app`, so importing it would permanently shadow ours). It passes:

- an intake CSV built from **this pack's own GL expense lines**, so the result must reconcile
  to the pack's expense total to the cent — asserted by `test_spendsort_total_reconciles_to_the_ledger`;
- a **chart of accounts** built from the same world, because SpendSort ships its own CoA in
  which `6000` is *Advertising & Marketing* while the shared engine's `6000` is *Professional
  fees*;
- a **pre-seeded vendor memory** from the GL. SpendSort's mock categorizer knows consumer and
  SaaS descriptors and cannot categorise synthetic B2B counterparties at all — but
  memory-first is its signature design, and the GL already records what each vendor's invoices
  were booked to. Result: 100% memory-hit, **zero LLM calls**, deterministic.

---

## `statementlens`

`SCHEMA_VERSION = "statementlens/v1(spec12 §6 + upstream PLAN P4/P5 shape; in-repo impl)"`

The version string admits what it is: upstream's *shape*, produced by an in-repo
implementation, because StatementLens has not written P4/P5 yet (it is at P3 of P11).

| dataset | columns |
|---|---|
| `ratios` | `formula_id label category value display prior_value prior_display unit status note definition` |
| `flags` | `rule_id label severity severity_rank message evidence` |

Two upstream rules are inherited verbatim because both are load-bearing:

- **A zero denominator yields `status="undefined"`** with the zero input named. Never `0`,
  never NaN, never a raised exception — and it renders as `n/a`, not a dash, because a dash in
  a ratio column is read as zero by everyone who has ever seen a spreadsheet.
- **An undefined metric never fires a flag.** "Current ratio below 1" must not fire because
  current liabilities were zero. That is how a flags engine ends up crying wolf about
  arithmetic, and once a reviewer learns to skim past flags the mechanism is dead.

`segment_ratios` is **deliberately absent** from the catalog. The default template binds a
required section to it, so the default pack carries one real structural gap and the waiver
flow runs on the default path rather than in a fixture.

### What changes when upstream ships P4/P5

`StatementLensAdapter.fetch` — and nothing else. The datasets, the column names, the
assembler, the templates, the golden files and the narrative prompts all stay as they are.
That is the whole reason it was built to upstream's shape rather than a convenient one.

---

## Adding a source

1. Implement the protocol. Return a `Frame`; let it raise on trouble.
2. Give it a `SCHEMA_VERSION` that names where the schema came from and when.
3. Validate on read and raise `SchemaMismatch` naming the offending field — so a change
   upstream becomes a labelled gap rather than a silent mis-parse.
4. Register it in `default_adapters()`.
5. Add it to `test_no_silent_omission.py`'s misbehaviour matrix. Twelve adversarial
   behaviours run against every registered source; a new one should face the same.
