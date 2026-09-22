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
    # Reported by the provider, not estimated. MODEL_COSTS.md quotes these, and a cost page
    # built on guesses is the kind of thing that is wrong by an order of magnitude and never
    # corrected because nobody measured.
    prompt_tokens: int = 0
    completion_tokens: int = 0


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

        display = request.display_by_ref
        by_id = {ref.ref_id: ref for ref in refs}

        # Only this period's figures lead. The frame carries prior-month and movement refs
        # alongside each current one, and ranking the whole set by magnitude put "revenue
        # (prior month)" first — a management paragraph that opens on last month's number,
        # then restates it two sentences later. Comparatives are *support*, so they are
        # attached to their own figure rather than competing with it.
        current = [r for r in refs if "(" not in r.label] or refs
        ranked = sorted(current, key=lambda r: abs(r.value), reverse=True)[:3]

        def movement_of(ref: FigureRef) -> str:
            """', up 2.9% on the prior month' — if that movement was actually supplied."""
            delta = by_id.get(f"{ref.ref_id.rsplit('.', 1)[0]}.delta_pct")
            if delta is None or delta.value == 0:
                return ""
            direction = "up" if delta.value > 0 else "down"
            shown = display.get(delta.ref_id, str(delta.value)).lstrip("+-−")
            return f", {direction} {shown} on the prior month"

        sentences: list[str] = []
        lead = ranked[0]
        sentences.append(
            # "totalled" rather than "was": the label may be singular or plural
            # ("revenue", "utilities") and this mock cannot do subject-verb agreement.
            f"For {request.period}, {lead.label.lower()} totalled "
            f"{display.get(lead.ref_id, lead.value)}{movement_of(lead)}."
        )
        for ref in ranked[1:]:
            sentences.append(
                f"{ref.label.capitalize()} stood at "
                f"{display.get(ref.ref_id, ref.value)}{movement_of(ref)}."
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

        usage = getattr(response, "usage_metadata", None) or {}
        return DraftResult(
            text=text.strip(),
            model=self.name,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
        )


def get_composer(*, faulty: bool = False) -> Composer:
    """Mock unless the environment explicitly asks for live."""
    if settings.live_llm and not faulty:
        return OpenAIComposer()
    return MockComposer(faulty=faulty)
