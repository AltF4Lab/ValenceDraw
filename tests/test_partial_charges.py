from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from valencedraw.core.geometry import Point2D
from valencedraw.core.molecule import (
    MAX_PARTIAL_CHARGE,
    Molecule,
    next_partial_charge,
    partial_charge_text,
)
from valencedraw.document.document import Document
from valencedraw.document.project import Project, project_from_data, project_to_data
from valencedraw.render.painter import (
    atom_label,
    charge_rect,
    label_rect,
    paint_molecule,
    partial_charge_rect,
)
from valencedraw.ui.tools import PartialChargeTool
from qt_helpers import move as _move
from qt_helpers import press as _press
from qt_helpers import release as _release


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _atom_document(element: str = "N") -> tuple[Document, int]:
    document = Document()
    atom_id = document.molecule.add_atom(element, Point2D(0.0, 0.0))
    return document, atom_id


# -- Modell --------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, ""), (1, "δ⁺"), (-1, "δ⁻"), (5, "δ⁺"), (-3, "δ⁻")],
)
def test_partial_charge_text(value: int, expected: str) -> None:
    assert partial_charge_text(value) == expected


def test_next_partial_charge_toggles_the_same_sign_off() -> None:
    assert next_partial_charge(0, 1) == 1
    assert next_partial_charge(1, 1) == 0
    assert next_partial_charge(0, -1) == -1
    assert next_partial_charge(-1, -1) == 0
    # Klick mit dem anderen Vorzeichen wechselt direkt
    assert next_partial_charge(-1, 1) == 1
    assert next_partial_charge(1, -1) == -1


def test_next_partial_charge_rejects_sign_zero() -> None:
    with pytest.raises(ValueError):
        next_partial_charge(0, 0)


def test_partial_charge_is_clamped() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom()

    molecule.set_partial_charge(atom_id, 5)
    assert molecule.atom(atom_id).partial_charge == MAX_PARTIAL_CHARGE

    molecule.set_partial_charge(atom_id, -4)
    assert molecule.atom(atom_id).partial_charge == -MAX_PARTIAL_CHARGE


def test_reset_atom_clears_the_partial_charge() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O")
    molecule.set_partial_charge(atom_id, -1)
    molecule.set_partial_charge_direction(atom_id, Point2D(1.0, 0.0))

    molecule.reset_atom(atom_id)

    atom = molecule.atom(atom_id)
    assert atom.partial_charge == 0
    assert atom.partial_charge_direction is None


# -- Darstellung ---------------------------------------------------------
def test_partial_charge_makes_a_plain_carbon_visible() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C")

    assert atom_label(molecule, atom_id) == ""
    molecule.set_partial_charge(atom_id, 1)
    assert atom_label(molecule, atom_id) == "C"
    assert partial_charge_rect(molecule, atom_id) is not None


def test_no_rect_without_partial_charge() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N")

    assert partial_charge_rect(molecule, atom_id) is None


def test_charge_and_partial_charge_use_opposite_corners() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N")
    molecule.set_charge(atom_id, 1)
    molecule.set_partial_charge(atom_id, 1)

    formal = charge_rect(molecule, atom_id)
    partial = partial_charge_rect(molecule, atom_id)

    assert formal is not None and partial is not None
    assert not formal.intersects(partial)
    # Formalladung oben rechts → Teilladung unten links
    assert partial.center().x() < formal.center().x()
    assert partial.center().y() > formal.center().y()


def test_label_rect_covers_the_partial_charge() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N")
    molecule.set_partial_charge(atom_id, -1)

    partial = partial_charge_rect(molecule, atom_id)
    assert partial is not None
    assert label_rect(molecule, atom_id).contains(partial)


def _ink(image: QImage) -> int:
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y) != QColor("white")
    )


