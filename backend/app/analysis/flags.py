"""The red-flag rules engine — YAML rules, a closed predicate DSL, no `eval`.

StatementLens's P5, built here to its shape (PLAN.md **D-018**). Rules are data, so a
controller can add one without a deploy; the DSL is closed, so a rule file cannot become
a program.

The rule that matters most is the quiet one: **an undefined metric never fires a flag.**
"Current ratio below 1" must not fire because current liabilities were zero and the ratio
could not be computed. That is how a flags engine ends up crying wolf about arithmetic,
and once a reviewer learns to skim past flags, the whole mechanism is dead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml

from app.analysis.formula import Computation

RULES_DIR = Path(__file__).parent / "rules"

Severity = Literal["high", "medium", "low"]
SEVERITY_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}

# The closed operator set. Adding one is a code change with a test, not a YAML edit.
OPS = {"lt", "lte", "gt", "gte", "eq", "ne", "between"}


@dataclass(frozen=True, slots=True)
class Flag:
    """One firing. Mirrors StatementLens's `flags` table (spec 12 §6)."""

    rule_id: str
    label: str
    period: str
    severity: Severity
    message: str
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK[self.severity]


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    label: str
    severity: Severity
    message: str
    # A selector is `ratio.<id>`, `line.<code>`, or `delta.<ratio_id>` — three closed
    # prefixes, not arbitrary attribute access.
    when: dict[str, Any]
    evidence: list[str] = field(default_factory=list)


class RuleError(ValueError):
    """A rule file that will not load."""


def _resolve(
    selector: str,
    computations: dict[str, Computation],
    figures: dict[str, Decimal | None],
    deltas: dict[str, Decimal | None],
) -> tuple[Decimal | None, str]:
    """Selector → (value, why-it-is-absent). Returns None when it cannot be resolved.

    The second element carries the reason so a skipped rule can say *why* it was
    skipped. A rules engine that silently evaluates nothing is indistinguishable from
    one where nothing is wrong.
    """
    kind, _, key = selector.partition(".")
    if not key:
        raise RuleError(f"selector {selector!r} must be 'ratio.<id>', 'line.<code>' or 'delta.<id>'")
    if kind == "ratio":
        comp = computations.get(key)
        if comp is None:
            raise RuleError(f"rule references unknown ratio {key!r}")
        if comp.status == "undefined":
            return None, f"{comp.label} is undefined ({comp.note})"
        return comp.value, ""
    if kind == "line":
        value = figures.get(key)
        return (value, "" if value is not None else f"line {key} not present")
    if kind == "delta":
        value = deltas.get(key)
        return (value, "" if value is not None else f"no prior period for {key}")
    raise RuleError(f"unknown selector kind {kind!r} in {selector!r}")


def _test(value: Decimal, op: str, operand: Any) -> bool:
    if op == "between":
        low, high = (Decimal(str(x)) for x in operand)
        return low <= value <= high
    threshold = Decimal(str(operand))
    return {
        "lt": value < threshold,
        "lte": value <= threshold,
        "gt": value > threshold,
        "gte": value >= threshold,
        "eq": value == threshold,
        "ne": value != threshold,
    }[op]


def _evaluate(
    node: dict[str, Any],
    computations: dict[str, Computation],
    figures: dict[str, Decimal | None],
    deltas: dict[str, Decimal | None],
) -> tuple[bool | None, str]:
    """Evaluate one predicate node. ``None`` means "could not be evaluated".

    Three-valued on purpose. ``all`` of [true, unknown] is unknown, not true — a
    compound rule with one unresolvable arm has not been satisfied, it has been left
    unanswered, and firing on it would be the cry-wolf bug in compound form.
    """
    if "all" in node:
        results = [_evaluate(child, computations, figures, deltas) for child in node["all"]]
        if any(r is None for r, _ in results):
            return None, next(note for r, note in results if r is None)
        return all(r for r, _ in results), ""
    if "any" in node:
        results = [_evaluate(child, computations, figures, deltas) for child in node["any"]]
        if any(r for r, _ in results):
            return True, ""
        if any(r is None for r, _ in results):
            return None, next(note for r, note in results if r is None)
        return False, ""
    if "not" in node:
        inner, note = _evaluate(node["not"], computations, figures, deltas)
        return (None, note) if inner is None else (not inner, "")

    selector = node.get("selector")
    if not isinstance(selector, str):
        raise RuleError(f"predicate needs a 'selector', got {node!r}")
    op = node.get("op", "lt")
    if op not in OPS:
        raise RuleError(f"unknown op {op!r}; permitted: {sorted(OPS)}")
    if "value" not in node:
        raise RuleError(f"predicate for {selector!r} needs a 'value'")

    value, why = _resolve(selector, computations, figures, deltas)
    if value is None:
        return None, why
    return _test(value, op, node["value"]), ""


def load_rules(directory: Path | None = None) -> list[Rule]:
    """Load every rule file. Unknown keys are rejected loudly.

    A rule with a typo'd key that loads and never fires is worse than one that fails to
    load: the reviewer believes they are covered.
    """
    directory = directory or RULES_DIR
    rules: list[Rule] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in raw.get("rules", []):
            unknown = set(entry) - {"rule_id", "label", "severity", "message", "when", "evidence"}
            if unknown:
                raise RuleError(f"{path.name}: rule {entry.get('rule_id')} has unknown keys {sorted(unknown)}")
            if entry.get("severity") not in SEVERITY_RANK:
                raise RuleError(
                    f"{path.name}: rule {entry.get('rule_id')} has severity "
                    f"{entry.get('severity')!r}; permitted: {sorted(SEVERITY_RANK)}"
                )
            rules.append(
                Rule(
                    rule_id=entry["rule_id"],
                    label=entry["label"],
                    severity=entry["severity"],
                    message=entry["message"],
                    when=entry["when"],
                    evidence=entry.get("evidence", []),
                )
            )
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        raise RuleError("duplicate rule_id across rule files")
    return rules


def evaluate_rules(
    computations: list[Computation],
    figures: dict[str, Decimal | None],
    deltas: dict[str, Decimal | None],
    period: str,
    rules: list[Rule] | None = None,
) -> list[Flag]:
    """Fire the rules. Deterministic order: severity desc, then rule_id."""
    rules = rules if rules is not None else load_rules()
    by_id = {c.formula_id: c for c in computations}
    fired: list[Flag] = []

    for rule in rules:
        result, _why = _evaluate(rule.when, by_id, figures, deltas)
        if result is not True:
            continue
        evidence: dict[str, str] = {}
        for selector in rule.evidence:
            value, _ = _resolve(selector, by_id, figures, deltas)
            kind, _, key = selector.partition(".")
            comp = by_id.get(key)
            label = comp.label if kind == "ratio" and comp else key
            evidence[label] = comp.display if kind == "ratio" and comp else (
                "n/a" if value is None else str(value)
            )
        fired.append(
            Flag(
                rule_id=rule.rule_id,
                label=rule.label,
                period=period,
                severity=rule.severity,
                message=rule.message,
                evidence=evidence,
            )
        )

    return sorted(fired, key=lambda f: (-f.severity_rank, f.rule_id))
