# Template guide

A ReportSmith template is a YAML document defining one report pack: its sections, where each
section's data comes from, and how the whole pack is allowed to speak. It is versioned, and a
version some pack has already used is frozen.

## The shape

```yaml
id: monthly_management_pack     # [a-z][a-z0-9_]*
name: Monthly Management Pack
version: 1                      # integer; (id, version) is immutable once cited
description: ...

style: { ... }                  # pack-level rules — the linter's whole rulebook
sections: [ ... ]               # at least one
```

Unknown keys are **errors**, at every level. A typo'd `tone_rule:` for `tone_rules:` fails at
load rather than being quietly dropped — the alternative is a controller editing the tone
rules, seeing no error, and getting a pack drafted under the old ones.

## The four section types, and no fifth

| type | what it is | editable by a reviewer |
|---|---|---|
| `table` | rows from a binding, optional total row | no — computed |
| `kpi_grid` | named metrics with prior-period comparatives | no — computed |
| `narrative` | prose drafted from this section's figures and tone rules only | **yes** |
| `flags` | rule firings with their evidence | no — computed |

Every section carries `id`, `title`, `type`, `required` and `binding`.
`required: true` means a gap here **blocks issuance** until resolved or waived.

## Bindings — the closed selector grammar

```yaml
binding:
  source: ledgerfab            # ledgerfab | spendsort | statementlens
  select: gl_expense_lines     # a dataset the adapter publishes
  where:
    - { field: account_type, op: eq, value: expense }
  group_by: [account_code, account_name]
  aggregate: { amount: sum, invoice_id: count_distinct }
  order_by: ["-amount"]        # leading "-" is descending
  limit: 10
```

These keys and no others. Operators: `eq ne gt gte lt lte in not_in`. Aggregates:
`sum count count_distinct mean min max`.

**There is no expression language, and there will not be one.** A template is user input, and
an expression language in user input is a remote-code-execution hole wearing a YAML hat. The
closed grammar is also what makes golden-file determinism achievable and what lets the editor
point at the offending line.

Anything the grammar cannot express is a **code** change in an adapter's published dataset —
reviewable, testable, versioned — rather than a clever string in a config file.

Three behaviours worth knowing:

- Stage order is fixed: `where → group_by/aggregate → order_by → limit`. Filtering after
  aggregating would silently turn "top 10 by spend" into "top 10 of whatever survived".
- Ordering is **total**: the sort key always ends with a tiebreak, so equal-valued rows
  cannot swap between runs and fail a golden file on a day nothing changed.
- `limit` records what it dropped, and the pack renders "showing 10 of 47". A silently
  truncated table reads as "this is everything".
- `None` is never compared. A row with no value is not "less than 10", it is unknown, and it
  is excluded. Aggregates skip it rather than treating it as zero.

## Section extras

```yaml
# table
columns:
  - { field: amount, label: Spend, align: right, format: money }
total_row: true        # only money and integer columns total; summing a % column is meaningless

# kpi_grid
kpis:
  - { id: revenue, label: Revenue, metric: revenue, format: money,
      compare: prior_period, direction: higher_is_better }

# narrative
max_words: 200
tone_rules:
  - Open with revenue for the month and its movement against the prior month.
  - Do not offer a cause. These figures do not contain one.
```

`direction` is how the UI knows whether a movement is good news. Payables rising is not an
improvement, and colour comes from that declaration rather than from the sign of the number.

## Style rules

```yaml
style:
  voice: "Third person, past tense, factual. Do not recommend, forecast, or speculate."
  rounding: { money: 0, percent: 1, ratio: 2 }
  currency: { code: GBP, symbol: "£", position: prefix, thousands: ",", negative: parens }
  taboo_phrases: [significant, robust, leverage, world-class]
  max_sentence_words: 30
```

The deterministic linter enforces these. It **auto-fixes formatting only** — rendering a
negative in parentheses, tidying spacing — and may never change a figure's value; the numeric
cross-check re-runs afterwards to prove it did not. Taboo phrases are **flagged, never
fixed**: choosing the honest replacement for "significant" is a judgement about the business,
and that belongs to whoever signs.

Changing the style rules mints a new prompt version (`template@vN/section_id`), so a tone
change is a tracked, evaluable event rather than a prompt tweak somebody made on a Tuesday.

## Versioning

Once any pack has been built from `(id, version)`, that version is **locked**. Editing it is
refused with a message telling you to increment `version`. That rule is the only thing making
`template_version` on an issued archive mean anything: re-running v1 must reproduce what the
archive attests to.

## Writing one

Start from `backend/app/template/default/monthly_management_pack.yaml`. The Templates screen
validates as you type, against the real backend schema rather than a copy of it in the
browser — a second definition of "valid" is a second thing to keep in step, and the one that
drifts is always the one the user sees.

For what each adapter publishes and what each column means, see
[ADAPTER_CONTRACTS.md](ADAPTER_CONTRACTS.md).
