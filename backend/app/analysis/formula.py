"""The ratio pack — pure Python, zero LLM, written to StatementLens's P4 shape.

This is the work StatementLens will eventually own (its spec 12 F2 / its PLAN P4). It is
not built upstream yet, so it is built here — emitting the exact shape their PLAN pins,
so that when P4 lands the swap touches only the adapter's reader (PLAN.md **D-018**).

Two rules are inherited verbatim from their design, because both are load-bearing:

**A zero denominator yields ``status="undefined"``** with the zero input named. Never a
``0``, never a NaN, never a raised exception. Zero and "cannot be computed" are different
facts, and a pack that prints `0.00` for the second is stating something false.

**Negative equity computes but carries ``status="caveat"``.** ROE on negative equity is
arithmetically fine and financially meaningless; suppressing it hides a red flag, and
printing it bare invites a wrong reading.

Every formula records the inputs it actually read, so the UI's click-a-number drill-down
is a lookup rather than a re-derivation that could disagree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.money import quantize

Status = Literal["ok", "undefined", "caveat"]
Unit = Literal["ratio", "percent", "days", "money", "times"]

# What a period's figures look like coming in: line_code → amount (or None if absent).
Figures = dict[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class Computation:
    """One computed figure. Mirrors StatementLens's `computations` table (spec 12 §6)."""

    formula_id: str
    label: str
    category: str
    period: str
    value: Decimal | None
    unit: Unit
    status: Status
    inputs: dict[str, str] = field(default_factory=dict)
    note: str = ""
    definition: str = ""

    @property
    def display(self) -> str:
        """How the figure reads in a table cell.

        ``undefined`` renders as a named reason rather than a dash, because a dash in a
        ratio column is read as zero by everyone who has ever seen a spreadsheet.
        """
        if self.value is None:
            return "n/a"
        if self.unit == "percent":
            return f"{quantize(self.value, 1)}%"
        if self.unit == "days":
            return f"{quantize(self.value, 1)} days"
        if self.unit == "times":
            return f"{quantize(self.value, 2)}×"
        if self.unit == "money":
            return f"{quantize(self.value, 0):,}"
        return str(quantize(self.value, 2))


@dataclass(frozen=True, slots=True)
class Formula:
    formula_id: str
    label: str
    category: str
    unit: Unit
    definition: str
    inputs: tuple[str, ...]
    fn: Callable[[Figures], tuple[Decimal | None, Status, str]]


REGISTRY: dict[str, Formula] = {}


def register(
    formula_id: str, label: str, category: str, unit: Unit, definition: str, inputs: tuple[str, ...]
) -> Callable[[Callable[[Figures], tuple[Decimal | None, Status, str]]], Callable]:
    def wrap(fn: Callable[[Figures], tuple[Decimal | None, Status, str]]) -> Callable:
        REGISTRY[formula_id] = Formula(formula_id, label, category, unit, definition, inputs, fn)
        return fn

    return wrap


def _div(
    numerator: Decimal | None,
    denominator: Decimal | None,
    denominator_name: str,
    *,
    scale: Decimal = Decimal(1),
) -> tuple[Decimal | None, Status, str]:
    """The guarded division every ratio goes through. The `undefined` path lives here.

    Centralised so there is exactly one place that decides what a zero denominator
    means — twelve formulas each writing their own guard is twelve chances for one of
    them to return 0.
    """
    if numerator is None or denominator is None:
        missing = "numerator" if numerator is None else denominator_name
        return None, "undefined", f"{missing} not present in these statements"
    if denominator == 0:
        return None, "undefined", f"{denominator_name} is zero"
    return quantize(numerator / denominator * scale, 6), "ok", ""


# ------------------------------------------------------------------ liquidity --


@register("current_ratio", "Current ratio", "Liquidity", "ratio",
          "Current assets ÷ current liabilities", ("total_current_assets", "total_current_liabilities"))
def _current_ratio(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("total_current_assets"), f.get("total_current_liabilities"),
                "current liabilities")


@register("quick_ratio", "Quick ratio", "Liquidity", "ratio",
          "(Current assets − inventory) ÷ current liabilities",
          ("total_current_assets", "inventory", "total_current_liabilities"))
def _quick_ratio(f: Figures) -> tuple[Decimal | None, Status, str]:
    ca, inv = f.get("total_current_assets"), f.get("inventory")
    numerator = None if ca is None else ca - (inv or Decimal(0))
    return _div(numerator, f.get("total_current_liabilities"), "current liabilities")


# -------------------------------------------------------------- profitability --


@register("gross_margin", "Gross margin", "Profitability", "percent",
          "Gross profit ÷ revenue", ("gross_profit", "revenue"))
def _gross_margin(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("gross_profit"), f.get("revenue"), "revenue", scale=Decimal(100))


@register("operating_margin", "Operating margin", "Profitability", "percent",
          "Operating profit ÷ revenue", ("operating_profit", "revenue"))
