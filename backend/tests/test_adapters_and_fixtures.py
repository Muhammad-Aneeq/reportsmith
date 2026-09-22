"""The adapters, and the reconciliation that makes a derived fixture worth having."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from app.adapters.base import SchemaMismatch
from app.adapters.ledgerfab_adapter import LedgerfabAdapter
from app.adapters.spendsort_adapter import (
    EXPECTED_COLUMNS,
    SpendSortAdapter,
    strip_injection_guard,
)
from app.adapters.statementlens_adapter import StatementLensAdapter


def test_spendsort_total_reconciles_to_the_ledger(period):
    """The property a hand-written fixture could never have (PLAN.md D-006).

    If this fails, the pack's category table no longer adds up to its own P&L cost line —
    which a controller would spot in seconds and which would end the document's
    credibility.
    """
    categories = SpendSortAdapter().fetch("categories", period)
    gl = LedgerfabAdapter().fetch("gl_expense_lines", period)

    category_total = sum((r["amount"] for r in categories.rows), Decimal(0))
    gl_total = sum((r["amount"] for r in gl.rows), Decimal(0))
    assert category_total == gl_total, (
        f"SpendSort categories total {category_total} but the GL says {gl_total}"
    )


def test_spendsort_fixture_is_a_real_export():
    """Its header is SpendSort's own COLUMNS tuple, not our reading of the spec."""
    path = SpendSortAdapter().dir / "2024-07.csv"
    assert path.exists(), "run `make fixtures`"
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "the real export is utf-8-sig; the BOM is the tell"
    header = raw.decode("utf-8-sig").splitlines()[0].split(",")
    assert tuple(header) == EXPECTED_COLUMNS


@pytest.mark.parametrize(
    "stored,expected",
    [
        ("'-EDF Energy", "-EDF Energy"),   # the exporter added this quote
        ("'=SUM(A1)", "=SUM(A1)"),
        ("'@handle", "@handle"),
        ("'Round Table Ltd", "'Round Table Ltd"),  # genuinely part of the name — kept
        ("Northgate Systems", "Northgate Systems"),
        ("", ""),
    ],
)
def test_injection_guard_is_stripped_narrowly(stored, expected):
    assert strip_injection_guard(stored) == expected


def test_missing_period_file_is_an_error_naming_what_exists(tmp_path):
    adapter = SpendSortAdapter(fixtures_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="make fixtures"):
        adapter.fetch("categories", "1999-01")


def test_schema_change_upstream_is_a_named_mismatch(tmp_path):
    """When SpendSort changes its export, ReportSmith must say so, not mis-parse."""
    (tmp_path / "2024-07.csv").write_text(
        "date,vendor_raw,amount\n2024-07-01,X,1.00\n", encoding="utf-8-sig"
    )
    with pytest.raises(SchemaMismatch) as exc:
        SpendSortAdapter(fixtures_dir=tmp_path).fetch("categories", "2024-07")
    assert "account" in str(exc.value)
    assert "schema has probably changed" in str(exc.value)


def test_statementlens_does_not_publish_segment_ratios():
    """The default template's honest gap depends on this staying true."""
    assert "segment_ratios" not in StatementLensAdapter().catalog()


def test_every_adapter_declares_its_provenance():
    for adapter in (LedgerfabAdapter(), SpendSortAdapter(), StatementLensAdapter()):
        assert adapter.SCHEMA_VERSION
        assert "/" in adapter.SCHEMA_VERSION, "a schema version should name its source"


def test_money_is_decimal_at_every_boundary(period):
    """One float anywhere and the fidelity gate starts failing for the wrong reason."""
    for adapter in (LedgerfabAdapter(), SpendSortAdapter(), StatementLensAdapter()):
        for dataset in adapter.catalog():
            frame = adapter.fetch(dataset, period)
            for row in frame.rows:
                for key, value in row.items():
                    assert not isinstance(value, float), (
                        f"{adapter.name}.{dataset}.{key} is a float: {value!r}"
                    )


def test_ratios_never_return_zero_for_undefined(period):
    """A zero denominator must read 'n/a', never '0.00' (upstream's P4 rule)."""
    from app.analysis.formula import compute_all

    computations = compute_all({"revenue": Decimal(0), "gross_profit": Decimal(100)}, period)
    margin = next(c for c in computations if c.formula_id == "gross_margin")
    assert margin.status == "undefined"
    assert margin.value is None
    assert margin.display == "n/a"
    assert "revenue is zero" in margin.note


def test_negative_equity_computes_with_a_caveat(period):
    from app.analysis.formula import compute_all

    computations = compute_all(
        {"net_income": Decimal(-100), "total_equity": Decimal(-50)}, period
    )
    roe = next(c for c in computations if c.formula_id == "return_on_equity")
    assert roe.status == "caveat"
    assert roe.value is not None
    assert "negative" in roe.note


def test_an_undefined_metric_never_fires_a_flag(period):
    """The cry-wolf bug: 'current ratio below 1' must not fire on a division by zero."""
    from app.analysis.flags import evaluate_rules
    from app.analysis.formula import compute_all

    figures = {"total_current_assets": Decimal(100), "total_current_liabilities": Decimal(0)}
    computations = compute_all(figures, period)
    flags = evaluate_rules(computations, figures, {}, period)
    assert not any(f.rule_id == "current_ratio_below_one" for f in flags)


def test_rules_load_and_are_unique():
    from app.analysis.flags import load_rules

    rules = load_rules()
    assert len(rules) >= 12
    assert len({r.rule_id for r in rules}) == len(rules)
    for name in ("current_ratio_below_one", "receivable_days_rising_on_flat_revenue",
                 "margin_compression", "negative_ocf_positive_ni"):
        assert any(r.rule_id == name for r in rules), f"spec 12 F4 names {name}"


def test_rule_files_reject_unknown_keys(tmp_path: Path):
    from app.analysis.flags import RuleError, load_rules

    (tmp_path / "bad.yaml").write_text(
        "rules:\n  - rule_id: x\n    label: X\n    severity: high\n"
        "    message: m\n    when: {selector: ratio.current_ratio, value: 1}\n    typo: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(RuleError, match="unknown keys"):
        load_rules(tmp_path)
