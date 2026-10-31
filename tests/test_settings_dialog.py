from __future__ import annotations

import pytest

from PySide6.QtWidgets import QDialog

from valencedraw.core.geometry import Point2D
from valencedraw.core.page import SCENE_UNITS_PER_MM
from valencedraw.document.document import Document
from valencedraw.render.style import DEFAULT_STYLE, Style
from valencedraw.ui.main_window import MainWindow
from valencedraw.ui.settings_dialog import SettingsDialog, StylePreview
from valencedraw.ui.tools import BondTool, RingTool
from qt_helpers import move as _move
from qt_helpers import press as _press


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


# -- Dialog --------------------------------------------------------------
def test_dialog_shows_current_style() -> None:
    style = Style(bond_length=50.0, bond_width=4.0)

    dialog = SettingsDialog(style)

    assert dialog.length_spin.value() == pytest.approx(5.0)
    assert dialog.width_spin.value() == pytest.approx(0.4)
    assert dialog.style == style


def test_dialog_returns_edited_style() -> None:
    dialog = SettingsDialog(DEFAULT_STYLE)

    dialog.length_spin.setValue(6.0)
    dialog.width_spin.setValue(0.5)

    edited = dialog.style
    assert edited.bond_length == pytest.approx(6.0 * SCENE_UNITS_PER_MM)
    assert edited.bond_width == pytest.approx(0.5 * SCENE_UNITS_PER_MM)
    # Alle übrigen Stilwerte bleiben erhalten.
    assert edited.label_pixel_size == DEFAULT_STYLE.label_pixel_size
    assert edited.text_pixel_size == DEFAULT_STYLE.text_pixel_size


def test_ask_returns_none_when_cancelled(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        SettingsDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected)
    )

    assert SettingsDialog.ask(None, DEFAULT_STYLE) is None


def test_ask_returns_style_when_accepted(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        SettingsDialog, "exec", lambda self: int(QDialog.DialogCode.Accepted)
    )

    style = SettingsDialog.ask(None, Style(bond_length=55.0))
    assert style is not None
    assert style.bond_length == pytest.approx(55.0)


# -- Vorschau ------------------------------------------------------------
def test_preview_follows_style() -> None:
    preview = StylePreview(DEFAULT_STYLE)
    preview.resize(240, 170)

    preview.set_style(Style(bond_length=70.0))

    molecule = preview.preview_molecule()
    lengths = [
        molecule.atom(bond.b).position.distance_to(molecule.atom(bond.a).position)
        for bond in molecule.bonds
    ]
    assert lengths
    assert all(length == pytest.approx(70.0) for length in lengths)
    assert not preview.grab().isNull()


# -- Verdrahtung ---------------------------------------------------------
def test_main_window_applies_style_to_canvas(qapp) -> None:  # noqa: ANN001
    window = MainWindow()
    try:
        style = Style(bond_length=60.0, bond_width=8.0)

        window._apply_style(style)

        assert window.style == style
        assert window.canvas.style == style
    finally:
        window.document.mark_saved()
        window.close()


def test_settings_menu_action_applies_style(monkeypatch, qapp) -> None:  # noqa: ANN001
    edited = Style(bond_length=70.0, bond_width=5.0)
    monkeypatch.setattr(
        SettingsDialog, "ask", staticmethod(lambda parent, style: edited)
    )
    window = MainWindow()
    try:
        window._settings_action.trigger()

        assert window.style == edited
        assert window.canvas.style == edited
    finally:
        window.document.mark_saved()
        window.close()


def test_bond_tool_uses_configured_bond_length() -> None:
    tool = BondTool(Document(), Style(bond_length=55.0))
    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_move(Point2D(300.0, 0.0), _move())

    target = tool.target_position()

    assert (target - Point2D(0.0, 0.0)).length == pytest.approx(55.0)


def test_ring_tool_follows_style_changes() -> None:
    tool = RingTool(Document(), Style(bond_length=50.0))
    vertices = tool.placement(Point2D(0.0, 0.0))
    first_edge = vertices[0].distance_to(vertices[1])
    assert first_edge == pytest.approx(50.0)

    tool.set_style(Style(bond_length=30.0))

    vertices = tool.placement(Point2D(0.0, 0.0))
    assert vertices[0].distance_to(vertices[1]) == pytest.approx(30.0)