def _operating_margin(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("operating_profit"), f.get("revenue"), "revenue", scale=Decimal(100))


@register("net_margin", "Net margin", "Profitability", "percent",
          "Net income ÷ revenue", ("net_income", "revenue"))
def _net_margin(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("net_income"), f.get("revenue"), "revenue", scale=Decimal(100))


@register("return_on_assets", "Return on assets", "Profitability", "percent",
          "Net income ÷ total assets", ("net_income", "total_assets"))
def _roa(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("net_income"), f.get("total_assets"), "total assets", scale=Decimal(100))


@register("return_on_equity", "Return on equity", "Profitability", "percent",
          "Net income ÷ total equity", ("net_income", "total_equity"))
def _roe(f: Figures) -> tuple[Decimal | None, Status, str]:
    equity = f.get("total_equity")
    value, status, note = _div(f.get("net_income"), equity, "total equity", scale=Decimal(100))
    if status == "ok" and equity is not None and equity < 0:
        # Computes, but the sign is an artefact: negative income over negative equity
        # reads as a positive return. Flagging beats hiding and beats printing bare.
        return value, "caveat", "equity is negative; the sign of this ratio is not meaningful"
    return value, status, note


# ------------------------------------------------------------------- leverage --


@register("debt_to_equity", "Debt to equity", "Leverage", "ratio",
          "Total liabilities ÷ total equity", ("total_liabilities", "total_equity"))
def _dte(f: Figures) -> tuple[Decimal | None, Status, str]:
    equity = f.get("total_equity")
    value, status, note = _div(f.get("total_liabilities"), equity, "total equity")
    if status == "ok" and equity is not None and equity < 0:
        return value, "caveat", "equity is negative; gearing is better read from the balance sheet"
    return value, status, note


@register("interest_cover", "Interest cover", "Leverage", "times",
          "Operating profit ÷ interest expense", ("operating_profit", "interest_expense"))
def _interest_cover(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("operating_profit"), f.get("interest_expense"), "interest expense")


# ----------------------------------------------------------------- efficiency --


def _days_formula(numerator_key: str, base_key: str, label_base: str):
    def fn(f: Figures) -> tuple[Decimal | None, Status, str]:
        # Monthly statements, so the conversion base is the period, not a year. Using 365
        # on a one-month set inflates every days metric by ~12× — the classic version of
        # this bug, and the reason the base is named in the definition string.
        return _div(f.get(numerator_key), f.get(base_key), label_base, scale=Decimal(30))

    return fn


REGISTRY["receivable_days"] = Formula(
    "receivable_days", "Receivable days", "Efficiency", "days",
    "Accounts receivable ÷ revenue × 30 (monthly basis)",
    ("accounts_receivable", "revenue"),
    _days_formula("accounts_receivable", "revenue", "revenue"),
)
REGISTRY["payable_days"] = Formula(
    "payable_days", "Payable days", "Efficiency", "days",
    "Accounts payable ÷ cost of sales × 30 (monthly basis)",
    ("accounts_payable", "cogs"),
    _days_formula("accounts_payable", "cogs", "cost of sales"),
)
REGISTRY["inventory_days"] = Formula(
    "inventory_days", "Inventory days", "Efficiency", "days",
    "Inventory ÷ cost of sales × 30 (monthly basis)",
    ("inventory", "cogs"),
    _days_formula("inventory", "cogs", "cost of sales"),
)


# ------------------------------------------------------------------ cash flow --


@register("operating_cf_ratio", "Operating cash flow ratio", "Cash flow", "ratio",
          "Operating cash flow ÷ current liabilities",
          ("cf_operating", "total_current_liabilities"))
def _ocf_ratio(f: Figures) -> tuple[Decimal | None, Status, str]:
    return _div(f.get("cf_operating"), f.get("total_current_liabilities"), "current liabilities")


@register("accruals_ratio", "Accruals ratio", "Cash flow", "percent",
          "(Net income − operating cash flow) ÷ total assets",
          ("net_income", "cf_operating", "total_assets"))
def _accruals(f: Figures) -> tuple[Decimal | None, Status, str]:
    ni, ocf = f.get("net_income"), f.get("cf_operating")
    numerator = None if ni is None or ocf is None else ni - ocf
    return _div(numerator, f.get("total_assets"), "total assets", scale=Decimal(100))


def compute_all(figures: Figures, period: str) -> list[Computation]:
    """Run every registered formula against one period's figures.

    Registry order, not sorted: the pack reads liquidity → profitability → leverage →
    efficiency → cash flow, which is how a reviewer scans a ratio page.
    """
    out: list[Computation] = []
    for formula in REGISTRY.values():
        value, status, note = formula.fn(figures)
        out.append(
            Computation(
                formula_id=formula.formula_id,
                label=formula.label,
                category=formula.category,
                period=period,
                value=value,
                unit=formula.unit,
                status=status,
                inputs={k: str(figures.get(k)) for k in formula.inputs},
                note=note,
                definition=formula.definition,
            )
        )
    return out
