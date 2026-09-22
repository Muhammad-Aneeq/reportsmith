"""The StatementLens adapter.

Reads the in-repo analysis today (`app/analysis/`), and the live spec-12 §7 endpoints
once StatementLens reaches P4/P5. Both produce the same shape, which is the whole point:
**this file's `fetch` is the only thing that changes when upstream ships** (PLAN.md
**D-018**). The datasets, the column names, the assembler, the templates, the golden
files and the narrative prompts all stay exactly as they are.

`segment_ratios` is deliberately absent from the catalog. The default template binds a
section to it, so the default pack carries one real, structural GAP — the data source
genuinely has no segment dimension — and a human has to waive it before the pack can be
issued. That is spec 13 F2 and F5 demonstrated on the default path rather than in a test.
"""

from __future__ import annotations

from app.adapters.frame import Frame, Value, frame_from_dicts
from app.analysis.engine import analyse, prior_computations_for
from app.settings import settings


class StatementLensAdapter:
    """Ratios and flags, in StatementLens's own P4/P5 shapes."""

    name = "statementlens"
    # The version string admits its provenance: this is the upstream *shape*, produced
    # by an in-repo implementation, because upstream has not written P4/P5 yet.
    SCHEMA_VERSION = "statementlens/v1(spec12 §6 + upstream PLAN P4/P5 shape; in-repo impl)"

    def __init__(self, profile: str | None = None, seed: int | None = None) -> None:
        self.profile = profile or settings.profile
        self.seed = seed if seed is not None else settings.seed

    def catalog(self) -> tuple[str, ...]:
        # Note what is NOT here: `segment_ratios`. See the module docstring.
        return ("ratios", "flags")

    def _ratios(self, period: str) -> Frame:
        computations, _ = analyse(period, self.profile, self.seed)
        prior = prior_computations_for(period, self.profile, self.seed)
        rows: list[dict[str, Value]] = []
        for comp in computations:
            prior_comp = prior.get(comp.formula_id)
            rows.append(
                {
                    "formula_id": comp.formula_id,
                    "label": comp.label,
                    "category": comp.category,
                    "value": comp.value,
                    "display": comp.display,
                    "prior_value": prior_comp.value if prior_comp else None,
                    "prior_display": prior_comp.display if prior_comp else "n/a",
                    "unit": comp.unit,
                    "status": comp.status,
                    "note": comp.note,
                    "definition": comp.definition,
                }
            )
        return frame_from_dicts(
            rows,
            source=self.name,
            dataset="ratios",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period},
        )

    def _flags(self, period: str) -> Frame:
        _, flags = analyse(period, self.profile, self.seed)
        rows: list[dict[str, Value]] = [
            {
                "rule_id": flag.rule_id,
                "label": flag.label,
                "severity": flag.severity,
                "severity_rank": flag.severity_rank,
                "message": " ".join(flag.message.split()),
                "evidence": "; ".join(f"{k}: {v}" for k, v in flag.evidence.items()) or None,
            }
            for flag in flags
        ]
        return frame_from_dicts(
            rows,
            # Explicit columns: a period with no flags is a good month, and the table
            # must still know its own shape to render an empty state rather than vanish.
            columns=("rule_id", "label", "severity", "severity_rank", "message", "evidence"),
            source=self.name,
            dataset="flags",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period},
        )

    def fetch(self, dataset: str, period: str) -> Frame:
        if dataset == "ratios":
            return self._ratios(period)
        if dataset == "flags":
            return self._flags(period)
        raise KeyError(f"statementlens publishes no dataset {dataset!r}")
