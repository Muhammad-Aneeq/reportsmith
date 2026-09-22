"""End-to-end: the default template on two periods, both issued, diff correct.

Spec 13 §10: *"E2E: default template on 2 ledgerfab periods → both packs issue; diff view
correct."* This is the third CI gate, and it exercises the product the way the definition of
done describes it — assemble, narrate, approve, waive, sign, archive, verify, diff.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

WORK = Path(tempfile.mkdtemp(prefix="reportsmith-e2e-"))
import os  # noqa: E402

os.environ["REPORTSMITH_ARCHIVE_DIR"] = str(WORK / "archive")
os.environ["REPORTSMITH_DATABASE_URL"] = f"sqlite:///{WORK / 'e2e.db'}"

import app.db as db_module  # noqa: E402
from app import service  # noqa: E402
from app.issue.archive import verify_archive  # noqa: E402
from app.periods import default_period, next_period  # noqa: E402

WAIVER = "No segment dimension exists in the current data sources; accepted for this period."


def issue(db, period: str) -> dict:
    pack = service.create_pack(db, "monthly_management_pack", period)
    data = service.pack_to_json(db, pack)

    assert len(data["sections"]) == 11, f"expected 11 sections, got {len(data['sections'])}"
    assert data["blockers"], "a freshly assembled pack should not be signable"

    for section in data["sections"]:
        service.approve_section(db, section["id"], "A. Controller")

    waivers = [
        {"section_key": gap["section_key"], "reason": WAIVER}
        for gap in data["gaps"]
        if gap["required"]
    ]
    issued = service.signoff(db, pack.id, "A. Controller", waivers)
    final = service.pack_to_json(db, issued)

    assert final["status"] == "issued", final["status"]
    assert final["archive"], "issuance produced no archive"
    verdict = verify_archive(pack.id)
    assert verdict["ok"], verdict["problems"]

    print(
        f"  {period}: issued · {len(waivers)} waiver(s) · "
        f"hash {final['archive']['content_hash'][:16]} · archive verified"
    )
    return final


def main() -> int:
    try:
        db_module.init_db()
        first = default_period().id
        second = next_period(first).id

        print(f"E2E · {first} then {second}")
        with db_module.session_scope() as db:
            a = issue(db, first)
            b = issue(db, second)

        structure_same = a["structure_hash"] == b["structure_hash"]
        values_differ = a["value_digest"] != b["value_digest"]
        print(f"  structure identical : {structure_same}")
        print(f"  numbers changed     : {values_differ}")

        problems = []
        if not structure_same:
            problems.append("the two packs do not share a structure hash")
        if not values_differ:
            problems.append("the two periods produced identical figures")

        (REPO / "evals" / "results").mkdir(parents=True, exist_ok=True)
        (REPO / "evals" / "results" / "e2e.json").write_text(
            json.dumps(
                {
                    "periods": [first, second],
                    "both_issued": True,
                    "structure_identical": structure_same,
                    "values_differ": values_differ,
                    "problems": problems,
                },
                indent=2,
            ),
            encoding="utf-8",
            newline="\n",
        )

        if problems:
            print("\nE2E FAILED:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("\nPASS — two periods, one template, both issued, structure held.")
        return 0
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
