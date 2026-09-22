"""The narrative pipeline (LangGraph).

    draft → numcheck → [retry once] → lint → numcheck re-verify → finalize

The ordering is the one decision worth defending (PLAN.md **D-015**). Spec 13 §8 says the
deterministic linter runs *before* the LLM style judge — which it does; the judge is an
evals-only stage. It does **not** mean the linter runs before the cross-check: the linter
rewrites how figures are rendered, so if it ran last, a fix could invalidate the guarantee
the cross-check had just established. Hence verify, lint, verify again.

The retry is a **re-draft**, not a repair. Spec 12 F5: *"mismatches fail the draft, one
retry, else that sentence is dropped."* Asking a model to patch its own bad number tends to
produce the same number with a hedge in front of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.narrate.composer import Composer, DraftRequest, get_composer
from app.narrate.lint import Violation, lint
from app.template.schema import NarrativeSection, Template
from numcheck import CheckResult, FigureRef, drop_failing_sentences, verify

MAX_ATTEMPTS = 2  # the draft, plus the one retry spec 12 F5 allows


class NarrativeState(TypedDict, total=False):
    request: DraftRequest
    composer: Composer
    attempt: int
    text: str
    model: str
    check: CheckResult
    violations: list[Violation]
    dropped: list[str]
    retried: bool


@dataclass
class NarrativeResult:
    """What the composer hands back for one section."""

    text: str
    ai_draft: str
    model: str
    prompt_version: str
    figure_refs: list[dict[str, Any]]
    verified: bool
    figures_checked: int
    violations: list[dict[str, Any]] = field(default_factory=list)
    dropped_sentences: list[str] = field(default_factory=list)
    retried: bool = False

    def to_content(self, base: dict[str, Any]) -> dict[str, Any]:
        return {
            **base,
            "text": self.text,
            "drafted": True,
            "verified": self.verified,
            "figures_checked": self.figures_checked,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "violations": self.violations,
            "dropped_sentences": self.dropped_sentences,
            "retried": self.retried,
        }


def _node_draft(state: NarrativeState) -> NarrativeState:
    attempt = state.get("attempt", 0) + 1
    result = state["composer"].draft(state["request"], attempt=attempt)
    return {**state, "attempt": attempt, "text": result.text, "model": result.model}


def _node_check(state: NarrativeState) -> NarrativeState:
    request = state["request"]
    return {
        **state,
        "check": verify(state["text"], request.figure_refs, periods=[request.period]),
    }


def _route_after_check(state: NarrativeState) -> str:
    if state["check"].ok:
        return "lint"
    if state["attempt"] < MAX_ATTEMPTS:
        return "draft"
    return "surgery"


def _node_surgery(state: NarrativeState) -> NarrativeState:
    """Second failure: remove the offending sentences, keep the rest."""
    request = state["request"]
    kept, dropped = drop_failing_sentences(
        state["text"], request.figure_refs, periods=[request.period]
    )
    return {**state, "text": kept, "dropped": dropped, "retried": True}


def _node_lint(state: NarrativeState) -> NarrativeState:
    request = state["request"]
    fixed, violations = lint(state["text"], request.style, request.tone_rules)
    return {**state, "text": fixed, "violations": violations}


def _node_reverify(state: NarrativeState) -> NarrativeState:
    """Verify again after the linter's fixes. See the module docstring."""
    request = state["request"]
    return {
        **state,
        "check": verify(state["text"], request.figure_refs, periods=[request.period]),
    }


def build_graph() -> Any:
    graph = StateGraph(NarrativeState)
    graph.add_node("draft", _node_draft)
    graph.add_node("check", _node_check)
    graph.add_node("surgery", _node_surgery)
    graph.add_node("lint", _node_lint)
    graph.add_node("reverify", _node_reverify)

    graph.add_edge(START, "draft")
    graph.add_edge("draft", "check")
    graph.add_conditional_edges(
        "check", _route_after_check, {"draft": "draft", "surgery": "surgery", "lint": "lint"}
    )
    graph.add_edge("surgery", "lint")
    graph.add_edge("lint", "reverify")
    graph.add_edge("reverify", END)
    return graph.compile()


_GRAPH = None


def compose_section(
    section: NarrativeSection,
    template: Template,
    period: str,
    content: dict[str, Any],
    composer: Composer | None = None,
) -> NarrativeResult:
    """Draft one narrative section from its bound figures and tone rules. Nothing else.

    The signature is the isolation guarantee: there is no parameter here through which the
    world, the other sections, or the raw ledger could arrive.
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()

    raw_refs = content.get("figure_refs", [])
    refs = [
        FigureRef(
            ref_id=r["ref_id"],
            value=Decimal(str(r["value"])),
            unit=r.get("unit", "bare"),
            label=r.get("label", ""),
        )
        for r in raw_refs
    ]
    display_by_ref = {r["ref_id"]: r.get("display", "") for r in raw_refs}

    from app.narrate.prompts import prompt_version

    version = prompt_version(template.id, template.version, section.id)
    request = DraftRequest(
        section_key=section.id,
        title=section.title,
        period=period,
        figure_refs=refs,
        display_by_ref=display_by_ref,
        tone_rules=list(section.tone_rules),
        style=template.style,
        max_words=section.max_words,
        prompt_version=version,
    )

    chosen = composer or get_composer()
    first = chosen.draft(request, attempt=1)  # kept as the AI draft of record

    final: NarrativeState = _GRAPH.invoke({"request": request, "composer": chosen, "attempt": 0})

    check: CheckResult = final["check"]
    return NarrativeResult(
        text=final["text"],
        # Spec 13 F5's "AI draft preserved alongside human edits" starts here: the draft
        # of record is the model's FIRST output, before verification trimmed it and before
        # the linter reformatted it. Storing the post-processed text would quietly erase
        # the evidence that any processing happened.
        ai_draft=first.text,
        model=final.get("model", chosen.name),
        prompt_version=version,
        figure_refs=raw_refs,
        verified=check.ok,
        figures_checked=check.checked,
        violations=[v.to_json() for v in final.get("violations", [])],
        dropped_sentences=final.get("dropped", []),
        retried=final.get("retried", False) or final.get("attempt", 1) > 1,
    )
