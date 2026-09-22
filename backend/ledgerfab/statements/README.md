# `ledgerfab.statements` — the multi-period statement emitter

A ledgerfab extension that emits **multi-period P&L, balance sheet and cash flow**
consistent with its GL worlds, with a seeded anomalies knob and a ground-truth answer
key (spec 12 F1; spec 00 A3's *"ground-truth emitter"*).

Written to be reused. Nothing here imports from `statementlens`, so lifting this
directory into the shared engine is a directory move.

```python
from ledgerfab.statements import emit_statements, statement_hash

st = emit_statements("squeeze", seed=42, periods=8, grain="quarter")

st.amount("2025-Q4", "total_assets")  # Decimal('12184593.71')
st.series("revenue")  # 8 Decimals, in period order
st.ground_truth.anomalies  # what was injected, and what should catch it
statement_hash(st)  # same inputs → same hash, always
```

---

## The design in one line

An **operating plan** becomes **balanced double-entry journals**, and the three
statements are **derived from the trial balance** — never authored.

```
BusinessProfile ──build_plans──> PeriodPlan[] ──apply_anomalies──> PeriodPlan[]
                                                       │
                                              build_entries
                                                       │
                                              JournalEntry[]  ← the books
                                                       │
                                                 build_lines
                                                       │
                                        P&L · balance sheet · cash flow
```

Three separately-generated statements are three chances to disagree with each other,
and the disagreements would be small and hard to see. A trial balance cannot disagree
with itself. Everything the emitter guarantees follows from that choice:

| Invariant | Holds because |
|---|---|
| every journal balances | `_Books.post` raises on an unbalanced entry — it cannot be recorded |
| `assets = liabilities + equity`, every period | the period-end closing journal sweeps P&L into retained earnings |
| `RE_t = RE_{t-1} + NI_t − dividends_t` | that closing journal is the only thing that touches retained earnings |
| `cf_net_change_in_cash = cash_t − cash_{t-1}`, to the cent | the indirect build-up is algebraically the accounting identity — see the derivation in `derive.py` |

`tests/test_emitter_invariants.py` asserts all four, per period, per profile, per seed,
at all three grains — plus a fifth that is the strongest of them:
**the operating section rebuilt from the cash postings must equal the indirect
build-up from the statements.** Two independent routes to the same number.

---

## Public surface

| | |
|---|---|
| `emit_statements(profile, seed, periods, grain, first_start, anomalies)` | the entry point |
| `statement_hash(set)` | the determinism proof |
| `PROFILES`, `get_profile`, `StatementProfile`, `BusinessProfile` | the knobs |
| `ANOMALIES`, `ANOMALIES_BY_ID`, `apply_anomalies` | the anomalies knob |
| `STATEMENT_LINES`, `LINES_BY_CODE`, `lines_for` | the canonical line vocabulary |
| `StatementSet`, `Period`, `Line`, `JournalEntry` | the data |
| `export.to_csv` / `to_xlsx` | the intake-template shape |

### Profiles

| name | entity | story | injected |
|---|---|---|---|
| `steady` | Harbourline Logistics | profitable and unremarkable | — |
| `growth` | Meridian Foods | growing fast, funding the working capital | — |
| `paper_profit` | Beacon & Vale | profitable on paper, burning cash underneath | `ocf_ni_divergence` |
| `squeeze` | Coldharbour Manufacturing | margins giving way, collections slipping | `margin_compression`, `ar_days_balloon`, `inventory_build` |
| `leveraged` | Northwind Trading | over-investing on the facility; current ratio breaks 1 | `liquidity_squeeze`, `debt_spike` |
| `distress` | Stonebridge Services | sales falling, margins going, equity eroding | `revenue_decline`, `margin_compression`, `capex_pause` |

`steady` and `growth` are the **controls**: they inject nothing, and they are what
prove a rule engine built on top does not simply fire on everything.

### Anomalies

Nine injectors. Each perturbs the **plan**, never the postings — which is why the books
survive all nine applied at once (`test_every_injector_at_once_leaves_the_books_intact`).

`ar_days_balloon` · `margin_compression` · `ocf_ni_divergence` · `liquidity_squeeze` ·
`inventory_build` · `payable_stretch` · `debt_spike` · `revenue_decline` ·
**`capex_pause`**

Each records an `AnomalyTruth` — what was injected, which periods, and which rule ids
*ought* to fire. **`capex_pause` deliberately maps to none.** Underinvestment is a real
pattern a human analyst would raise and this project ships no rule for it; without at
least one such case, flag recall would be 100% by construction and would measure wiring
rather than detection.

---

## Reusing it in another project

1. **Copy the directory.** It imports only from `ledgerfab.*` — `rng`, and nothing else
   that matters. A test enforces that (`test_the_extension_never_imports_the_application`).
2. **Address lines by `STATEMENT_LINES`.** One canonical vocabulary; each entry carries
   its `statement`, `section`, `sign` (`magnitude` or `signed`) and, for subtotals, the
   `(line_code, coefficient)` components it is built from. Do not hard-code a subtotal.
3. **Respect the sign convention**, because it is what silently breaks a ratio:
   * P&L — revenue and every expense are positive magnitudes; subtotals are signed.
   * BS — magnitudes, except `retained_earnings` and `total_equity`, which are signed
     (**negative equity is a supported case, not an accident**).
   * CF — every line signed, inflow-positive.
4. **Use `Period.days`, never 365.** A quarterly set's receivable days divide by the
   quarter's own day count. This is the single easiest way to be wrong by 4× and still
   print a plausible number.
5. **Money is `Decimal`.** `statement_hash` raises on a float rather than rounding it
   away — the step whose job is proving the data did not change must not hide a change.
6. **`amount()` returns `None`, not zero,** for a line the set does not carry. A missing
   cash flow statement is not a cash flow of nought.

### Adding an anomaly

Write the injector against `PeriodPlan` (never against postings), register it in
`ANOMALIES`, and give it a sub-stream via `rng.child(id)` so adding it cannot shift the
draws of any existing one. Then add a test that it moves its metric against the *same
seed with the injector off* — comparing against an absolute threshold tests the profile,
not the injector.

### Adding a line or an account

Add the `StatementAccount` to `STATEMENT_ACCOUNTS` with its `cf_section`, and the
`StatementLineDef` to `STATEMENT_LINES`. `test_every_posted_account_maps_to_a_statement_line`
will fail until the two agree — which is deliberate, because the cash-flow identity holds
only while every account sits in exactly one section.

---

## What it does not do

* **No FX.** Single currency per set.
* **No disposals.** PPE is carried at cost and only ever increases, which is what makes
  `cf_capex = −Δ ppe_gross` exact. Adding disposals means adding a gain/loss line and
  splitting that movement.
* **No VAT.** Account `2200` exists for uploads that carry it and is never posted to.
* **No consolidation, no segments, no comparative restatements.**
* **No revenue-recognition subtlety.** Revenue is booked on credit, in period.

These are honest limits, and several of them are exactly what the analysis layer's
"what these statements cannot tell us" section exists to say out loud.
