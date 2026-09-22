"""numcheck's own suite. Runs with the application not installed — it imports only numcheck."""

from __future__ import annotations

from decimal import Decimal

import pytest

from numcheck import FigureRef, drop_failing_sentences, split_sentences, tokenize, verify
from numcheck.exempt import EXEMPTIONS
from numcheck.match import matches

REV = FigureRef(ref_id="rev", value=Decimal("3815070.61"), unit="money", label="Revenue")
MARGIN = FigureRef(ref_id="gm", value=Decimal("27.8975"), unit="percent", label="Gross margin")
LOSS = FigureRef(ref_id="op", value=Decimal("-57087.06"), unit="money", label="Operating profit")
COUNT = FigureRef(ref_id="n", value=Decimal("17"), unit="count", label="Exceptions")
DAYS = FigureRef(ref_id="d", value=Decimal("63.24"), unit="days", label="Receivable days")
REFS = [REV, MARGIN, LOSS, COUNT, DAYS]


# ------------------------------------------------------------- tokenisation --


@pytest.mark.parametrize(
    "text,count",
    [
        ("Revenue was £3,815,071.", 1),
        ("£3.8m", 1),
        ("(1,234)", 1),
        ("12.3%", 1),
        ("1.42x", 1),
        ("63.2 days", 1),
        ("no numbers at all", 0),
        ("£1,234 and £5,678 and 9.1%", 3),
        ("-£1,234", 1),
        ("£ 1,234", 1),
    ],
)
def test_tokenizer_counts(text, count):
    assert len(tokenize(text)) == count


@pytest.mark.parametrize(
    "text,value",
    [
        ("£3.8m", Decimal("3800000")),
        ("£1.5k", Decimal("1500")),
        ("(1,234)", Decimal("-1234")),
        ("-1,234", Decimal("-1234")),
        ("12.34%", Decimal("12.34")),
        ("£1,234.56", Decimal("1234.56")),
    ],
)
def test_tokenizer_values(text, value):
    assert tokenize(text)[0].value == value


@pytest.mark.parametrize("text,precision", [("3.8", 1), ("3", 0), ("3.815", 3), ("1,234.56", 2)])
def test_precision_is_what_the_author_wrote(text, precision):
    assert tokenize(text)[0].precision == precision


def test_spans_are_exact():
    """Surgery depends on these. An off-by-one here silently breaks sentence dropping."""
    text = "Revenue was £3.8m today."
    token = tokenize(text)[0]
    assert text[token.start : token.end] == "£3.8m"


# ------------------------------------------------------------------ matching --


@pytest.mark.parametrize(
    "written,ok",
    [
        ("£3.8m", True),  # 1 dp at millions scale
        ("£3,815,071", True),  # 0 dp
        ("£3,815,070.61", True),  # exact
        ("£3.82m", True),  # 2 dp at millions scale
        ("£3.9m", False),  # wrong at the precision written
        ("£3,815,072", False),
        # "£4m" is ACCEPTED, and that is correct: £3,815,071 rounded to the nearest
        # million is £4m, so the sentence is true at the precision it was written to.
        # How precisely a pack is *allowed* to state things is a style rule, enforced by
        # the tone linter — not a truth question, which is all this module decides.
        ("£4m", True),
        ("£5m", False),
    ],
)
def test_rounding_is_accepted_at_the_precision_written(written, ok):
    assert verify(f"Revenue was {written}.", REFS).ok is ok


def test_units_must_agree():
    """1.42 must not satisfy 1.42% — the conflation most worth preventing."""
    assert verify("The margin was 27.9%.", [MARGIN]).ok
    assert not verify("Revenue was £27.9.", [MARGIN]).ok
    assert not verify("The ratio was 3,815,070.61%.", [REV]).ok


def test_bare_numbers_may_satisfy_any_unit():
    assert verify("It stood at 27.9.", [MARGIN]).ok


def test_negatives_in_parentheses():
    assert verify("An operating loss of (57,087) was recorded.", REFS).ok
    assert verify("An operating loss of -£57,087 was recorded.", REFS).ok


def test_counts_and_days():
    assert verify("There were 17 exceptions.", REFS).ok
    assert verify("Receivable days stood at 63.2 days.", REFS).ok
    assert not verify("There were 18 exceptions.", REFS).ok


