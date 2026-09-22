"""Determinism: same data + same template = identical output (spec 13 §10).

Golden files alone can lock in a bug, so the numbers are also asserted independently in
`test_kpi_math.py`. These tests answer a different question: *did anything change?*
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from app.adapters.frame import frame_from_dicts
from app.adapters.selector import apply_selector
from app.assemble.engine import assemble
from app.assemble.hashes import value_digest
from app.template.schema import Condition, Selector

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden"


def _canonical(pack) -> str:
    return json.dumps(
        {
            "template_ref": pack.template_ref,
            "period": pack.period,
            "structure_hash": pack.structure_hash,
            "value_digest": pack.value_digest,
            "sections": [s.as_row() for s in pack.sections],
        },
        indent=2, sort_keys=True, default=str,
    )


def test_assembling_twice_is_byte_identical(template, period, adapters):
    a = assemble(template, period, adapters)
    b = assemble(template, period, adapters)
    assert _canonical(a) == _canonical(b)
    assert a.structure_hash == b.structure_hash
    assert a.value_digest == b.value_digest
    assert a.snapshot_hash == b.snapshot_hash


@pytest.mark.parametrize("which", ["first", "second"])
def test_matches_the_committed_golden_file(which, template, period, second_period, adapters):
    target = period if which == "first" else second_period
    path = GOLDEN / f"{template.id}-{target}.json"
    if not path.exists():
        pytest.skip(f"golden file not generated yet: run `make golden` ({path.name})")

    actual = _canonical(assemble(template, target, adapters))
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"assembly output drifted from {path.name}. If the change is intended, "
        f"regenerate with `make golden` and review the diff."
    )


def test_structure_is_stable_across_periods_but_values_are_not(
    template, period, second_period, adapters
):
    """Spec 13 F7's claim, tested rather than demonstrated."""
    a = assemble(template, period, adapters)
    b = assemble(template, second_period, adapters)
    assert a.structure_hash == b.structure_hash
    assert a.value_digest != b.value_digest


def test_narrative_rewording_does_not_change_the_value_digest():
    """Editing prose must not look, to the diff view, like the numbers moved."""
    base = {
        "section_key": "n", "type": "narrative", "order_index": 0,
        "content_json": {
            "text": "Revenue was £3.8m.",
            "figure_refs": [{"ref_id": "r", "value": "3815070.61"}],
        },
    }
    reworded = {
        **base,
        "content_json": {**base["content_json"], "text": "In the month, revenue reached £3.8m."},
    }
    assert value_digest([base]) == value_digest([reworded])


def test_figure_change_does_change_the_value_digest():
    base = {
        "section_key": "n", "type": "narrative", "order_index": 0,
        "content_json": {"text": "x", "figure_refs": [{"ref_id": "r", "value": "1.00"}]},
    }
    moved = {
        **base,
        "content_json": {"text": "x", "figure_refs": [{"ref_id": "r", "value": "2.00"}]},
    }
    assert value_digest([base]) != value_digest([moved])


# ------------------------------------------------------------------ ordering --


def test_ordering_is_total_under_input_permutation():
    """Equal-valued rows must not swap places, or a golden file fails for no reason."""
    rows = [
        {"name": "b", "amount": Decimal("100")},
        {"name": "a", "amount": Decimal("100")},
        {"name": "c", "amount": Decimal("100")},
    ]
    selector = Selector(source="ledgerfab", select="x", order_by=["-amount"])

    first = apply_selector(frame_from_dicts(rows), selector)
    second = apply_selector(frame_from_dicts(list(reversed(rows))), selector)
    assert [r["name"] for r in first.rows] == [r["name"] for r in second.rows]


def test_limit_records_what_it_dropped():
    """A silently truncated table reads as 'this is everything'."""
    rows = [{"n": i, "amount": Decimal(i)} for i in range(20)]
    selector = Selector(source="ledgerfab", select="x", order_by=["-amount"], limit=5)
    out = apply_selector(frame_from_dicts(rows), selector)
    assert len(out.rows) == 5
    assert out.meta["truncated_from"] == 20


def test_nulls_sort_last_in_both_directions():
    rows = [{"n": "a", "v": Decimal(1)}, {"n": "b", "v": None}, {"n": "c", "v": Decimal(3)}]
    ascending = apply_selector(
        frame_from_dicts(rows), Selector(source="ledgerfab", select="x", order_by=["v"])
    )
    descending = apply_selector(
        frame_from_dicts(rows), Selector(source="ledgerfab", select="x", order_by=["-v"])
    )
    assert ascending.rows[-1]["n"] == "b"
    assert descending.rows[-1]["n"] == "b"


def test_where_on_none_excludes_rather_than_compares():
    """A row with no value is not 'less than 10'; it is unknown."""
    rows = [{"v": Decimal(5)}, {"v": None}]
    out = apply_selector(
        frame_from_dicts(rows),
        Selector(source="ledgerfab", select="x",
                 where=[Condition(field="v", op="lt", value=10)]),
    )
    assert len(out.rows) == 1


def test_aggregate_skips_nulls_rather_than_zeroing_them():
    rows = [{"k": "a", "v": Decimal(10)}, {"k": "a", "v": None}, {"k": "a", "v": Decimal(20)}]
    out = apply_selector(
        frame_from_dicts(rows),
        Selector(source="ledgerfab", select="x", group_by=["k"], aggregate={"v": "sum"}),
    )
    assert out.rows[0]["v"] == Decimal(30)


def test_no_llm_anywhere_in_assemble():
    """Determinism is only achievable if nothing here can reach a model."""
    package = Path(__file__).resolve().parents[1] / "app" / "assemble"
    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        for banned in ("openai", "langchain", "langgraph", "anthropic", "app.narrate"):
            assert banned not in source, f"{module.name} reaches a model path ({banned})"
