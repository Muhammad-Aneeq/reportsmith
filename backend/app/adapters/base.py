"""The adapter contract, and the reason a binding can never silently vanish.

Spec 13 F2: *"missing/failed binding → section renders as an explicit GAP (never
silently omitted), listed in a gaps panel."*

The mechanism is a **sum type with no third arm**. ``resolve_binding`` returns
``Bound`` or ``Gap`` — there is no ``None`` return, no raise path out, and no way for a
caller to receive nothing at all. Every adapter failure is caught here and converted,
including the ones nobody predicted: the bare ``except Exception`` is deliberate and is
the single most important line in this module.

A "silent omission" bug in a reporting tool is uniquely bad. A crash gets noticed. A
missing section in a board pack gets *signed*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.adapters.frame import Frame
from app.template.schema import Selector


class GapReason(StrEnum):
    """Why a binding did not produce data. Each renders as distinct copy in the panel."""

    ADAPTER_UNAVAILABLE = "adapter_unavailable"  # the source itself is not configured
    UNKNOWN_DATASET = "unknown_dataset"  # the source has no such dataset
    BINDING_FAILED = "binding_failed"  # it raised while fetching
    EMPTY_RESULT = "empty_result"  # it ran and there was nothing there
    SCHEMA_MISMATCH = "schema_mismatch"  # the data was not the shape we were promised
    SELECTOR_INVALID = "selector_invalid"  # the template asked for a field that is absent


@dataclass(frozen=True, slots=True)
class Gap:
    """A binding that did not resolve, with enough detail to act on."""

    reason: GapReason
    detail: str
    source: str
    dataset: str

    @property
    def is_gap(self) -> bool:
        return True

    def to_json(self) -> dict[str, str]:
        return {
            "reason": str(self.reason),
            "detail": self.detail,
            "source": self.source,
            "dataset": self.dataset,
        }


@dataclass(frozen=True, slots=True)
class Bound:
    """A binding that resolved."""

    frame: Frame

    @property
    def is_gap(self) -> bool:
        return False


BindingResult = Bound | Gap


@runtime_checkable
class SourceAdapter(Protocol):
    """What every data source must provide.

    ``SCHEMA_VERSION`` is a string that admits its own provenance — e.g.
    ``"spendsort/v1(export.py COLUMNS @2026-09-22)"``. It is carried into the pack and
    into the archive hash, so a pack records not just its numbers but what shape of
    upstream data produced them.
    """

    name: str
    SCHEMA_VERSION: str

    def catalog(self) -> tuple[str, ...]:
        """Dataset names this adapter publishes."""
        ...

    def fetch(self, dataset: str, period: str) -> Frame:
        """One dataset for one period. May raise; the caller converts to a Gap."""
        ...


def resolve_binding(
    adapters: dict[str, SourceAdapter],
    selector: Selector,
    period: str,
) -> BindingResult:
    """The only way a section gets its data. Returns Bound or Gap — never raises.

    Order matters: check the adapter exists, then the dataset, then fetch, then apply
    the selector, then check emptiness. Each step has its own reason code, so the gaps
    panel can say *which* thing went wrong rather than "binding failed".
    """
    from app.adapters.selector import SelectorError, apply_selector

    adapter = adapters.get(selector.source)
    if adapter is None:
        return Gap(
            reason=GapReason.ADAPTER_UNAVAILABLE,
            detail=(
                f"no adapter registered for source {selector.source!r}; "
                f"registered: {sorted(adapters) or 'none'}"
            ),
            source=selector.source,
            dataset=selector.select,
        )

    try:
        catalog = adapter.catalog()
    except Exception as exc:
        return Gap(
            reason=GapReason.ADAPTER_UNAVAILABLE,
            detail=f"{selector.source} could not list its datasets: {exc}",
            source=selector.source,
            dataset=selector.select,
        )

    if selector.select not in catalog:
        return Gap(
            reason=GapReason.UNKNOWN_DATASET,
            detail=(
                f"{selector.source} publishes no dataset {selector.select!r}; "
                f"available: {list(catalog)}"
            ),
            source=selector.source,
            dataset=selector.select,
        )

    frame: Any
    try:
        frame = adapter.fetch(selector.select, period)
    except SchemaMismatch as exc:
        return Gap(
            reason=GapReason.SCHEMA_MISMATCH,
            detail=str(exc),
            source=selector.source,
            dataset=selector.select,
        )
    except Exception as exc:
        return Gap(
            reason=GapReason.BINDING_FAILED,
            detail=f"{type(exc).__name__}: {exc}",
            source=selector.source,
            dataset=selector.select,
        )

    # `fetch` is *declared* to return a Frame, but an adapter is code this module does
    # not control and the whole contract here is that no adapter behaviour escapes as an
    # exception. `frame` is therefore held as Any at this boundary, which keeps the
    # runtime check honest instead of letting the annotation argue it away.
    if not isinstance(frame, Frame):
        # An adapter that returns None or a list is a programming error, but it must
        # still surface as a gap rather than an AttributeError three layers up.
        return Gap(
            reason=GapReason.SCHEMA_MISMATCH,
            detail=(
                f"{selector.source}.{selector.select} returned "
                f"{type(frame).__name__}, expected Frame"
            ),
            source=selector.source,
            dataset=selector.select,
        )

    try:
        frame = apply_selector(frame, selector)
    except SelectorError as exc:
        return Gap(
            reason=GapReason.SELECTOR_INVALID,
            detail=str(exc),
            source=selector.source,
            dataset=selector.select,
        )
    except Exception as exc:
        return Gap(
            reason=GapReason.BINDING_FAILED,
            detail=f"selector failed: {type(exc).__name__}: {exc}",
            source=selector.source,
            dataset=selector.select,
        )

    if frame.is_empty:
        return Gap(
            reason=GapReason.EMPTY_RESULT,
            detail=(
                f"{selector.source}.{selector.select} returned no rows for {period}"
                + (" after filtering" if selector.where else "")
            ),
            source=selector.source,
            dataset=selector.select,
        )

    return Bound(frame=frame)


class SchemaMismatch(ValueError):
    """The upstream data was not the shape its schema version promised.

    A distinct type so it gets its own gap reason. When a sibling changes its export,
    ReportSmith should say *"statementlens/v1 promised a 'value' column"* — not
    "binding failed".
    """
