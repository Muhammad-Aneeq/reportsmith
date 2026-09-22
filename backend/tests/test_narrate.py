"""The composer: structural isolation, the retry, the drop, and the linter."""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from app.assemble.engine import assemble
from app.narrate.composer import DraftRequest, MockComposer
from app.narrate.graph import compose_section
from app.narrate.lint import has_blocking_violations, lint
from app.template.schema import NarrativeSection
from numcheck import FigureRef, verify


def _narrative(template, period, adapters):
    pack = assemble(template, period, adapters)
    section = next(s for s in pack.sections if s.type == "narrative" and not s.has_gap)
    spec = template.section(section.section_key)
    assert isinstance(spec, NarrativeSection)
    return spec, section


# ------------------------------------------------------------------ isolation --


def test_the_composer_cannot_receive_the_world():
    """Spec 13 F4's isolation is structural: there is no parameter to smuggle it through."""
    params = set(inspect.signature(DraftRequest.__init__).parameters) - {"self"}
    forbidden = {"world", "pack", "sections", "ledger", "db", "session", "snapshot", "adapters"}
    assert not (params & forbidden), f"DraftRequest exposes {params & forbidden}"


def test_the_prompt_contains_nothing_but_the_section(template, period, adapters):
    """A canary planted outside the bound frame must not appear in the prompt."""
    from app.narrate.prompts import build_messages

    spec, section = _narrative(template, period, adapters)
    refs = [
        FigureRef(
            ref_id=r["ref_id"],
            value=Decimal(str(r["value"])),
            unit=r.get("unit", "bare"),
            label=r.get("label", ""),
        )
        for r in section.content_json["figure_refs"]
    ]
    request = DraftRequest(
        section_key=spec.id,
        title=spec.title,
        period=period,
        figure_refs=refs,
        display_by_ref={r["ref_id"]: r["display"] for r in section.content_json["figure_refs"]},
        tone_rules=list(spec.tone_rules),
        style=template.style,
        max_words=spec.max_words,
        prompt_version="test",
    )
    system, human = build_messages(request)
    combined = system + human

    for canary in ("CP-0", "INV-", "Northgate Systems Limited", "txn", "GL-0"):
        assert canary not in combined, f"the prompt leaked {canary!r} from outside the frame"


# ---------------------------------------------------------------- the pipeline --


def test_a_clean_draft_verifies(template, period, adapters):
    spec, section = _narrative(template, period, adapters)
    result = compose_section(spec, template, period, section.content_json)
    assert result.verified
    assert result.figures_checked > 0
    assert not result.dropped_sentences


def test_the_faulty_mock_is_caught(template, period, adapters):
    """D-014 — the gate must be observed failing before it is trusted when green."""
    spec, section = _narrative(template, period, adapters)
    result = compose_section(
        spec, template, period, section.content_json, composer=MockComposer(faulty=True)
    )
    assert result.retried, "an unsupportable figure must trigger the retry"
    assert result.dropped_sentences, "the offending sentence must be removed"
    assert "approximately" in result.dropped_sentences[0]
    # What survives is verified — the fabrication did not reach the document.
    assert result.verified


def test_the_ai_draft_of_record_is_the_first_output(template, period, adapters):
    """Not the post-processed text — storing that would erase the evidence of processing."""
    spec, section = _narrative(template, period, adapters)
    result = compose_section(
        spec, template, period, section.content_json, composer=MockComposer(faulty=True)
    )
    assert "approximately" in result.ai_draft
    assert "approximately" not in result.text


def test_the_composer_is_deterministic(template, period, adapters):
    spec, section = _narrative(template, period, adapters)
    a = compose_section(spec, template, period, section.content_json)
    b = compose_section(spec, template, period, section.content_json)
    assert a.text == b.text


def test_prompt_version_tracks_the_template_version(template, period, adapters):
    spec, section = _narrative(template, period, adapters)
    result = compose_section(spec, template, period, section.content_json)
    assert result.prompt_version == f"{template.id}@v{template.version}/{spec.id}"


def test_mock_is_the_default_with_no_api_key(template, period, adapters):
    from app.narrate.composer import get_composer

    assert get_composer().name.startswith("mock")


# -------------------------------------------------------------------- linter --


def test_taboo_phrases_are_flagged_and_never_auto_fixed(template):
    text = "Revenue showed strong performance and a robust margin."
    fixed, violations = lint(text, template.style)
    assert fixed == text, "the linter must not rewrite a judgement"
    taboo = [v for v in violations if v.rule == "taboo_phrase"]
    assert len(taboo) >= 2
    assert all(not v.fixed for v in taboo)
    assert has_blocking_violations(violations)


def test_negatives_are_reformatted_but_not_revalued(template):
    fixed, violations = lint("The loss was -£57,087 this month.", template.style)
    assert "(£57,087)" in fixed
    assert any(v.rule == "currency.negative" and v.fixed for v in violations)


def test_lint_never_changes_a_figures_verification(template):
    """The guarantee behind D-015: a formatting fix cannot invalidate the cross-check."""
    refs = [FigureRef(ref_id="op", value=Decimal("-57087.06"), unit="money", label="Operating")]
    for text in (
        "The loss was -£57,087 this month.",
        "The  loss was  -£57,087 .",
        "A loss of (£57,087) was recorded.",
    ):
        before = verify(text, refs).ok
        fixed, _ = lint(text, template.style)
        assert verify(fixed, refs).ok == before, f"lint changed the verdict for {text!r}"


def test_long_sentences_are_flagged(template):
    long_sentence = "Revenue " + " ".join(["word"] * 40) + " ended."
    _, violations = lint(long_sentence, template.style)
    assert any(v.rule == "max_sentence_words" for v in violations)


def test_recommendation_language_is_flagged_when_the_voice_forbids_it(template):
    _, violations = lint("The business should reduce its payables.", template.style)
    assert any(v.rule == "voice.no_recommendations" for v in violations)


@pytest.mark.live
def test_live_model_draft(template, period, adapters):
    """Excluded from `make test`. Needs OPENAI_API_KEY and costs a few cents."""
    from app.narrate.composer import OpenAIComposer

    spec, section = _narrative(template, period, adapters)
    result = compose_section(
        spec, template, period, section.content_json, composer=OpenAIComposer()
    )
    assert result.text
    assert result.verified, f"live draft failed the cross-check: {result.dropped_sentences}"
