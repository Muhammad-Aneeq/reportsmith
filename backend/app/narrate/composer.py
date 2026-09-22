"""The composer boundary: a protocol, a deterministic mock, and the live model.

The isolation required by spec 13 F4 — *"input = that section's bound data + tone rules
ONLY"* — is **structural, not prompted**. `draft()` takes a `DraftRequest` carrying the
section's figure refs, its tone rules and the pack style. There is no parameter through
which the world, the other sections, or the raw ledger could arrive, so no prompt-injection
of context is possible because there is no context to inject.

`MockComposer` is the default, so a fresh clone runs the whole product with no API key.

**`MockComposer(faulty=True)` emits a number that no figure supports.** A mock that always
satisfied the cross-check would make a 100% fidelity gate vacuous — green on an empty
check. The faulty mode is what lets the gate be *observed failing* before it is trusted
when green (PLAN.md **D-014**).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.settings import settings
from app.template.schema import PackStyle
from numcheck import FigureRef


@dataclass(frozen=True, slots=True)
class DraftRequest:
    """Everything the composer is allowed to see. Deliberately small."""

    section_key: str
    title: str
    period: str
    figure_refs: list[FigureRef]
    display_by_ref: dict[str, str]
    tone_rules: list[str]
    style: PackStyle
    max_words: int
    prompt_version: str


@dataclass(frozen=True, slots=True)
class DraftResult:
    text: str
    model: str
    cited_refs: list[str] = field(default_factory=list)


@runtime_checkable
class Composer(Protocol):
    name: str

    def draft(self, request: DraftRequest, *, attempt: int = 1) -> DraftResult: ...


class MockComposer:
    """Deterministic prose assembled from the figures themselves.

    Not a language model and not pretending to be one. It writes a short, factual
    paragraph from the refs it was given, which is enough to exercise every part of the
    pipeline — verification, linting, tracked edits, sign-off — at zero cost and with
    identical output every run. The golden files depend on that last property.
    """

    def __init__(self, *, faulty: bool = False) -> None:
        self.faulty = faulty
        self.name = "mock-faulty" if faulty else "mock"

    def draft(self, request: DraftRequest, *, attempt: int = 1) -> DraftResult:
        refs = request.figure_refs
        if not refs:
            return DraftResult(
                text=f"No figures were bound to {request.title.lower()} for {request.period}.",
                model=self.name,
            )

        # Largest absolute figures first — a management paragraph leads with the big
        # numbers, and this also makes the output stable under row reordering.
        ranked = sorted(refs, key=lambda r: abs(r.value), reverse=True)[:4]
        display = request.display_by_ref

        lead = ranked[0]
        sentences = [
            f"For {request.period}, {lead.label.lower()} was "
            f"{display.get(lead.ref_id, lead.value)}."
        ]
        for ref in ranked[1:3]:
            sentences.append(
                f"{ref.label.capitalize()} stood at {display.get(ref.ref_id, ref.value)}."
            )
        if len(ranked) > 3:
            tail = ranked[3]
            sentences.append(
                f"{tail.label.capitalize()} was {display.get(tail.ref_id, tail.value)}."
            )

        if self.faulty:
            # A figure no ref supports: the lead value nudged, kept plausible so that
            # catching it is a real test of the checker rather than of an obvious outlier.
            wrong = (lead.value * Decimal("1.07")).quantize(Decimal("0.01"))
            sentences.append(f"Adjusted for the period, this was approximately £{wrong:,}.")

        return DraftResult(
            text=" ".join(sentences),
            model=self.name,
            cited_refs=[r.ref_id for r in ranked],
        )


class OpenAIComposer:
    """The live path. Constructed only when REPORTSMITH_LLM=live.

    Kept thin on purpose: the value of this project is in what surrounds the model —
    the bound-data-only input, the cross-check, the linter, the sign-off — not in the
    call itself.
    """

    name = "openai"

    def __init__(self, model: str | None = None, temperature: float | None = None) -> None:
        self.model = model or settings.model
        self.temperature = temperature if temperature is not None else settings.temperature
        self.name = f"openai:{self.model}"

    def draft(self, request: DraftRequest, *, attempt: int = 1) -> DraftResult:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        from app.narrate.prompts import build_messages

        system, human = build_messages(request, attempt=attempt)
        client = ChatOpenAI(model=self.model, temperature=self.temperature)
        response = client.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        text = response.content if isinstance(response.content, str) else str(response.content)
        return DraftResult(text=text.strip(), model=self.name)


def get_composer(*, faulty: bool = False) -> Composer:
    """Mock unless the environment explicitly asks for live."""
    if settings.live_llm and not faulty:
        return OpenAIComposer()
    return MockComposer(faulty=faulty)