def test_no_tolerance_knob_exists():
    """If someone adds one, this test should be the thing that stops them.

    Scans executable lines only — the module docstring *says* "no tolerance parameter",
    and a naive substring search over the whole file flags its own explanation.
    """
    import ast
    import inspect

    import numcheck.match as match_module

    source = inspect.getsource(match_module)
    tree = ast.parse(source)
    # Strip every docstring, then unparse back to code-only text.
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef) and ast.get_docstring(
            node
        ):
            node.body = node.body[1:]
    code = ast.unparse(tree).lower()

    for smell in ("tolerance", "epsilon", "atol", "rtol"):
        assert smell not in code, f"{smell!r} appeared in the matcher's executable code"
    assert "float(" not in code, "float() in the matcher reintroduces the dust Decimal removes"


def test_matches_is_symmetric_in_precision():
    token = tokenize("£3.8m")[0]
    assert matches(token, REV)


# ---------------------------------------------------------------- exemptions --


def test_exemption_list_is_closed_at_two():
    """Exemption creep is how this class of checker dies. Growing it is a visible change."""
    assert EXEMPTIONS == ("declared period label", "ordinal list marker")
    assert len(EXEMPTIONS) == 2


def test_declared_period_labels_pass():
    assert verify("Revenue in 2024-07 was £3.8m.", REFS, periods=["2024-07"]).ok
    assert verify("In Jul 2024 revenue was £3.8m.", REFS, periods=["Jul 2024"]).ok


def test_an_undeclared_year_is_a_failure():
    """The whole point: a model cannot smuggle a number through by making it look like a date."""
    assert not verify("Revenue rose through 2019.", REFS, periods=["2024-07"]).ok


def test_list_markers_are_structure():
    text = "Findings:\n1. Revenue was £3.8m.\n2. Margin was 27.9%."
    assert verify(text, REFS).ok


# ------------------------------------------------------------------- surgery --


def test_sentence_splitting_survives_decimals_and_abbreviations():
    text = "Revenue was £1.4m. Northgate Systems Ltd. was the largest supplier. Margin held."
    assert len(split_sentences(text)) == 3


def test_only_the_offending_sentence_is_dropped():
    text = "Revenue was £3.8m. Margin collapsed to 99.9%. Gross margin was 27.9%."
    kept, dropped = drop_failing_sentences(text, REFS)
    assert dropped == ["Margin collapsed to 99.9%."]
    assert "Revenue was £3.8m." in kept
    assert "Gross margin was 27.9%." in kept


def test_surgery_never_invents_text():
    text = "Revenue was £9.9m."
    kept, dropped = drop_failing_sentences(text, REFS)
    assert kept == ""
    assert dropped == [text]


# -------------------------------------------------------------------- harness --


def test_harness_requires_figures_to_have_been_checked():
    """A composer that writes nothing must not score a pass."""
    from numcheck import score

    empty = score([("s", "No figures were available.", REFS, [])])
    assert empty.fidelity == Decimal(100)
    assert not empty.passed(), "prose with no numbers must not count as verified"

    real = score([("s", "Revenue was £3.8m.", REFS, [])])
    assert real.passed()
    assert real.figures_checked == 1


def test_harness_reports_the_failing_token():
    from numcheck import score

    report = score([("commentary", "Revenue was £9.9m.", REFS, [])])
    assert not report.passed()
    assert report.failures[0]["section"] == "commentary"
    assert "9.9" in report.failures[0]["token"]


# ----------------------------------------------------------- standalone-ness --


def test_numcheck_imports_nothing_from_the_application():
    """It must lift into StatementLens as a directory move. See ORIGIN.md."""
    from pathlib import Path

    package = Path(__file__).resolve().parents[1]
    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "from app" not in source, f"{module.name} imports from the application"
        assert "import app" not in source, f"{module.name} imports from the application"
        assert "ledgerfab" not in source, f"{module.name} reaches into the data engine"


def test_numcheck_does_not_shadow_a_stdlib_module():
    """The bug that cost an afternoon: numcheck/tokenize.py breaks `import inspect`."""
    import sys
    from pathlib import Path

    package = Path(__file__).resolve().parents[1]
    stdlib = set(sys.stdlib_module_names)
    for module in package.glob("*.py"):
        assert module.stem not in stdlib, (
            f"numcheck/{module.name} shadows the stdlib module {module.stem!r}; "
            f"rename it (see ORIGIN.md)"
        )
