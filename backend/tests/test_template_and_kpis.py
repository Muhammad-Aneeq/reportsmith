"""The template schema's fences, and the KPI arithmetic, computed by hand.

The golden files prove *nothing changed*. These prove the numbers were right in the first
place — a golden file will happily lock in a bug, so the two have to exist together.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.formatting import format_delta, format_money, format_percent
from app.money import pct_change, quantize, to_money
from app.template.schema import PackStyle, Template
from app.template.store import TemplateError, dump_template, parse_template

MINIMAL = """
id: tiny
name: Tiny
version: 1
sections:
  - id: s1
    title: One
    type: table
    binding: { source: ledgerfab, select: pnl_lines }
    columns:
      - { field: label, label: Line, align: left, format: text }
"""


# ------------------------------------------------------------------ schema --


def test_the_shipped_template_covers_all_four_types_and_round_trips(template):
    assert {s.type for s in template.sections} == {"table", "kpi_grid", "narrative", "flags"}
    assert parse_template(dump_template(template), source="rt") == template


def test_a_fifth_section_type_is_a_validation_error():
    bad = MINIMAL.replace("type: table", "type: timeline")
    with pytest.raises(TemplateError) as exc:
        parse_template(bad)
    assert "s1" in str(exc.value) or "type" in str(exc.value)


def test_an_unknown_key_fails_loudly():
    """A typo that is silently dropped means a pack drafted under the old rules."""
    bad = MINIMAL.replace("    title: One", "    title: One\n    tone_rule: oops")
    with pytest.raises(TemplateError, match=r"tone_rule|[Ee]xtra"):
        parse_template(bad)


def test_duplicate_section_ids_are_rejected():
    bad = (
        MINIMAL
        + """
  - id: s1
    title: Duplicate
    type: narrative
    binding: { source: ledgerfab, select: pnl_lines }
