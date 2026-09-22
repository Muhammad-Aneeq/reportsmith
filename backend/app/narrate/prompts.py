"""Prompts, versioned by (template_id, template_version, section_id).

Spec 13 §8: *"Prompts versioned per template version: changing a template's tone rules is a
tracked, evaluable event."* The version string is stored on the pack and keyed on in the
eval report, so a tone-rule edit shows up as a different prompt id rather than as a quiet
change in how the packs read.

The figures are given to the model **pre-formatted**. It is asked to copy a rendered string
like `£3,815,071`, not to round `3815070.61` itself. Every rounding decision the model is
not asked to make is a numeric-fidelity failure that cannot happen.
"""

from __future__ import annotations

from app.narrate.composer import DraftRequest


def prompt_version(template_id: str, template_version: int, section_id: str) -> str:
    return f"{template_id}@v{template_version}/{section_id}"


def build_messages(request: DraftRequest, *, attempt: int = 1) -> tuple[str, str]:
    """(system, human). Built only from the request — see composer.py on isolation."""
    style = request.style

    system = "\n".join(
        [
            "You write one section of a monthly finance pack for a controller to review.",
            "",
            "ABSOLUTE RULES:",
            "1. Every number you write MUST be copied exactly from the FIGURES list below.",
            "   Do not compute, re-round, combine or estimate. If a number you want is not",
            "   in the list, do not write that sentence.",
            "2. You have not been given the underlying ledger and must not refer to anything",
            "   outside the FIGURES list. You cannot know causes; do not offer any.",
            "3. Write prose only. No headings, no bullet points, no tables.",
            "",
            f"VOICE: {style.voice}",
            f"Maximum {style.max_sentence_words} words per sentence.",
            (
                "Never use these words or phrases: "
                + ", ".join(repr(p) for p in style.taboo_phrases)
                if style.taboo_phrases
                else ""
            ),
        ]
    ).strip()

    figures = "\n".join(
        f"  - {ref.label}: {request.display_by_ref.get(ref.ref_id, ref.value)}"
        for ref in request.figure_refs
    )
    rules = "\n".join(f"  {i}. {rule}" for i, rule in enumerate(request.tone_rules, 1))

    human_parts = [
        f"SECTION: {request.title}",
        f"PERIOD: {request.period}",
        "",
        "FIGURES (the only numbers you may write):",
        figures,
        "",
        "SECTION RULES:" if rules else "",
        rules,
        "",
        f"Write at most {request.max_words} words.",
    ]

    if attempt > 1:
        # The retry is told what went wrong in general terms, not which sentence to
        # rewrite. Handing back the offending sentence invites a cosmetic edit that keeps
        # the invented figure; re-drafting from the figures is what is actually wanted.
        human_parts += [
            "",
            "Your previous draft contained a number that is not in the FIGURES list.",
            "Write it again, copying every number exactly from that list.",
        ]

    return system, "\n".join(p for p in human_parts if p is not None).strip()
