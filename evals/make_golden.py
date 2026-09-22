"""Regenerate the committed golden files.

Run via `make golden`. The output is committed, so any change in assembly shows up as a
reviewable diff in a pull request rather than as a surprise in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.assemble.engine import assemble, default_adapters  # noqa: E402
from app.periods import default_period, next_period  # noqa: E402
from app.template.store import default_template  # noqa: E402

OUT = REPO / "evals" / "golden"


def canonical(pack) -> str:
    return json.dumps(
        {
            "template_ref": pack.template_ref,
            "period": pack.period,
            "structure_hash": pack.structure_hash,
            "value_digest": pack.value_digest,
            "sections": [s.as_row() for s in pack.sections],
        },
        indent=2,
        sort_keys=True,
        default=str,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    template = default_template()
    adapters = default_adapters()
    first = default_period().id
    periods = [first, next_period(first).id]

    for period in periods:
        pack = assemble(template, period, adapters)
        path = OUT / f"{template.id}-{period}.json"
        path.write_text(canonical(pack), encoding="utf-8", newline="\n")
        print(
            f"  {path.relative_to(REPO)}  structure={pack.structure_hash[:12]} "
            f"values={pack.value_digest[:12]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
