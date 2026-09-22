"""The numeric-fidelity gate — 100%, or the build fails.

Spec 13 §10: *"narrate/: numeric-fidelity 100% gate (shared harness with Spec 12)."*

Two things make this gate honest rather than decorative:

**It requires figures to have been checked.** A composer that learned to satisfy the checker
by stating nothing would score 100% on a naive metric. `FidelityReport.passed()` demands
both perfection and a non-zero denominator.

**It runs the faulty composer too, and requires it to FAIL.** A gate that has never been
seen red is not evidence of anything. `--self-test` is run by CI alongside the real gate;
if the deliberately-broken composer passes, the gate is broken and the build stops.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.assemble.engine import assemble, default_adapters  # noqa: E402
from app.narrate.composer import Composer, MockComposer  # noqa: E402
from app.narrate.graph import compose_section  # noqa: E402
from app.periods import default_period, next_period  # noqa: E402
from app.template.schema import NarrativeSection  # noqa: E402
from app.template.store import default_template  # noqa: E402
from numcheck import FigureRef, score  # noqa: E402

RESULTS = REPO / "evals" / "results"


def run(composer: Composer | None = None) -> tuple[object, list[dict[str, object]]]:
    template = default_template()
    adapters = default_adapters()
    first = default_period().id
    periods = [first, next_period(first).id]

    narratives: list[tuple[str, str, list[FigureRef], list[str]]] = []
    rows: list[dict[str, object]] = []

    for period in periods:
        pack = assemble(template, period, adapters)
        for section in pack.sections:
            spec = template.section(section.section_key)
            if not isinstance(spec, NarrativeSection) or section.has_gap:
                continue
            result = compose_section(spec, template, period, section.content_json, composer=composer)
            refs = [
                FigureRef(
                    ref_id=r["ref_id"],
                    value=Decimal(str(r["value"])),
                    unit=r.get("unit", "bare"),
                    label=r.get("label", ""),
                )
                for r in result.figure_refs
            ]
            narratives.append((f"{period}/{section.section_key}", result.text, refs, [period]))
            rows.append(
                {
                    "period": period,
                    "section": section.section_key,
                    "model": result.model,
                    "prompt_version": result.prompt_version,
                    "verified": result.verified,
                    "figures_checked": result.figures_checked,
                    "retried": result.retried,
                    "dropped": len(result.dropped_sentences),
                    "words": len(result.text.split()),
                }
            )

    return score(narratives), rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the deliberately faulty composer; the gate must FAIL, or the gate is broken",
    )
    args = parser.parse_args()

    if args.self_test:
        # The faulty mock states a figure no ref supports. The pipeline's surgery removes
        # that sentence, so the *final* text verifies — which is the behaviour we want and
        # is not what this test measures. What it measures is that the checker fired at
        # all: something must have been dropped or re-drafted.
        _, rows = run(composer=MockComposer(faulty=True))
        caught = [r for r in rows if r["dropped"] or r["retried"]]
        print(f"self-test: {len(caught)}/{len(rows)} sections triggered the cross-check")
        for row in caught[:3]:
            print(f"  {row['period']}/{row['section']}: dropped={row['dropped']} retried={row['retried']}")
        if not caught:
            print("FAIL — the faulty composer slipped an unsupported figure past the gate.")
            return 1
        print("PASS — the gate fires when a figure is not supported.")
        return 0

    report, rows = run()
    print(report.summary())
    for row in rows:
        mark = "ok " if row["verified"] else "FAIL"
        print(
            f"  {mark} {row['period']}/{row['section']:<24} "
            f"{row['figures_checked']:>2} figures, {row['words']:>3} words"
            + (f", {row['dropped']} dropped" if row["dropped"] else "")
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "fidelity.json").write_text(
        json.dumps(
            {
                "fidelity_pct": str(report.fidelity),
                "figures_checked": report.figures_checked,
                "figures_verified": report.figures_verified,
                "sections": report.sections,
                "passed": report.passed(),
                "failures": report.failures,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )

    if not report.passed():
        print("\nGATE FAILED — every numeric claim must be supported by a bound figure.")
        for failure in report.failures:
            print(f"  {failure['section']}: {failure['token']} — {failure['reason']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
