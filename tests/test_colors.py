"""Tests für die Farbpalette und nachträglich gefärbte Objekte."""

from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind, ArrowObject, TextObject
from valencedraw.core.colors import PALETTE, color_to_hex, normalize_color
from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import Molecule
from valencedraw.demo import ethane
from valencedraw.document.document import Document
from valencedraw.document.project import Project, project_from_json, project_to_json
from valencedraw.render.export import render_image
from valencedraw.render.painter import _label_color
from valencedraw.render.style import DEFAULT_STYLE
from valencedraw.ui.color_palette import ColorPalette
from valencedraw.ui.main_window import MainWindow

RED = (210, 40, 40)
GREEN = (0, 150, 60)
BLUE = (40, 90, 200)


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    """Qt braucht für Schrift-/Render-Tests eine laufende Anwendung."""
    yield


def test_normalize_color_accepts_rgb_and_none() -> None:
    assert normalize_color(None) is None
    assert normalize_color([1, 2, 3]) == (1, 2, 3)
    assert normalize_color((255, 0, 128)) == (255, 0, 128)
    assert color_to_hex((255, 0, 128)) == "#ff0080"


@pytest.mark.parametrize("color", [(-1, 0, 0), (0, 0, 256), (1, 2), "rot"])
def test_normalize_color_rejects_invalid_values(color) -> None:  # noqa: ANN001
    with pytest.raises(ValueError):
        normalize_color(color)


def test_molecule_sets_and_resets_colors() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(left, right)

    molecule.set_atom_color(right, RED)
    molecule.set_bond_color(bond, BLUE)

    assert molecule.atom(right).color == RED
    assert molecule.bonds[0].color == BLUE
    assert molecule.atom(left).color is None

    molecule.set_atom_color(right, None)
    molecule.set_bond_color(bond, None)

    assert molecule.atom(right).color is None
    assert molecule.bonds[0].color is None


def test_colors_are_copied_when_cloning() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), color=GREEN)
    other = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(atom_id, other, color=BLUE)

    copy = molecule.clone()

    assert copy.atom(atom_id).color == GREEN
    assert copy.bonds[0].color == BLUE


def _colored_document() -> tuple[Document, int, int, int]:
    document = Document()
    molecule = document.molecule
    first = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    last = molecule.add_atom("O", Point2D(2 * BOND_LENGTH, 0.0))
    molecule.add_bond(first, middle)
    molecule.add_bond(middle, last)
    document.add_text(Point2D(0.0, 80.0), "A")
    document.add_arrow(Point2D(0.0, 120.0), Point2D(100.0, 120.0))
    return document, first, middle, last


def test_set_selection_color_colors_atoms_internal_bonds_texts_and_arrows() -> None:
    document, first, middle, _last = _colored_document()
    document.select_objects([first, middle], [0], [0])

    count = document.set_selection_color(RED)

    assert count == 5  # 2 Atome + 1 innere Bindung + Text + Pfeil
    assert document.molecule.atom(first).color == RED
    assert document.molecule.atom(middle).color == RED
    assert [bond.color for bond in document.molecule.bonds] == [RED, None]
    assert document.texts[0].color == RED
    assert document.arrows[0].color == RED


def test_set_selection_color_is_one_undo_step_and_resettable() -> None:
    document, first, middle, _last = _colored_document()
    document.select_objects([first, middle], [0], [0])
    document.set_selection_color(RED)

    document.undo_stack.undo()

    assert document.molecule.atom(first).color is None
    assert document.molecule.atom(middle).color is None
    assert all(bond.color is None for bond in document.molecule.bonds)
    assert document.texts[0].color is None
    assert document.arrows[0].color is None

    document.undo_stack.redo()
    document.set_selection_color(None)

    assert document.molecule.atom(first).color is None
    assert document.arrows[0].color is None