"""
    )
    with pytest.raises(TemplateError, match="duplicate"):
        parse_template(bad)


def test_aggregate_without_group_by_is_refused():
    """Ambiguous: one total row, or a no-op? Refusing beats picking a meaning."""
    bad = MINIMAL.replace(
        "binding: { source: ledgerfab, select: pnl_lines }",
        "binding: { source: ledgerfab, select: pnl_lines, aggregate: { amount: sum } }",
    )
    with pytest.raises(TemplateError, match="group_by"):
        parse_template(bad)


def test_list_operators_require_list_values():
    bad = MINIMAL.replace(
        "binding: { source: ledgerfab, select: pnl_lines }",
        "binding: { source: ledgerfab, select: pnl_lines, where: [{field: x, op: in, value: 3}] }",
    )
    with pytest.raises(TemplateError, match="list"):
        parse_template(bad)


def test_an_unknown_source_is_refused_at_load():
    bad = MINIMAL.replace("source: ledgerfab", "source: quickbooks")
    with pytest.raises(TemplateError):
        parse_template(bad)


def test_a_template_version_cannot_be_edited_once_a_pack_cites_it(db_session, period):
    """The rule that makes `template_version` on an archive mean anything."""
    from app import service

    service.create_pack(db_session, "monthly_management_pack", period)
    row = service.get_template_row(db_session, "monthly_management_pack")
    with pytest.raises(service.ServiceError, match="Increment `version`"):
        service.save_template(db_session, row.yaml.replace("version: 1", "version: 1"))


def test_incrementing_the_version_creates_a_new_row(db_session, period):
    from app import service

    service.create_pack(db_session, "monthly_management_pack", period)
    row = service.get_template_row(db_session, "monthly_management_pack")
    new = service.save_template(db_session, row.yaml.replace("version: 1", "version: 2"))
    assert new.version == 2
    assert service.get_template_row(db_session, "monthly_management_pack", 1) is not None


def test_a_yaml_syntax_error_names_the_file():
    with pytest.raises(TemplateError, match="not valid YAML"):
        parse_template("id: [unclosed", source="broken.yaml")


def test_template_is_frozen_after_load():
    from pydantic import ValidationError

    template = parse_template(MINIMAL)
    assert isinstance(template, Template)
    # frozen=True: a loaded template cannot drift under the pack that cites it.
    with pytest.raises(ValidationError):
        template.version = 9  # type: ignore[misc]


# ------------------------------------------------------------- money maths --


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1.1, Decimal("1.10")),
        ("1,234.56", Decimal("1234.56")),
        ("£", None),  # handled below
        (0, Decimal("0.00")),
        (Decimal("2.345"), Decimal("2.35")),  # half-up, not banker's
        (Decimal("2.355"), Decimal("2.36")),
        (-1.005, Decimal("-1.01")),
    ],
)
def test_to_money_hand_computed(raw, expected):
    if expected is None:
        with pytest.raises(ValueError):
            to_money(raw)
        return
    assert to_money(raw) == expected


def test_float_goes_through_str_not_through_binary():
    """Decimal(0.1) is 0.1000000000000000055…; Decimal(str(0.1)) is what the source meant."""
    assert to_money(0.1) == Decimal("0.10")
    assert to_money(2.675) == Decimal("2.68")


@pytest.mark.parametrize(
    "current,prior,expected",
    [
        (Decimal(110), Decimal(100), Decimal("10.0000")),
        (Decimal(90), Decimal(100), Decimal("-10.0000")),
        (Decimal(100), Decimal(100), Decimal("0.0000")),
        # A negative base: the magnitude is what moved, so the sign of the *change* is kept.
        (Decimal(-50), Decimal(-100), Decimal("50.0000")),
        (Decimal(100), Decimal(0), None),  # zero base — not a 100% rise
        (Decimal(100), None, None),  # no prior period
        (None, Decimal(100), None),  # figure absent this period
    ],
)
def test_pct_change_hand_computed(current, prior, expected):
    assert pct_change(current, prior) == expected


def test_a_zero_base_is_not_reported_as_infinite_growth():
    """'n/a' and '0%' are different facts; a pack that renders them alike lies about one."""
    assert pct_change(Decimal(500), Decimal(0)) is None


@pytest.mark.parametrize(
    "value,places,expected",
    [
        (Decimal("2.5"), 0, Decimal("3")),
        (Decimal("3.5"), 0, Decimal("4")),
        (Decimal("-2.5"), 0, Decimal("-3")),
        (Decimal("1.2345"), 2, Decimal("1.23")),
    ],
)
def test_quantize_is_half_up_not_bankers(value, places, expected):
    # A controller who checks 2.5 → 3 by hand and finds 2 stops trusting the document.
    assert quantize(value, places) == expected


# -------------------------------------------------------------- formatting --


def test_money_renders_per_the_pack_style():
    style = PackStyle()
    assert format_money(Decimal("3815070.61"), style) == "£3,815,071"
    assert format_money(Decimal("-57087.06"), style) == "(£57,087)"
    assert format_money(None, style) == "n/a"


def test_currency_style_is_actually_honoured():
    style = PackStyle.model_validate(
        {
            "currency": {
                "code": "USD",
                "symbol": "$",
                "position": "suffix",
                "thousands": " ",
                "negative": "minus",
            },
            "rounding": {"money": 2, "percent": 1, "ratio": 2},
        }
    )
    assert format_money(Decimal("1234.5"), style) == "1 234.50$"
    assert format_money(Decimal("-1234.5"), style) == "-1 234.50$"


def test_deltas_are_signed_explicitly():
    """In a column of changes, an unsigned '2.9%' reads as a level."""
    style = PackStyle()
    assert format_delta(Decimal("2.8906"), style) == "+2.9%"
    assert format_delta(Decimal("-4.6296"), style) == "-4.6%"
    assert format_delta(None, style) == "n/a"


def test_percent_respects_the_rounding_rule():
    style = PackStyle.model_validate({"rounding": {"money": 0, "percent": 3, "ratio": 2}})
    assert format_percent(Decimal("27.8975"), style) == "27.898%"


# ---------------------------------------------------------------- KPI grid --


def test_kpi_sentiment_comes_from_the_template_not_the_sign(template, period, adapters):
    """Payables rising is not an improvement."""
    from app.assemble.engine import assemble

    pack = assemble(template, period, adapters)
    grid = next(s for s in pack.sections if s.type == "kpi_grid")
    by_id = {k["id"]: k for k in grid.content_json["kpis"]}

    payables = by_id["open_payables"]
    if payables["direction"] == "up":
        assert payables["sentiment"] == "bad"
    elif payables["direction"] == "down":
        assert payables["sentiment"] == "good"


def test_a_kpi_naming_an_unknown_metric_is_visible_not_absent(template, period, adapters):
    """A KPI that quietly disappears from a board pack is the failure mode to prevent."""
    from app.adapters.frame import frame_from_dicts
    from app.assemble.renderers import render_kpi_grid
    from app.template.schema import KpiGridSection

    grid = next(s for s in template.sections if isinstance(s, KpiGridSection))
    frame = frame_from_dicts(
        [
            {
                "metric": "revenue",
                "label": "Revenue",
                "value": Decimal(1),
                "prior_value": None,
                "delta": None,
                "delta_pct": None,
            }
        ],
        source="test",
        dataset="period_metrics",
    )
    content = render_kpi_grid(grid, frame, template.style)
    missing = [k for k in content["kpis"] if k["missing"]]
    assert missing, "every other KPI should be reported missing, not dropped"
    assert "not published by" in missing[0]["note"]
    assert "revenue" in missing[0]["available"]
