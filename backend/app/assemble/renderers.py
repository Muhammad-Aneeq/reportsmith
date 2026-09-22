"""Deterministic renderers: frame + section spec → the section's content.

Zero LLM here, by construction — nothing in this module can reach a model. That is what
makes spec 13 §10's *"same data + template = identical tables"* achievable, and it is
asserted by a test that greps this package for model SDK imports.

Every rendered cell carries both the raw value and its formatted string. The raw value is
what the hashes and the numeric cross-check use; the string is what the reader and the
model see. Keeping both means the narrative can be handed pre-formatted figures — so the
model copies text rather than rounding a number — while verification still compares
Decimals.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.adapters.frame import Frame
from app.formatting import format_delta, format_value
from app.template.schema import (
    FlagsSection,
    KpiGridSection,
    NarrativeSection,
    PackStyle,
    TableSection,
)


def _cell(value: Any, fmt: str, style: PackStyle) -> dict[str, Any]:
    return {
        "value": str(value) if isinstance(value, Decimal) else value,
        "display": format_value(value, fmt, style),
    }


def render_table(section: TableSection, frame: Frame, style: PackStyle) -> dict[str, Any]:
    frame.require(*[c.field for c in section.columns])

    rows = [
        {c.field: _cell(row.get(c.field), c.format, style) for c in section.columns}
        for row in frame.rows
    ]

    total: dict[str, Any] | None = None
    if section.total_row:
        # Only money and integer columns total. Summing a percentage column produces a
        # number with no meaning, and a "Total 412.7%" line in a management pack is the
        # kind of thing that costs a document its credibility.
        total = {}
        for column in section.columns:
            if column.format in ("money", "integer"):
                values = [
                    row.get(column.field)
                    for row in frame.rows
                    if isinstance(row.get(column.field), Decimal | int)
                    and not isinstance(row.get(column.field), bool)
                ]
                summed = sum((Decimal(str(v)) for v in values), Decimal(0))
                total[column.field] = _cell(summed, column.format, style)
            else:
                total[column.field] = {"value": None, "display": ""}
        if section.columns:
            total[section.columns[0].field] = {"value": "Total", "display": "Total"}

    return {
        "columns": [
            {"field": c.field, "label": c.label, "align": c.align, "format": c.format}
            for c in section.columns
        ],
        "rows": rows,
        "total": total,
        "row_count": len(rows),
        "truncated_from": frame.meta.get("truncated_from"),
        "source": frame.source,
        "dataset": frame.dataset,
        "schema_version": frame.schema_version,
    }


def render_kpi_grid(section: KpiGridSection, frame: Frame, style: PackStyle) -> dict[str, Any]:
    """KPIs are looked up by metric name from a long frame.

    A template naming a metric the adapter does not publish produces a KPI marked
    ``missing`` with the available names listed — visible in the pack rather than silently
    absent. A KPI that quietly disappears from a board pack is the failure mode this whole
    product exists to prevent.
    """
    frame.require("metric", "value")
    by_metric = {str(row["metric"]): row for row in frame.rows}

    kpis: list[dict[str, Any]] = []
    for spec in section.kpis:
        row = by_metric.get(spec.metric)
        if row is None:
            kpis.append(
                {
                    "id": spec.id,
                    "label": spec.label,
                    "metric": spec.metric,
                    "missing": True,
                    "display": "n/a",
                    "note": f"metric {spec.metric!r} not published by {frame.source}",
                    "available": sorted(by_metric),
                }
            )
            continue

        value = row.get("value")
        prior = row.get("prior_value")
        delta_pct = row.get("delta_pct") if spec.compare == "prior_period" else None
        direction = "flat"
        if isinstance(delta_pct, Decimal):
            direction = "up" if delta_pct > 0 else "down" if delta_pct < 0 else "flat"

        # Whether a movement is good news is a property of the metric, not the sign.
        # Payables rising is not an improvement; the template says which way is better
        # and the UI colours from this, never from the arithmetic.
        sentiment = "neutral"
        if direction != "flat" and spec.direction != "neutral":
            improving = (direction == "up") == (spec.direction == "higher_is_better")
            sentiment = "good" if improving else "bad"

        kpis.append(
            {
                "id": spec.id,
                "label": spec.label,
                "metric": spec.metric,
                "missing": False,
                "value": str(value) if isinstance(value, Decimal) else value,
                "display": format_value(value, spec.format, style),
                "prior_value": str(prior) if isinstance(prior, Decimal) else prior,
                "prior_display": format_value(prior, spec.format, style),
                "delta_pct": str(delta_pct) if isinstance(delta_pct, Decimal) else None,
                "delta_display": format_delta(delta_pct, style) if spec.compare != "none" else "",
                "direction": direction,
                "sentiment": sentiment,
                "format": spec.format,
            }
        )

    return {
        "kpis": kpis,
        "source": frame.source,
        "dataset": frame.dataset,
        "schema_version": frame.schema_version,
    }


def render_flags(section: FlagsSection, frame: Frame, style: PackStyle) -> dict[str, Any]:
    frame.require("rule_id", "severity")
    items = [
        {
            "rule_id": str(row.get("rule_id")),
            "label": str(row.get("label") or row.get("rule_id")),
            "severity": str(row.get("severity")),
            "severity_rank": int(row.get("severity_rank") or 0),
            "message": str(row.get("message") or ""),
            "evidence": row.get("evidence"),
            "amount_display": (
                format_value(row["amount"], "money", style) if row.get("amount") is not None else None
            ),
            "reference": row.get("txn_id") or row.get("counterparty"),
        }
        for row in frame.rows
    ]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return {
        "items": items,
        "counts": counts,
        "source": frame.source,
        "dataset": frame.dataset,
        "schema_version": frame.schema_version,
    }


def build_figure_refs(
    section: NarrativeSection, frame: Frame, style: PackStyle
) -> list[dict[str, Any]]:
    """The figures a narrative section is *allowed* to cite — and nothing else.

    This is the composer's entire numeric universe (spec 13 F4: *"input = that section's
    bound data + tone rules ONLY"*). Each ref carries a raw Decimal for verification and a
    pre-formatted display string for the prompt, so the model is asked to copy a rendered
    figure rather than to round one itself.
    """
    refs: list[dict[str, Any]] = []
    label_field = next(
        (f for f in ("label", "account_name", "vendor_raw", "line_code") if f in frame.columns),
        None,
    )

    numeric_fields = [
        f
        for f in frame.columns
        if any(isinstance(row.get(f), Decimal) for row in frame.rows)
    ]

    for index, row in enumerate(frame.rows):
        label = str(row.get(label_field)) if label_field else f"row {index + 1}"
        for field_name in numeric_fields:
            value = row.get(field_name)
            if not isinstance(value, Decimal):
                continue
            fmt = (
                "percent"
                if "pct" in field_name or field_name.endswith("_rate")
                else "integer"
                if field_name.endswith("_count")
                else "money"
            )
            refs.append(
                {
                    "ref_id": f"{label_field or 'row'}{index}.{field_name}",
                    "label": _ref_label(label, field_name),
                    "value": str(value),
                    "display": format_value(value, fmt, style),
                    "unit": "percent" if fmt == "percent" else "money" if fmt == "money" else "count",
                }
            )
    return refs


# How a figure's field name reads when the composer copies the label into a sentence.
# "Revenue (prior month)" is something a controller would write; "revenue — prior_amount"
# is a column header that leaked into prose. The composer is handed these verbatim, so
# they have to be publishable English rather than schema.
_FIELD_PHRASES: dict[str, str] = {
    "amount": "",
    "value": "",
    "prior_amount": " (prior month)",
    "prior_value": " (prior month)",
    "delta": " (movement)",
    "delta_pct": " (percentage movement)",
    "txn_count": " (number of items)",
    "queued_count": " (items awaiting review)",
    "auto_rate": " (proportion coded automatically)",
    "avg_confidence": " (average confidence)",
}


def _ref_label(row_label: str, field_name: str) -> str:
    suffix = _FIELD_PHRASES.get(field_name)
    if suffix is None:
        suffix = f" ({field_name.replace('_', ' ')})"
    return f"{row_label}{suffix}"