def test_set_selection_color_without_selection_changes_nothing() -> None:
    document, first, _middle, _last = _colored_document()
    undo_before = document.undo_stack.count()

    assert document.set_selection_color(RED) == 0
    assert document.molecule.atom(first).color is None
    assert document.undo_stack.count() == undo_before


def test_project_roundtrip_keeps_every_color() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0), color=RED)
    right = molecule.add_atom("N", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(left, right, color=BLUE)
    project = Project(
        molecule=molecule,
        texts=(TextObject(Point2D(0.0, 80.0), "H_2O", color=GREEN),),
        arrows=(
            ArrowObject(
                Point2D(0.0, 120.0),
                Point2D(100.0, 120.0),
                ArrowKind.FORWARD,
                color=RED,
            ),
        ),
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded == project
    assert loaded.molecule.atom(left).color == RED
    assert loaded.molecule.bonds[0].color == BLUE
    assert loaded.texts[0].color == GREEN
    assert loaded.arrows[0].color == RED


def test_clipboard_keeps_colors() -> None:
    source = Document()
    left = source.molecule.add_atom("C", Point2D(0.0, 0.0), color=RED)
    right = source.molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    source.molecule.add_bond(left, right, color=BLUE)
    source.select_all()

    fragment = source.copy_selection()
    target = Document()
    target.paste_fragment(fragment)

    assert [atom.color for atom in target.molecule.atoms.values()] == [RED, None]
    assert target.molecule.bonds[0].color == BLUE


def test_arrow_color_survives_moving_and_bending() -> None:
    arrow = ArrowObject(
        Point2D(0.0, 0.0),
        Point2D(100.0, 0.0),
        ArrowKind.PAIR_FLOW,
        0.3,
        color=RED,
    )

    assert arrow.translated(Point2D(10.0, 5.0)).color == RED

    resized = ArrowObject(
        arrow.start,
        arrow.end,
        arrow.kind,
        0.4,
        arrow.bow_along,
        color=arrow.color,
    )
    assert resized.color == RED


def test_default_labels_stay_black() -> None:
    molecule = Molecule()
    oxygen = molecule.add_atom("O", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(BOND_LENGTH, 0.0))

    assert _label_color(molecule, oxygen, DEFAULT_STYLE) == DEFAULT_STYLE.bond_color
    assert _label_color(molecule, nitrogen, DEFAULT_STYLE) == DEFAULT_STYLE.bond_color


def test_render_uses_custom_bond_color() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(left, right)
    molecule.set_bond_color(bond, RED)

    image = render_image(molecule, width=300, height=120)

    red_pixels = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).red() > 150
        and image.pixelColor(x, y).green() < 120
        and image.pixelColor(x, y).blue() < 120
    )
    assert red_pixels > 10


def test_render_uses_custom_atom_color() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), color=GREEN)

    image = render_image(molecule, width=200, height=200)

    green_pixels = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).green() > 100
        and image.pixelColor(x, y).red() < 100
        and image.pixelColor(x, y).blue() < 100
    )
    assert green_pixels > 5


def test_palette_emits_colors_and_reset() -> None:
    palette = ColorPalette()
    received: list[object] = []
    palette.color_selected.connect(received.append)

    assert {name for name, _color in PALETTE} <= set(palette.buttons)
    palette.buttons["Rot"].click()
    palette.buttons["Standard"].click()

    assert received == [RED, None]


def test_main_window_applies_color_to_selection() -> None:
    window = MainWindow(Document(ethane()))
    atom_id = window.document.molecule.atom_ids()[0]
    try:
        window.document.select_only(atom_id)
        window._apply_color_to_selection(RED)
        assert window.document.molecule.atom(atom_id).color == RED

        window.document.clear_selection()
        window._apply_color_to_selection(BLUE)
        assert window.document.molecule.atom(atom_id).color == RED
        assert "auswählen" in window.statusBar().currentMessage()
    finally:
        window.document.mark_saved()
        window.close()
