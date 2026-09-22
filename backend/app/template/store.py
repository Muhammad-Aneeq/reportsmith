"""The YAML template store, and the immutability rule that makes versions mean something.

A template version is a **promise about content**: if a pack says it was built from
``monthly_management_pack@v3``, then re-running v3 must produce the same structure, and
the archive's hash must still describe what a reader would see. That promise is only
worth anything if v3 cannot be edited after a pack cites it — otherwise "template
version" is decoration.

So: editing a referenced version raises. Editing produces a *new* version. That is the
one constraint this module exists to enforce; everything else here is loading YAML.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.template.schema import Template

DEFAULT_DIR = Path(__file__).parent / "default"


class TemplateError(ValueError):
    """A template that will not load. Carries a message aimed at the YAML author."""


class TemplateLocked(TemplateError):
    """Attempted edit of a version some pack already used."""


def _format_validation_error(exc: ValidationError, source: str) -> str:
    """Turn pydantic's report into something a YAML author can act on.

    The editor screen shows this verbatim, so it names the path and the problem and
    nothing else. A raw pydantic dump in a UI is how a schema-validated editor ends up
    feeling worse than no validation at all.
    """
    lines = [f"{source}: {len(exc.errors())} problem(s)"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p != "function-after")
        lines.append(f"  · {loc or '(root)'}: {err['msg']}")
    return "\n".join(lines)


def parse_template(text: str, *, source: str = "<string>") -> Template:
    """YAML text → a validated Template, or a TemplateError naming the problem."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TemplateError(f"{source}: not valid YAML — {exc}") from exc
    if not isinstance(raw, dict):
        raise TemplateError(f"{source}: expected a mapping at the top level")
    try:
        return Template.model_validate(raw)
    except ValidationError as exc:
        raise TemplateError(_format_validation_error(exc, source)) from exc


def load_template_file(path: Path) -> Template:
    return parse_template(path.read_text(encoding="utf-8"), source=path.name)


def dump_template(template: Template) -> str:
    """Template → YAML.

    ``sort_keys=False`` so a round-trip preserves the author's ordering: a template is
    read by humans in the order they wrote it, and alphabetising ``sections`` would
    reorder the actual report.
    """
    data = template.model_dump(mode="json", exclude_defaults=False)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def load_default_templates() -> list[Template]:
    """Every template shipped with the product (spec 13 F1: a default pack ships)."""
    return [load_template_file(p) for p in sorted(DEFAULT_DIR.glob("*.yaml"))]


def default_template() -> Template:
    """The Monthly Management Pack — what `make month1` runs with no arguments."""
    return load_template_file(DEFAULT_DIR / "monthly_management_pack.yaml")
