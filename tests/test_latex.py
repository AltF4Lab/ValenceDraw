from __future__ import annotations

from valencedraw.core.annotations import TextObject
from valencedraw.core.geometry import Point2D
from valencedraw.core.latex import expand_math, has_math, latex_to_markup
from valencedraw.core.markup import (
    format_markup,
    markup_to_html,
    parse_markup,
    to_plain_text,
)


# -- Symbole --------------------------------------------------------------
def test_greek_letters_become_unicode() -> None:
    assert latex_to_markup(r"\alpha \beta \gamma") == "α β γ"
    assert latex_to_markup(r"\Delta H") == "ΔH"
    assert latex_to_markup(r"\Omega") == "Ω"


def test_common_symbols_become_unicode() -> None:
    assert latex_to_markup(r"a \cdot b") == "a · b"
    assert latex_to_markup(r"a \times b") == "a × b"
    assert latex_to_markup(r"\pm 5") == "± 5"
    assert latex_to_markup(r"\infty") == "∞"
    assert latex_to_markup(r"\rightarrow") == "→"
    assert latex_to_markup(r"A \rightleftharpoons B") == "A ⇌ B"


def test_hyphen_becomes_minus_sign() -> None:
    assert latex_to_markup("-1") == "−1"


# -- Hoch- und Tiefstellung ----------------------------------------------
def test_superscript_and_subscript() -> None:
    assert latex_to_markup("x^2") == "x^{2}"
    assert latex_to_markup("K_a") == "K_{a}"
    assert latex_to_markup("SO_4^{2-}") == "SO_{4}^{2−}"


def test_degree_sign_is_superscript_ring() -> None:
    assert latex_to_markup(r"\Delta G^\circ") == "ΔG^{∘}"


def test_nested_script_is_flattened() -> None:
    # Unser Markup kennt keine verschachtelten Skripte.
    assert latex_to_markup("x^{a^b}") == "x^{ab}"


# -- Brüche, Wurzeln ------------------------------------------------------
def test_fraction_is_set_inline() -> None:
    assert latex_to_markup(r"\frac{1}{2}") == "1/2"
    assert latex_to_markup(r"\frac{\Delta H}{T}") == "ΔH/T"


def test_fraction_parenthesizes_sums() -> None:
    assert latex_to_markup(r"\frac{a+b}{c}") == "(a+b)/c"
    assert latex_to_markup(r"\frac{[A^-][H^+]}{[HA]}") == "[A^{−}][H^{+}]/[HA]"


def test_sqrt() -> None:
    assert latex_to_markup(r"\sqrt{2}") == "√2"
    assert latex_to_markup(r"\sqrt{x^2+y^2}") == "√(x^{2}+y^{2})"
    assert latex_to_markup(r"\sqrt[3]{x}") == "∛x"


# -- Schriftstile und Text -----------------------------------------------
def test_text_commands_keep_spaces() -> None:
    assert latex_to_markup(r"\text{Beispiel Text}") == "Beispiel Text"
    assert latex_to_markup(r"\mathrm{sp^3}") == "sp^{3}"


def test_bold_and_italic_commands() -> None:
    assert latex_to_markup(r"\mathbf{fett}") == "**fett**"
    assert latex_to_markup(r"\mathit{kursiv}") == "*kursiv*"


def test_function_names_keep_their_space() -> None:
    assert latex_to_markup(r"-RT \ln K") == "−RT ln K"
    assert latex_to_markup(r"\ln\left(x\right)") == "ln(x)"


def test_left_right_delimiters() -> None:
    assert latex_to_markup(r"\left( a \right)") == "(a)"


def test_unknown_command_falls_back_to_its_name() -> None:
    assert latex_to_markup(r"\unbekannt") == "unbekannt"


def test_accent_commands_use_combining_marks() -> None:
    assert latex_to_markup(r"\bar{x}") == "x\u0304"
    assert latex_to_markup(r"\vec{v}") == "v\u20d7"


# -- $…$ im Text ----------------------------------------------------------
def test_expand_math_replaces_formulas() -> None:
    assert expand_math(r"Es gilt $\Delta G = -RT \ln K$.") == "Es gilt ΔG = −RT ln K."


def test_expand_math_handles_several_formulas() -> None:
    assert expand_math(r"$K_a$ und $K_b$") == "K_{a} und K_{b}"


def test_expand_math_supports_display_dollars() -> None:
    assert expand_math(r"$$\frac{1}{2}$$") == "1/2"


def test_escaped_dollar_stays_dollar() -> None:
    assert expand_math(r"Kosten \$ 5") == r"Kosten \$ 5"
    # ``\$`` bleibt auch nach dem Markup-Parser ein Dollarzeichen.
    assert to_plain_text(r"Kosten \$ 5") == "Kosten $ 5"


def test_unclosed_formula_stays_untouched() -> None:
    assert expand_math(r"offen $x_1") == r"offen $x_1"


def test_has_math() -> None:
    assert has_math("$x$") is True
    assert has_math("H_2O") is False


def test_text_without_math_is_unchanged() -> None:
    assert expand_math("NO2 + H2O") == "NO2 + H2O"


# -- Zusammenspiel mit dem Markup ---------------------------------------
def test_markup_to_html_renders_math() -> None:
    html = markup_to_html(r"$\frac{1}{2}$ H_2O")
    assert "1/2" in html
    assert "<sub>2</sub>" in html


def test_superscript_from_math_uses_sup_tag() -> None:
    html = markup_to_html(r"$\Delta G^\circ$")
    assert "Δ" in html
    assert "<sup>" in html


def test_plain_text_of_math() -> None:
    assert to_plain_text(r"$\sqrt{2}$ mol") == "√2 mol"


def test_text_object_runs_include_math() -> None:
    obj = TextObject(Point2D(0.0, 0.0), r"$x_1$")
    runs = parse_markup(obj.markup)

    assert "".join(run.text for run in runs) == "x1"


def test_text_object_keeps_the_latex_source() -> None:
    obj = TextObject(Point2D(0.0, 0.0), r"$\alpha$")

    assert obj.markup == r"$\alpha$"
    assert to_plain_text(obj.markup) == "α"


def test_auto_format_still_applies_around_math() -> None:
    # Chemiker-Schreibweise funktioniert weiterhin neben Formeln.
    assert format_markup(r"$x$ in H2O") == "x in H_{2}O"
