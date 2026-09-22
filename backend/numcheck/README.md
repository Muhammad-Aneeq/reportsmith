# numcheck

Every number in an LLM's prose must match a figure you supplied. Anything else is a
fabrication, and this package finds it.

```python
from decimal import Decimal
from numcheck import FigureRef, verify, drop_failing_sentences

refs = [FigureRef(ref_id="rev", value=Decimal("3815070.61"), unit="money", label="Revenue")]

verify("Revenue was £3.8m.", refs).ok  # True  — 3.8m, to the 1 dp the author wrote
verify("Revenue was £3,815,071.", refs).ok  # True  — same figure, more precisely stated
verify("Revenue was £3.9m.", refs).ok  # False — no supplied figure supports it
verify("Margin was 3.8%.", refs).ok  # False — right digits, wrong unit
```

When a draft fails, remove the offending sentence rather than the draft:

```python
kept, dropped = drop_failing_sentences(text, refs, periods=["2024-07"])
```

## The two rules that make it worth trusting

**Precision comes from the text, not from a setting.** `£3.8m` is the claim "3.8 million to
one decimal place", and is checked to one. There is no tolerance parameter, because a
tolerance parameter is a knob, and a knob gets widened the first time a build goes red.

**The exemption list is closed at two entries** — declared period labels, and ordinals in
list markers — and a test asserts its exact contents. Every exemption is a hole. Anything a
narrative may legitimately cite should be supplied as a `FigureRef` instead.

## Units

`money · percent · count · days · times · bare`. `bare` satisfies any unit, because prose
drops the symbol on a repeat mention. **`money` and `percent` never satisfy each other** —
that conflation is the hole most worth keeping shut.

## Scoring a whole run

```python
from numcheck import score

report = score([(key, text, refs, periods), ...])
report.summary()  # "PASS numeric-fidelity 100.00% (34/34 figures across 3 section(s))"
report.passed()  # 100% AND at least one figure actually checked
```

`passed()` requires both, so a composer cannot score 100% by writing nothing.

## Provenance

Written in ReportSmith, designed to live in StatementLens. See `ORIGIN.md`.
