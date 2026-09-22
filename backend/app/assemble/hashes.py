"""Three hashes over deliberately disjoint inputs.

Spec 13 F7's demo claim is *"structure identical / numbers changed"*. A single hash over
the whole pack can only ever say "different", which would make the month-diff view an
impression rather than a fact. Two hashes make the claim falsifiable (PLAN.md **D-016**):

- ``structure_hash`` — template ref, and each section's (key, type, order). **No values.**
- ``value_digest``   — every figure, and nothing about layout.
- ``snapshot_hash``  — the bound source data, which is what the archive attests to.

Canonical JSON throughout: sorted keys, no whitespace, `Decimal` as a string. A Decimal
serialised through float would change the hash of unchanged data, at the one step whose
entire job is proving the data did not change.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    return value


def digest(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def structure_hash(template_ref: str, sections: list[dict[str, Any]]) -> str:
    """What the pack *is*, independent of what the numbers say.

    Section title is excluded along with the values: retitling "Profit and loss" to
    "Income statement" is a presentation change, and a diff view that called that a
    structural change would cry wolf on the demo it exists to support.
    """
    return digest(
        {
            "template": template_ref,
            "sections": [
                {"key": s["section_key"], "type": s["type"], "order": s["order_index"]}
                for s in sections
            ],
        }
    )


def value_digest(sections: list[dict[str, Any]]) -> str:
    """Every figure in the pack, and nothing else.

    Narrative prose is excluded on purpose. Two runs of the same data must produce the
    same value digest even if a human has since reworded a paragraph — otherwise editing
    a sentence would look, to the diff view, like the numbers moved.
    """
    figures: list[Any] = []
    for section in sorted(sections, key=lambda s: s["order_index"]):
        content = section.get("content_json") or {}
        if section["type"] == "table":
            figures.append([row for row in content.get("rows", [])])
        elif section["type"] == "kpi_grid":
            figures.append(
                [
                    {"id": k["id"], "value": k.get("value"), "prior": k.get("prior_value")}
                    for k in content.get("kpis", [])
                ]
            )
        elif section["type"] == "flags":
            figures.append([f["rule_id"] for f in content.get("items", [])])
        elif section["type"] == "narrative":
            # The figures the prose cites, not the prose. Sorted, because the model may
            # legitimately mention them in a different order on a re-draft.
            figures.append(sorted(str(r.get("value")) for r in content.get("figure_refs", [])))
    return digest(figures)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """The bound source data behind the pack — what the archive attests to."""
    return digest(snapshot)
