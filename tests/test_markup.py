from __future__ import annotations

import pytest

from valencedraw.core.markup import (
    Script,
    TextRun,
    auto_format,
    markup_to_html,
    parse_markup,
    to_plain_text,
)


def test_plain_text_has_single_run() -> None:
    assert parse_markup("Ethanol") == (TextRun("Ethanol"),)


def test_single_character_subscript() -> None:
    assert parse_markup("H_2O") == (
        TextRun("H"),
        TextRun("2", Script.SUB),
        TextRun("O"),
    )


def test_grouped_subscript_and_superscript() -> None:
    assert parse_markup("SO_4^{2-}") == (
        TextRun("SO"),
        TextRun("4", Script.SUB),
        TextRun("2-", Script.SUPER),
    )


def test_multiple_scripts_in_a_row() -> None:
    runs = parse_markup("Fe^{3+}_{aq}")
    assert [run.script for run in runs] == [Script.NORMAL, Script.SUPER, Script.SUB]
    assert runs[1].text == "3+"
    assert runs[2].text == "aq"


def test_escaped_markers_are_literal() -> None:
    assert parse_markup("A\\_B") == (TextRun("A_B"),)
    assert parse_markup("x\\^y") == (TextRun("x^y"),)


def test_dangling_marker_is_literal() -> None:
    assert parse_markup("C_") == (TextRun("C_"),)
    assert parse_markup("^") == (TextRun("^"),)


def test_empty_group_is_allowed() -> None:
    runs = parse_markup("H_{}O")
    assert runs[1] == TextRun("", Script.SUB)


def test_html_contains_sup_and_sub() -> None:
    html = markup_to_html("H_2O")
    assert "<sub>2</sub>" in html
    assert markup_to_html("Fe^{3+}").endswith("</sup>")


def test_html_escapes_special_characters() -> None:
    html = markup_to_html("a<b>&c")
    assert "&lt;" in html
    assert "&amp;" in html
    assert "<b>" not in html


def test_newline_becomes_line_break() -> None:
    assert "<br/>" in markup_to_html("Zeile 1\nZeile 2")


def test_plain_text_strips_scripts() -> None:
    assert to_plain_text("SO_4^{2-}") == "SO42-"


@pytest.mark.parametrize("markup", ["", " ", "H_2O", "^{x}"])
def test_parse_never_fails(markup: str) -> None:
    runs = parse_markup(markup)
    assert isinstance(runs, tuple)


# -- Automatische Chemiker-Schreibweise ---------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("NO2", "NO_{2}"),
        ("(CH3)2CO", "(CH_{3})_{2}CO"),
        ("NO3-", "NO_{3}^{-}"),
        ("NH4+", "NH_{4}^{+}"),
        ("Ca2+", "Ca^{2+}"),
        ("Fe3+", "Fe^{3+}"),
        ("Cl-", "Cl^{-}"),
        ("H+", "H^{+}"),
        ("C60-", "C_{60}^{-}"),
        ("SO4 2-", "SO_{4} ^{2-}"),
    ],
)
def test_auto_format_chemist_notation(text: str, expected: str) -> None:
    assert auto_format(text) == expected


@pytest.mark.parametrize("text", ["", "  ", "H_2O", "Fe^{3+}", "A\\_B"])
def test_auto_format_leaves_explicit_markup_alone(text: str) -> None:
    assert auto_format(text) == text


def test_auto_format_keeps_trailing_whitespace() -> None:
    assert auto_format("H2O ") == "H_{2}O "


def test_html_and_plain_text_use_auto_format() -> None:
    assert markup_to_html("NO2") == "NO<sub>2</sub>"
    assert to_plain_text("NO3-") == "NO3-"


# -- Fett und Kursiv -----------------------------------------------------
def test_bold_and_italic_markers() -> None:
    assert parse_markup("**fett**") == (TextRun("fett", bold=True),)
    assert parse_markup("*kursiv*") == (TextRun("kursiv", italic=True),)


def test_bold_survives_sub_and_superscript() -> None:
    runs = parse_markup("**SO_4^{2-}**")

    assert [(run.text, run.script, run.bold) for run in runs] == [
        ("SO", Script.NORMAL, True),
        ("4", Script.SUB, True),
        ("2-", Script.SUPER, True),
    ]


def test_bold_and_italic_are_combinable() -> None:
    runs = parse_markup("**a *b* c**")

    assert [(run.text, run.bold, run.italic) for run in runs] == [
        ("a ", True, False),
        ("b", True, True),
        (" c", True, False),
    ]


def test_escaped_star_is_literal() -> None:
    assert parse_markup("A\\*B") == (TextRun("A*B"),)


def test_html_contains_bold_and_italic() -> None:
    assert markup_to_html("**fett**") == "<b>fett</b>"
    assert markup_to_html("*kursiv*") == "<i>kursiv</i>"


def test_auto_format_also_works_inside_bold() -> None:
    html = markup_to_html("**NO2**")
    assert "<sub>2</sub>" in html
    assert html.startswith("<b>") and html.endswith("</b>")
    assert "NO" in html
    assert "<b>" in markup_to_html("**Ca2+**")
    assert "<sup>2+</sup>" in markup_to_html("**Ca2+**")


def test_plain_text_strips_bold_and_italic() -> None:
    assert to_plain_text("**fett** und *kursiv*") == "fett und kursiv"


def test_auto_formatted_text_round_trips_through_runs() -> None:
    runs = parse_markup(auto_format("NO3-"))
    assert [run.text for run in runs] == ["NO", "3", "-"]
    assert [run.script for run in runs] == [Script.NORMAL, Script.SUB, Script.SUPER]