def test_partial_charge_is_drawn() -> None:
    counts: list[int] = []
    for partial in (0, 1):
        molecule = Molecule()
        atom_id = molecule.add_atom("N")
        molecule.set_partial_charge(atom_id, partial)
        image = QImage(240, 160, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.translate(40.0, 80.0)
        paint_molecule(painter, molecule)
        painter.end()
        counts.append(_ink(image))

    assert counts[1] > counts[0]


# -- Dokument ------------------------------------------------------------
def test_document_sets_partial_charge_in_one_undo_step() -> None:
    document, atom_id = _atom_document()

    document.set_atom_partial_charge(atom_id, 1)
    assert document.molecule.atom(atom_id).partial_charge == 1
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.molecule.atom(atom_id).partial_charge == 0


def test_cycle_atom_partial_charge_toggles() -> None:
    document, atom_id = _atom_document()

    assert document.cycle_atom_partial_charge(atom_id, 1) == 1
    assert document.cycle_atom_partial_charge(atom_id, 1) == 0
    assert document.cycle_atom_partial_charge(atom_id, -1) == -1


def test_copy_and_paste_keeps_partial_charges() -> None:
    document, atom_id = _atom_document()
    document.set_atom_partial_charge(atom_id, -1, Point2D(1.0, 0.0))
    document.select_only(atom_id)

    fragment = document.copy_selection()
    assert document.paste_fragment(fragment, Point2D(100.0, 0.0))

    pasted = document.molecule.atom(document.molecule.atom_ids()[-1])
    assert pasted.partial_charge == -1
    assert pasted.partial_charge_direction is not None
    assert pasted.partial_charge_direction.x == pytest.approx(1.0)


def test_project_roundtrip_keeps_partial_charge_and_position() -> None:
    document, atom_id = _atom_document("O")
    document.set_atom_partial_charge(atom_id, -1, Point2D(-1.0, 0.0))

    data = project_to_data(Project(document.molecule))
    restored = project_from_data(data).molecule.atom(atom_id)

    assert restored.partial_charge == -1
    assert restored.partial_charge_direction is not None
    assert restored.partial_charge_direction.x == pytest.approx(-1.0)


# -- Werkzeug ------------------------------------------------------------
def test_click_sets_partial_plus_and_removes_it_again() -> None:
    document, atom_id = _atom_document()
    tool = PartialChargeTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(0.0, 0.0), _release())
    assert document.molecule.atom(atom_id).partial_charge == 1

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(0.0, 0.0), _release())
    assert document.molecule.atom(atom_id).partial_charge == 0


def test_right_click_sets_partial_minus() -> None:
    document, atom_id = _atom_document("O")
    tool = PartialChargeTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press(button=Qt.MouseButton.RightButton))
    tool.mouse_release(Point2D(0.0, 0.0), _release())

    assert document.molecule.atom(atom_id).partial_charge == -1


def test_shift_click_sets_partial_minus() -> None:
    document, atom_id = _atom_document()
    tool = PartialChargeTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press(Qt.KeyboardModifier.ShiftModifier))
    tool.mouse_release(Point2D(0.0, 0.0), _release())

    assert document.molecule.atom(atom_id).partial_charge == -1


def test_click_next_to_the_atom_does_nothing() -> None:
    document, atom_id = _atom_document()
    tool = PartialChargeTool(document)

    assert tool.mouse_press(Point2D(200.0, 200.0), _press()) is False
    assert document.molecule.atom(atom_id).partial_charge == 0


def test_holding_the_button_chooses_the_position() -> None:
    document, atom_id = _atom_document()
    tool = PartialChargeTool(document)

    tool.mouse_press(Point2D(0.0, 8.0), _press())
    assert tool.chooser_active is False  # erst nach kurzer Wartezeit
    tool._show_chooser()
    assert tool.chooser_active is True

    tool.mouse_move(Point2D(-20.0, 0.0), _move())
    tool.mouse_release(Point2D(-20.0, 0.0), _release())

    atom = document.molecule.atom(atom_id)
    assert atom.partial_charge == 1
    assert atom.partial_charge_direction is not None
    assert atom.partial_charge_direction.x == pytest.approx(-1.0, abs=1e-6)


def test_chooser_preview_does_not_fail() -> None:
    document, _atom_id = _atom_document()
    tool = PartialChargeTool(document)
    tool.mouse_press(Point2D(0.0, 8.0), _press())
    tool._show_chooser()

    image = QImage(160, 160, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(80.0, 80.0)
    tool.paint_overlay(painter)
    painter.end()

    assert _ink(image) > 0
