"""The invariant: a section never disappears, whatever an adapter does.

Spec 13 F2: *"missing/failed binding → section renders as an explicit GAP (never silently
omitted), listed in a gaps panel."*

This is the most important test in the repo. A crash gets noticed; a missing section in a
board pack gets **signed**. So the adapters below misbehave in every way one plausibly
could, and the assertion is always the same: the pack has exactly as many sections as the
template does, and the trouble shows up as a gap with a reason.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.base import GapReason, resolve_binding
from app.adapters.frame import Frame, frame_from_dicts
from app.assemble.engine import assemble
from app.template.schema import Selector


class _Base:
    name = "ledgerfab"
    SCHEMA_VERSION = "test/v0"

    def catalog(self):
        return (
            "pnl_lines",
            "bs_lines",
            "cf_lines",
            "period_metrics",
            "exceptions",
            "invoices",
            "gl_expense_lines",
            "ratios",
            "flags",
            "categories",
        )

    def fetch(self, dataset, period):
        raise NotImplementedError


class RaisesValueError(_Base):
    def fetch(self, dataset, period):
        raise ValueError("upstream exploded")


class RaisesKeyError(_Base):
    def fetch(self, dataset, period):
        raise KeyError("missing key")


class ReturnsNone(_Base):
    def fetch(self, dataset, period):
        return None


class ReturnsList(_Base):
    def fetch(self, dataset, period):
        return [{"a": 1}]


class ReturnsEmptyFrame(_Base):
    def fetch(self, dataset, period):
        return frame_from_dicts([], columns=("a",), source=self.name, dataset=dataset)


class ReturnsWrongColumns(_Base):
    def fetch(self, dataset, period):
        return frame_from_dicts([{"nonsense": Decimal("1")}], source=self.name, dataset=dataset)


class EmptyCatalog(_Base):
    def catalog(self):
        return ()


class CatalogRaises(_Base):
    def catalog(self):
        raise RuntimeError("cannot enumerate")


class ReturnsNullValues(_Base):
    def fetch(self, dataset, period):
        return frame_from_dicts(
            [{"metric": None, "value": None, "label": None, "rule_id": None, "severity": None}],
            source=self.name,
            dataset=dataset,
        )


class ReturnsHugeFrame(_Base):
    def fetch(self, dataset, period):
        return frame_from_dicts(
            [
                {
                    "metric": f"m{i}",
                    "value": Decimal(i),
                    "label": str(i),
                    "rule_id": str(i),
                    "severity": "low",
                    "severity_rank": 1,
                }
                for i in range(5000)
            ],
            source=self.name,
            dataset=dataset,
        )


class ReturnsUnicodeSoup(_Base):
    def fetch(self, dataset, period):
        return frame_from_dicts(
            [
                {
                    "metric": "\x00﻿",
                    "value": Decimal("1"),
                    "label": "🙂‮",
                    "rule_id": "x",
                    "severity": "low",
                    "severity_rank": 1,
                }
            ],
            source=self.name,
            dataset=dataset,
        )


class ReturnsFloatsNotDecimals(_Base):
    """The quiet one: right shape, wrong numeric type."""

    def fetch(self, dataset, period):
        return frame_from_dicts(
            [
                {
                    "metric": "revenue",
                    "value": 1.1,
                    "label": "Revenue",
                    "rule_id": "x",
                    "severity": "low",
                    "severity_rank": 1,
                }
            ],
            source=self.name,
            dataset=dataset,
        )


MISBEHAVIOURS = [
    RaisesValueError,
    RaisesKeyError,
    ReturnsNone,
    ReturnsList,
    ReturnsEmptyFrame,
    ReturnsWrongColumns,
    EmptyCatalog,
    CatalogRaises,
    ReturnsNullValues,
    ReturnsHugeFrame,
    ReturnsUnicodeSoup,
    ReturnsFloatsNotDecimals,
]


@pytest.mark.parametrize("behaviour", MISBEHAVIOURS, ids=lambda b: b.__name__)
def test_section_count_invariant_holds(behaviour, template, period):
    """However an adapter misbehaves, every template section still produces a section."""
    broken = behaviour()
    adapters = {"ledgerfab": broken, "spendsort": broken, "statementlens": broken}

    pack = assemble(template, period, adapters)

    assert len(pack.sections) == len(template.sections), (
        f"{behaviour.__name__} caused a section to vanish — "
        f"{len(pack.sections)} of {len(template.sections)}"
    )
    assert [s.section_key for s in pack.sections] == [s.id for s in template.sections]


@pytest.mark.parametrize("behaviour", MISBEHAVIOURS, ids=lambda b: b.__name__)
def test_trouble_is_always_visible(behaviour, template, period):
    """Something went wrong, so the pack must say so somewhere a human will look."""
    broken = behaviour()
    adapters = {"ledgerfab": broken, "spendsort": broken, "statementlens": broken}

    pack = assemble(template, period, adapters)
    troubled = [s for s in pack.sections if s.has_gap or not s.content_json]
    assert troubled, f"{behaviour.__name__} produced a pack claiming everything was fine"

    for section in pack.sections:
        for gap in section.gaps_json:
            assert gap["reason"] in set(GapReason)
            assert gap["detail"], "a gap with no detail tells a reviewer nothing"


def test_missing_adapter_is_a_gap_not_a_crash(template, period):
    pack = assemble(template, period, {})
    assert len(pack.sections) == len(template.sections)
    assert all(s.has_gap for s in pack.sections)
    assert all(
        g["reason"] == GapReason.ADAPTER_UNAVAILABLE for s in pack.sections for g in s.gaps_json
    )


def test_unknown_dataset_names_what_is_available():
    class Small(_Base):
        def catalog(self):
            return ("ratios",)

    result = resolve_binding(
        {"statementlens": Small()},
        Selector(source="statementlens", select="segment_ratios"),
        "2024-07",
    )
    assert result.is_gap
    assert result.reason == GapReason.UNKNOWN_DATASET
    assert "ratios" in result.detail


def test_resolve_binding_never_raises(template, period):
    """The sum type has two arms and no exception path. Exhaustively."""
    for behaviour in MISBEHAVIOURS:
        broken = behaviour()
        for section in template.sections:
            result = resolve_binding({section.binding.source: broken}, section.binding, period)
            assert isinstance(result, Frame | object)
            assert hasattr(result, "is_gap")
