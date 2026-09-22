"""Claims this repo makes about itself, asserted rather than trusted."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_makefile_and_powershell_expose_the_same_targets():
    """A parity claim nobody checks stops being true in about a week."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    make_targets = {
        line.split(":")[0]
        for line in makefile.splitlines()
        if re.match(r"^[a-z][a-z0-9-]*:.*## ", line)
    }

    ps = (REPO / "make.ps1").read_text(encoding="utf-8")
    ps_targets = set(re.findall(r"^\s{4}'([a-z][a-z0-9-]*)'\s*\{", ps, re.M)) - {"default"}

    missing_from_ps = make_targets - ps_targets
    missing_from_make = ps_targets - make_targets - {"help"}
    assert not missing_from_ps, f"make.ps1 is missing: {sorted(missing_from_ps)}"
    assert not missing_from_make, f"Makefile is missing: {sorted(missing_from_make)}"


def test_the_shipped_template_is_installed_by_a_fresh_database(db_session):
    """`make dev` on a fresh clone must render the default template with no setup."""
    from app.models import TemplateRow

    rows = db_session.query(TemplateRow).all()
    assert any(r.template_id == "monthly_management_pack" for r in rows)


def test_mock_is_the_default_so_a_fresh_clone_needs_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.narrate.composer import get_composer

    assert get_composer().name.startswith("mock")


def test_no_langchain_classic_chains_anywhere():
    """Spec 00 F: *"no LangChain-classic chains (LCEL/LangGraph only)"*."""
    app_dir = REPO / "backend" / "app"
    for module in app_dir.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "from langchain.chains" not in source, module.name
        assert "LLMChain" not in source, module.name


def test_every_blocker_referenced_in_the_plan_exists():
    plan = (REPO / "PLAN.md").read_text(encoding="utf-8")
    blockers = (REPO / "BLOCKERS.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"BLOCKERS?\s+\*\*(B\d)\*\*", plan))
    for blocker in referenced:
        assert re.search(rf"\b{blocker}\b", blockers), (
            f"PLAN cites {blocker}; BLOCKERS has no entry"
        )


def test_every_decision_referenced_is_defined():
    """A dangling D-0xx reference is a decision somebody meant to write down and did not."""
    plan = (REPO / "PLAN.md").read_text(encoding="utf-8")
    defined = set(re.findall(r"^\| \*\*(D-\d{3})\*\*", plan, re.M))

    sources = [
        *(REPO / "backend" / "app").rglob("*.py"),
        *(REPO / "backend" / "numcheck").glob("*.py"),
        *(REPO / "frontend" / "src").rglob("*.ts*"),
    ]
    referenced: set[str] = set()
    for path in sources:
        referenced |= set(re.findall(r"\bD-(\d{3})\b", path.read_text(encoding="utf-8")))

    dangling = {f"D-{n}" for n in referenced} - defined
    assert not dangling, f"code cites decisions the plan does not define: {sorted(dangling)}"


@pytest.mark.parametrize(
    "doc",
    ["PLAN.md", "PROGRESS.md", "BLOCKERS.md", "README.md", "MODEL_COSTS.md", "FINAL_REPORT.md"],
)
def test_required_documents_exist_and_are_not_stubs(doc):
    path = REPO / doc
    assert path.exists(), f"{doc} is missing"
    assert len(path.read_text(encoding="utf-8")) > 800, f"{doc} looks like a stub"


def test_readme_leads_with_the_things_the_brief_requires():
    """The brief names four things the README must carry. Checked by meaning, not by an
    exact substring — an earlier version of this test looked for the literal "define once"
    and failed on "Define the pack once", which is the same claim written better."""
    readme = (REPO / "README.md").read_text(encoding="utf-8").lower()

    assert "the pack once" in readme and "review forever" in readme, (
        "the positioning line is missing"
    )
    assert "all data is synthetic" in readme, "the synthetic-data banner is missing"
    assert "## status" in readme, "there is no honest STATUS section"
    assert "sign-off" in readme, "the governance section is missing"
    assert "tracked edits" in readme, "the tracked-edits governance point is missing"


def test_final_report_carries_sibling_notes():
    report = (REPO / "FINAL_REPORT.md").read_text(encoding="utf-8")
    assert "SIBLING_NOTES" in report
    for sibling in ("spendsort", "statementlens"):
        assert sibling in report.lower(), f"SIBLING_NOTES says nothing about {sibling}"
