from __future__ import annotations

import pytest

from valencedraw.ui.text_dialog import TextDialog


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def test_dialog_round_trips_markup() -> None:
    dialog = TextDialog("H_2O")
    assert dialog.markup() == "H_2O"


def test_dialog_strips_whitespace() -> None:
    dialog = TextDialog("  CH_4  ")
    assert dialog.markup() == "CH_4"


def test_wrap_selection_puts_marker_around_selection() -> None:
    dialog = TextDialog()
    dialog.set_markup("H2O")
    dialog._edit.setSelection(1, 1)  # das "2" auswählen

    dialog.wrap_selection("_")

    assert dialog.markup() == "H_{2}O"


def test_wrap_selection_without_selection_inserts_empty_group() -> None:
    dialog = TextDialog()
    dialog.set_markup("H2O")
    dialog._edit.setCursorPosition(1)

    dialog.wrap_selection("^")

    assert dialog.markup() == "H^{}2O"


def test_dialog_accepts_custom_title() -> None:
    dialog = TextDialog("NO2", title="Atomlabel")
    assert dialog.windowTitle() == "Atomlabel"


def test_toggle_bold_wraps_and_unwraps_selection() -> None:
    dialog = TextDialog()
    dialog.set_markup("Ethanol")
    dialog._edit.setSelection(0, 3)  # "Eth" auswählen

    dialog.toggle_style("**")
    assert dialog.markup() == "**Eth**anol"

    dialog.toggle_style("**")
    assert dialog.markup() == "Ethanol"


def test_toggle_italic_wraps_selection() -> None:
    dialog = TextDialog()
    dialog.set_markup("Wasser")
    dialog._edit.setSelection(0, 6)

    dialog.toggle_style("*")

    assert dialog.markup() == "*Wasser*"


def test_preview_renders_bold_and_italic() -> None:
    dialog = TextDialog()
    dialog.set_markup("**fett** und *kursiv*")

    preview = dialog._preview.text()
    assert "<b>fett</b>" in preview
    assert "<i>kursiv</i>" in preview


def test_preview_applies_automatic_formatting() -> None:
    dialog = TextDialog()
    dialog.set_markup("NO2")
    assert "<sub>2</sub>" in dialog._preview.text()


def test_toggle_math_wraps_and_unwraps_selection() -> None:
    dialog = TextDialog()
    dialog.set_markup("Delta G")
    dialog._edit.setSelection(0, 7)

    dialog.toggle_math()
    assert dialog.markup() == "$Delta G$"

    dialog.toggle_math()
    assert dialog.markup() == "Delta G"


def test_toggle_math_without_selection_inserts_empty_formula() -> None:
    dialog = TextDialog()
    dialog.set_markup("K")
    dialog._edit.setCursorPosition(1)

    dialog.toggle_math()

    assert dialog.markup() == "K$$"


def test_preview_renders_latex() -> None:
    dialog = TextDialog()
    dialog.set_markup(r"$\frac{1}{2}\,\mathrm{mol}$")

    preview = dialog._preview.text()

    assert "1/2" in preview
    assert "mol" in preview
