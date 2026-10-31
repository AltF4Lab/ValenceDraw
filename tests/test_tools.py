from __future__ import annotations

import math

import pytest
from PySide6.QtCore import Qt

from valencedraw.core.annotations import (
    DEFAULT_FLOW_BOW,
    MAX_FLOW_BOW,
    MAX_FLOW_BOW_ALONG,
    ArrowKind,
    ArrowObject,
)
from valencedraw.core.geometry import BOND_LENGTH, Point2D, angle_between
from valencedraw.core.molecule import MAX_ATOM_CHARGE, Molecule
from valencedraw.demo import benzene, ethane
from valencedraw.document.document import Document
from valencedraw.render.painter import (
    arrow_curve_handle,
    atom_label,
    atom_label_full,
    charge_rect,
    label_center,
)
from valencedraw.ui.charge_dialog import ChargeDialog
from valencedraw.ui.tools import (
    ArrowTool,
    AtomTool,
    BondTool,
    ChargeTool,
    EraseTool,
    RingTool,
    SelectTool,
    TextTool,
)
from qt_helpers import move as _move
from qt_helpers import press as _press
from qt_helpers import release as _release


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def test_bond_tool_creates_two_atoms_and_a_bond() -> None:
    document = Document()
    tool = BondTool(document)

    assert tool.mouse_press(Point2D(0.0, 0.0), _press())
    assert tool.mouse_move(Point2D(120.0, 10.0), _move())
    assert tool.mouse_release(Point2D(120.0, 10.0), _release())

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1
    first, second = document.molecule.atom_ids()
    start = document.molecule.atom(first).position
    end = document.molecule.atom(second).position
    assert start.distance_to(end) == pytest.approx(BOND_LENGTH)
    # Winkel rastet auf 0° ein -> exakt horizontal
    assert start.y == pytest.approx(end.y, abs=1e-6)
    assert document.undo_stack.count() == 1


def test_bond_tool_click_on_empty_space_adds_bond() -> None:
    document = Document()
    tool = BondTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(4.0, 3.0), _release())

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1
    start = document.molecule.atom(0).position
    end = document.molecule.atom(1).position
    assert start == Point2D(0.0, 0.0)
    # Ohne Hindernisse waagerecht und in Standardlänge.
    assert end.y == pytest.approx(0.0)
    assert start.distance_to(end) == pytest.approx(BOND_LENGTH)
    assert document.undo_stack.count() == 1


def test_bond_tool_raises_order_of_existing_bond() -> None:
    document = Document(ethane())
    tool = BondTool(document)

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())
    tool.mouse_release(Point2D(BOND_LENGTH / 2, 0.0), _release())

    assert len(document.molecule) == 2
    assert document.molecule.bonds[0].order == 2


def test_bond_tool_respects_bond_order_setting() -> None:
    document = Document()
    tool = BondTool(document)
    tool.bond_order = 3

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(100.0, 0.0), _release())

    assert document.molecule.bonds[0].order == 3


def test_select_tool_selects_and_moves_atoms() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    left = document.molecule.atom_ids()[0]

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())
    assert document.selection == frozenset({left})

    tool.mouse_move(Point2D(0.0, 20.0), _move())
    tool.mouse_release(Point2D(0.0, 20.0), _release())

    moved = document.molecule.atom(left).position
    assert moved.x == pytest.approx(0.0)
    assert moved.y == pytest.approx(20.0)
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.molecule.atom(left).position.y == pytest.approx(0.0)


def test_select_tool_shift_extends_selection() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    first, second = document.molecule.atom_ids()

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())
    tool.mouse_press(
        Point2D(BOND_LENGTH / 2, 0.0), _press(Qt.KeyboardModifier.ShiftModifier)
    )

    assert document.selection == frozenset({first, second})


def test_select_tool_click_on_empty_space_clears_selection() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    document.select_all()

    tool.mouse_press(Point2D(500.0, 500.0), _press())
    tool.mouse_release(Point2D(500.0, 500.0), _release())

    assert document.selection == frozenset()


def test_atom_tool_changes_element_of_existing_atom() -> None:
    document = Document(ethane())
    tool = AtomTool(document)
    tool.element = "N"
    atom_id = document.molecule.atom_ids()[0]

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())

    assert document.molecule.atom(atom_id).element == "N"
    assert document.undo_stack.count() == 1


def test_atom_tool_creates_new_atom_on_free_space() -> None:
    document = Document()
    tool = AtomTool(document)
    tool.element = "O"

    tool.mouse_press(Point2D(60.0, 40.0), _press())

    assert len(document.molecule) == 1
    atom = document.molecule.atom(document.molecule.atom_ids()[0])
    assert atom.element == "O"
    assert atom.position == Point2D(60.0, 40.0)


def test_atom_tool_labels_explicit_carbon() -> None:
    """Kohlenstoff ist im Skelett unsichtbar – explizit gesetzt zeigt er „C“."""
    document = Document()
    tool = AtomTool(document)  # Standardelement ist C

    tool.mouse_press(Point2D(60.0, 40.0), _press())

    atom_id = document.molecule.atom_ids()[0]
    assert document.molecule.atom(atom_id).element == "C"
    assert document.molecule.atom_label(atom_id) == "C"


def test_atom_tool_does_not_label_other_elements() -> None:
    document = Document()
    tool = AtomTool(document)
    tool.element = "O"

    tool.mouse_press(Point2D(60.0, 40.0), _press())

    atom_id = document.molecule.atom_ids()[0]
    assert document.molecule.atom_label(atom_id) == ""


def test_atom_tool_removes_carbon_label_when_element_changes() -> None:
    document = Document()
    tool = AtomTool(document)
    position = Point2D(60.0, 40.0)
    tool.mouse_press(position, _press())
    tool.element = "O"

    tool.mouse_press(position, _press())

    atom_id = document.molecule.atom_ids()[0]
    assert document.molecule.atom(atom_id).element == "O"
    assert document.molecule.atom_label(atom_id) == ""


def test_atom_tool_keeps_group_label_when_element_changes() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    document.molecule.set_label(atom_id, "NO2")
    tool = AtomTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())

    assert document.molecule.atom(atom_id).element == "C"
    assert document.molecule.atom_label(atom_id) == "NO2"


def test_explicit_carbon_label_is_rendered() -> None:
    document = Document()
    tool = AtomTool(document)
    tool.mouse_press(Point2D(60.0, 40.0), _press())
    atom_id = document.molecule.atom_ids()[0]

    assert atom_label(document.molecule, atom_id) == "C"


# -- Ladungswerkzeug ------------------------------------------------------
def _charge_click(tool, position, event=None) -> None:  # noqa: ANN001
    tool.mouse_press(position, event or _press())
    tool.mouse_release(position, _release())


def test_charge_tool_cycles_positive_charge() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)

    charges = []
    for _ in range(MAX_ATOM_CHARGE + 1):
        _charge_click(tool, Point2D(0.0, 0.0))
        charges.append(document.molecule.atom(atom_id).charge)

    assert charges == [*range(1, MAX_ATOM_CHARGE + 1), 0]
    assert document.undo_stack.count() == MAX_ATOM_CHARGE + 1


def test_charge_tool_right_click_cycles_negative_charge() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("O", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    right = Qt.MouseButton.RightButton

    charges = []
    for _ in range(MAX_ATOM_CHARGE + 1):
        _charge_click(tool, Point2D(0.0, 0.0), _press(button=right))
        charges.append(document.molecule.atom(atom_id).charge)

    assert charges == [-value for value in range(1, MAX_ATOM_CHARGE + 1)] + [0]


def test_charge_tool_shift_click_counts_down() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0), charge=2)
    tool = ChargeTool(document)

    _charge_click(tool, Point2D(0.0, 0.0), _press(Qt.KeyboardModifier.ShiftModifier))

    assert document.molecule.atom(atom_id).charge == -1


def test_charge_tool_switches_the_sign_on_the_opposite_charge() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0), charge=-2)
    tool = ChargeTool(document)

    _charge_click(tool, Point2D(0.0, 0.0))

    assert document.molecule.atom(atom_id).charge == 1


def test_charge_tool_ignores_free_canvas() -> None:
    document = Document()
    tool = ChargeTool(document)

    assert tool.mouse_press(Point2D(200.0, 150.0), _press()) is False
    assert document.undo_stack.count() == 0


def test_charge_tool_hits_an_offset_atom_label() -> None:
    """Endständige Labels liegen neben dem Atomzentrum und bleiben klickbar."""
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    document.molecule.set_element(atom_id, "O")
    tool = ChargeTool(document)

    _charge_click(tool, label_center(document.molecule, atom_id))

    assert document.molecule.atom(atom_id).charge == 1


def test_charge_is_rendered_next_to_the_atom() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    _charge_click(tool, Point2D(0.0, 0.0))
    _charge_click(tool, Point2D(0.0, 0.0))

    assert atom_label(document.molecule, atom_id) == "N"
    assert atom_label_full(document.molecule, atom_id) == "N2+"
    assert charge_rect(document.molecule, atom_id) is not None


def test_charge_tool_reaches_permanganate_charge() -> None:
    """Mn in MnO₄⁻ ist +7 – sieben Klicks müssen reichen."""
    document = Document()
    atom_id = document.molecule.add_atom("Mn", Point2D(0.0, 0.0))
    tool = ChargeTool(document)

    for _ in range(7):
        _charge_click(tool, Point2D(0.0, 0.0))

    assert document.molecule.atom(atom_id).charge == 7


def test_charge_tool_ctrl_click_opens_the_dialog(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("Mn", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    asked: list[int] = []

    def fake_ask(_cls, _parent, charge=0, symbol=""):  # noqa: ANN001
        asked.append(charge)
        return 5

    monkeypatch.setattr(ChargeDialog, "ask", classmethod(fake_ask))

    _charge_click(tool, Point2D(0.0, 0.0), _press(Qt.KeyboardModifier.ControlModifier))

    assert asked == [0]
    assert document.molecule.atom(atom_id).charge == 5


def test_charge_tool_double_click_starts_at_the_old_charge(monkeypatch) -> None:  # noqa: ANN001
    """Der erste Klick des Doppelklicks wird zurückgenommen."""

    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    asked: list[int] = []
    monkeypatch.setattr(
        ChargeDialog,
        "ask",
        classmethod(lambda _cls, _parent, charge=0, symbol="": asked.append(charge) or 4),
    )

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(0.0, 0.0), _release())
    assert document.molecule.atom(atom_id).charge == 1

    tool.mouse_double_click(Point2D(0.0, 0.0), _press())

    assert asked == [0]
    assert document.molecule.atom(atom_id).charge == 4


def test_charge_tool_dialog_cancel_keeps_the_old_charge(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    monkeypatch.setattr(
        ChargeDialog, "ask", classmethod(lambda _cls, _parent, charge=0, symbol="": None)
    )

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(0.0, 0.0), _release())
    tool.mouse_double_click(Point2D(0.0, 0.0), _press())

    assert document.molecule.atom(atom_id).charge == 0


# -- Positionsauswahl der Ladung (Gedrückthalten) -------------------------
def _patch_dialog(monkeypatch, result: int | None) -> list[int]:  # noqa: ANN001
    """Ersetzt den Ladungsdialog und merkt sich den Startwert."""
    asked: list[int] = []

    def fake_ask(_cls, _parent, charge=0, symbol=""):  # noqa: ANN001
        asked.append(charge)
        return result

    monkeypatch.setattr(ChargeDialog, "ask", classmethod(fake_ask))
    return asked


def test_holding_the_charge_button_shows_the_positions() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)

    tool.mouse_press(Point2D(0.0, 8.0), _press())
    assert tool.chooser_active is False  # erst nach kurzer Wartezeit

    tool._show_chooser()

    assert tool.chooser_active is True
    assert len(tool.chooser_directions()) == ChargeTool.CHOOSER_STEPS
    # Klick unterhalb des Atoms → Richtung „unten“ ist markiert
    assert tool.chooser_direction is not None
    assert tool.chooser_direction.y == pytest.approx(1.0, abs=1e-6)
    assert document.molecule.atom(atom_id).charge == 0  # noch nichts gesetzt


def test_charge_position_is_stored_and_value_asked(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    asked = _patch_dialog(monkeypatch, 3)

    tool.mouse_press(Point2D(0.0, 8.0), _press())
    tool._show_chooser()
    tool.mouse_move(Point2D(-20.0, 0.0), _move())
    tool.mouse_release(Point2D(-20.0, 0.0), _release())

    atom = document.molecule.atom(atom_id)
    assert asked == [1]  # sinnvoller Startwert für eine neue Ladung
    assert atom.charge == 3
    assert atom.charge_direction is not None
    assert atom.charge_direction.x == pytest.approx(-1.0, abs=1e-6)


def test_charge_position_dialog_cancel_changes_nothing(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    _patch_dialog(monkeypatch, None)

    tool.mouse_press(Point2D(0.0, 8.0), _press())
    tool._show_chooser()
    tool.mouse_release(Point2D(0.0, 8.0), _release())

    atom = document.molecule.atom(atom_id)
    assert atom.charge == 0
    assert atom.charge_direction is None
    assert document.undo_stack.count() == 0


def test_charge_position_negative_start_value(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("O", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    asked = _patch_dialog(monkeypatch, -2)

    tool.mouse_press(Point2D(8.0, 0.0), _press(button=Qt.MouseButton.RightButton))
    tool._show_chooser()
    tool.mouse_release(Point2D(8.0, 0.0), _release())

    assert asked == [-1]
    assert document.molecule.atom(atom_id).charge == -2


def test_charge_picker_cancel_on_deactivate(monkeypatch) -> None:  # noqa: ANN001
    document = Document()
    atom_id = document.molecule.add_atom("N", Point2D(0.0, 0.0))
    tool = ChargeTool(document)
    asked = _patch_dialog(monkeypatch, 4)
    tool.mouse_press(Point2D(0.0, 8.0), _press())
    tool._show_chooser()

    tool.deactivate()
    tool.mouse_release(Point2D(0.0, 8.0), _release())

    assert asked == []
    assert document.molecule.atom(atom_id).charge == 0
    assert tool.chooser_active is False


def test_erase_tool_removes_atom_and_its_bonds() -> None:
    document = Document(ethane())
    tool = EraseTool(document)

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())

    assert len(document.molecule) == 1
    assert document.molecule.bonds == ()
    assert document.undo_stack.count() == 1


def test_eraser_does_not_leave_stale_selection() -> None:
    document = Document(ethane())
    tool = EraseTool(document)
    atom_id = document.molecule.atom_ids()[0]
    document.select_only(atom_id)

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())

    assert document.selection == frozenset()


def test_eraser_removes_only_the_label_first() -> None:
    """Ein beschriftetes Atom behält beim ersten Klick seine Bindungen."""
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.set_atom_label(atom_id, "OTs")
    tool = EraseTool(document)
    position = Point2D(BOND_LENGTH / 2, 0.0)
    before = document.undo_stack.count()

    tool.mouse_press(position, _press())

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1
    assert document.molecule.atom_label(atom_id) == ""
    assert document.undo_stack.count() == before + 1


def test_eraser_clears_a_charge_before_deleting_the_atom() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.set_atom_charge(atom_id, 2)
    tool = EraseTool(document)
    position = Point2D(BOND_LENGTH / 2, 0.0)

    tool.mouse_press(position, _press())

    atom = document.molecule.atom(atom_id)
    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1
    assert atom.charge == 0
    assert atom.element == "C"


def test_eraser_removes_atom_with_second_click() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.set_atom_label(atom_id, "OTs")
    tool = EraseTool(document)
    position = Point2D(BOND_LENGTH / 2, 0.0)

    tool.mouse_press(position, _press())
    tool.mouse_press(position, _press())

    assert len(document.molecule) == 1
    assert document.molecule.bonds == ()


def test_eraser_turns_element_into_carbon_but_keeps_bonds() -> None:
    """Aceton: das O wegzuradieren lässt die Doppelbindung stehen."""
    molecule = Molecule()
    c1 = molecule.add_atom("C", Point2D(0.0, 0.0))
    c2 = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    c3 = molecule.add_atom("C", Point2D(2 * BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, -BOND_LENGTH))
    molecule.add_bond(c1, c2)
    molecule.add_bond(c2, c3)
    molecule.add_bond(c2, oxygen, order=2)
    document = Document(molecule)
    tool = EraseTool(document)

    tool.mouse_press(Point2D(BOND_LENGTH, -BOND_LENGTH), _press())

    result = document.molecule
    assert len(result) == 4
    assert len(result.bonds) == 3
    assert result.atom(oxygen).element == "C"
    assert result.atom(oxygen).label == ""
    assert sorted(bond.order for bond in result.bonds) == [1, 1, 2]


def test_eraser_resets_charge_to_carbon() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)
    document = Document(molecule)
    tool = EraseTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())

    atom = document.molecule.atom(atom_id)
    assert atom.element == "C"
    assert atom.charge == 0


def test_eraser_label_removal_is_undoable() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.set_atom_label(atom_id, "OTs")
    tool = EraseTool(document)

    tool.mouse_press(Point2D(BOND_LENGTH / 2, 0.0), _press())
    document.undo_stack.undo()

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1
    assert document.molecule.atom_label(atom_id) == "OTs"


# -- Bindungsordnung -----------------------------------------------------
def test_click_on_bond_cycles_order_with_bond_tool() -> None:
    document = Document(ethane())
    tool = BondTool(document)
    middle = Point2D(0.0, 0.0)

    for expected_order, expected_side, expected_centered in (
        (2, 0, True),
        (2, 1, False),
        (2, -1, False),
        (3, 0, False),
        (1, 0, False),
    ):
        tool.mouse_press(middle, _press())
        tool.mouse_release(middle, _release())
        bond = document.molecule.bonds[0]
        assert bond.order == expected_order
        assert bond.side == expected_side
        assert bond.centered is expected_centered

    assert document.undo_stack.count() == 5
    document.undo_stack.undo()
    assert document.molecule.bonds[0].order == 3


def test_click_on_empty_space_adds_a_bond_without_cycling() -> None:
    document = Document(ethane())
    tool = BondTool(document)
    point = Point2D(500.0, 500.0)

    tool.mouse_press(point, _press())
    tool.mouse_release(point, _release())

    # Die vorhandene Bindung bleibt unverändert …
    assert len(document.molecule) == 4
    assert document.molecule.bonds[0].order == 1
    # … und an der Klickstelle entsteht eine neue Bindung.
    assert len(document.molecule.bonds) == 2
    new_atoms = document.molecule.atom_ids()[-2:]
    assert document.molecule.bond_between(*new_atoms) is not None
    assert document.undo_stack.count() == 1


# -- Automatische Bindungsrichtung ---------------------------------------
def _click_atom(tool, document, atom_id) -> None:  # noqa: ANN001
    position = document.molecule.atom(atom_id).position
    tool.mouse_press(position, _press())
    tool.mouse_release(position, _release())


def test_bond_tool_click_on_atom_adds_bond_in_best_direction() -> None:
    document = Document(ethane())
    tool = BondTool(document)
    right = max(
        document.molecule.atom_ids(),
        key=lambda atom_id: document.molecule.atom(atom_id).position.x,
    )

    _click_atom(tool, document, right)

    assert len(document.molecule) == 3
    new_atom = max(document.molecule.atom_ids())
    assert document.molecule.bond_between(right, new_atom) is not None
    start = document.molecule.atom(right).position
    end = document.molecule.atom(new_atom).position
    assert start.distance_to(end) == pytest.approx(BOND_LENGTH)
    # Die neue Bindung steht im idealen Winkel zur bestehenden.
    existing = (document.molecule.atom(0).position - start).normalized()
    added = (end - start).normalized()
    assert angle_between(existing, added) == pytest.approx(120.0)


def test_bond_tool_auto_direction_points_out_of_the_ring() -> None:
    document = Document(benzene())
    molecule = document.molecule
    atom_id = max(molecule.atom_ids(), key=lambda i: molecule.atom(i).position.x)
    tool = BondTool(document)

    _click_atom(tool, document, atom_id)

    start = molecule.atom(atom_id).position
    end = molecule.atom(max(molecule.atom_ids())).position
    # Nicht in den Ring hinein, sondern nach außen.
    assert end.distance_to(Point2D()) > start.distance_to(Point2D())
    assert end.x > start.x


def test_bond_tool_click_near_the_page_edge_turns_inward() -> None:
    document = Document()
    tool = BondTool(document)
    _low, high = document.page.bounds
    start = Point2D(high.x - 10.0, 0.0)

    tool.mouse_press(start, _press())
    tool.mouse_release(start, _release())

    assert len(document.molecule) == 2
    end = document.molecule.atom(1).position
    assert tool.is_on_page(end)
    assert end.x < start.x


def test_bond_tool_click_on_empty_space_keeps_clear_of_atoms() -> None:
    document = Document(ethane())
    tool = BondTool(document)
    start = Point2D(-60.0, 0.0)

    tool.mouse_press(start, _press())
    tool.mouse_release(start, _release())

    molecule = document.molecule
    end = molecule.atom(molecule.atom_ids()[-1]).position
    for atom_id in molecule.atom_ids()[:-1]:
        clearance = BOND_LENGTH * BondTool.AUTO_ATOM_CLEARANCE
        assert end.distance_to(molecule.atom(atom_id).position) >= clearance - 1e-6


def test_bond_tool_auto_direction_stays_on_the_page() -> None:
    document = Document()
    _low, high = document.page.bounds
    atom_id = document.molecule.add_atom("C", Point2D(high.x - 10.0, 0.0))
    tool = BondTool(document)

    _click_atom(tool, document, atom_id)

    assert len(document.molecule) == 2
    start = document.molecule.atom(atom_id).position
    end = document.molecule.atom(max(document.molecule.atom_ids())).position
    assert tool.is_on_page(end)
    assert end.x < start.x  # von der Blattkante weg


def test_bond_tool_auto_bond_is_undoable() -> None:
    document = Document(ethane())
    tool = BondTool(document)

    _click_atom(tool, document, document.molecule.atom_ids()[0])
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1


def test_bond_tool_auto_bond_uses_the_selected_order() -> None:
    document = Document(ethane())
    tool = BondTool(document)
    tool.bond_order = 2

    _click_atom(tool, document, document.molecule.atom_ids()[0])

    assert document.molecule.bonds[-1].order == 2


def test_select_tool_click_cycles_bond_order() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    middle = Point2D(0.0, 0.0)

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].order == 2
    assert document.molecule.bonds[0].centered

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].order == 2
    assert not document.molecule.bonds[0].centered
    assert document.molecule.bonds[0].side == 1

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].order == 2
    assert document.molecule.bonds[0].side == -1

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].order == 3


# -- Auswahl von Texten und Pfeilen --------------------------------------
def test_box_selection_selects_whole_molecule() -> None:
    document = Document(ethane())
    tool = SelectTool(document)

    tool.mouse_press(Point2D(-40.0, -40.0), _press())
    tool.mouse_move(Point2D(40.0, 40.0), _move())
    tool.mouse_release(Point2D(40.0, 40.0), _release())

    assert document.selection == frozenset(document.molecule.atom_ids())


def test_box_selection_selects_texts_and_arrows() -> None:
    document = Document()
    document.add_text(Point2D(100.0, 100.0), "Ph")
    document.add_arrow(Point2D(200.0, 100.0), Point2D(300.0, 100.0))
    tool = SelectTool(document)

    tool.mouse_press(Point2D(80.0, 80.0), _press())
    tool.mouse_move(Point2D(320.0, 140.0), _move())
    tool.mouse_release(Point2D(320.0, 140.0), _release())

    assert document.text_selection == frozenset({0})
    assert document.arrow_selection == frozenset({0})


def test_box_selection_then_drag_moves_whole_molecule() -> None:
    document = Document(ethane())
    tool = SelectTool(document)

    tool.mouse_press(Point2D(-40.0, -40.0), _press())
    tool.mouse_move(Point2D(40.0, 40.0), _move())
    tool.mouse_release(Point2D(40.0, 40.0), _release())

    # Auswahl am rechten Atom packen und verschieben.
    tool.mouse_press(Point2D(20.0, 0.0), _press())
    tool.mouse_move(Point2D(40.0, 20.0), _move())
    tool.mouse_release(Point2D(40.0, 20.0), _release())

    assert document.molecule.atom(0).position == Point2D(0.0, 20.0)
    assert document.molecule.atom(1).position == Point2D(40.0, 20.0)


def test_box_selection_preview_is_drawn_while_dragging() -> None:
    from PySide6.QtGui import QImage, QPainter

    document = Document(ethane())
    tool = SelectTool(document)
    tool.mouse_press(Point2D(10.0, 10.0), _press())
    tool.mouse_move(Point2D(100.0, 100.0), _move())

    image = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    tool.paint_overlay(painter)
    painter.end()

    assert image.pixelColor(50, 50).alpha() > 0
    assert image.pixelColor(150, 150).alpha() == 0


def test_select_tool_selects_and_moves_text() -> None:
    document = Document(ethane())
    document.add_text(Point2D(100.0, 100.0), "Ph")
    tool = SelectTool(document)
    start = Point2D(102.0, 102.0)

    tool.mouse_press(start, _press())
    assert document.text_selection == frozenset({0})

    tool.mouse_move(start + Point2D(20.0, 10.0), _move())
    tool.mouse_release(start + Point2D(20.0, 10.0), _release())

    assert document.texts[0].position == Point2D(120.0, 110.0)
    # Das Molekül bleibt unverändert.
    assert len(document.molecule.bonds) == 1
    assert document.molecule.atom(0).position == Point2D(-BOND_LENGTH / 2, 0.0)


def test_select_tool_selects_and_moves_arrow() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 200.0), Point2D(100.0, 200.0))
    tool = SelectTool(document)

    tool.mouse_press(Point2D(50.0, 200.0), _press())
    assert document.arrow_selection == frozenset({0})

    tool.mouse_move(Point2D(50.0, 230.0), _move())
    tool.mouse_release(Point2D(50.0, 230.0), _release())

    arrow = document.arrows[0]
    assert arrow.start == Point2D(0.0, 230.0)
    assert arrow.end == Point2D(100.0, 230.0)


def test_click_on_arrow_end_selects_the_arrow() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    tool = SelectTool(document)

    tool.mouse_press(Point2D(100.0, 0.0), _press())

    assert document.arrow_selection == frozenset({0})


def test_arrow_handle_drag_extends_the_arrow() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    document.select_arrow(0)
    tool = SelectTool(document)

    tool.mouse_press(Point2D(100.0, 0.0), _press())
    tool.mouse_move(Point2D(160.0, 0.0), _move())
    tool.mouse_release(Point2D(160.0, 0.0), _release())

    arrow = document.arrows[0]
    assert arrow.start == Point2D(0.0, 0.0)
    assert arrow.end == Point2D(160.0, 0.0)
    assert document.undo_stack.count() == 2  # Pfeil zeichnen + verlängern


def test_arrow_handle_drag_moves_the_start_point() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    document.select_arrow(0)
    tool = SelectTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_move(Point2D(-40.0, 0.0), _move())
    tool.mouse_release(Point2D(-40.0, 0.0), _release())

    arrow = document.arrows[0]
    assert arrow.start.x == pytest.approx(-40.0)
    assert arrow.start.y == pytest.approx(0.0)
    assert arrow.end == Point2D(100.0, 0.0)


def test_flow_arrow_end_drag_continues_the_circle() -> None:
    """Das Pfeilende wandert auf demselben Kreis weiter (konstante Krümmung)."""
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.PAIR_FLOW)
    document.select_arrow(0)
    arrow = document.arrows[0]
    arc = arrow.arc
    assert arc is not None
    tool = SelectTool(document)

    tool.mouse_press(Point2D(100.0, 0.0), _press())
    tool.mouse_move(Point2D(150.0, 0.0), _move())
    tool.mouse_release(Point2D(150.0, 0.0), _release())

    resized = document.arrows[0]
    resized_arc = resized.arc
    assert resized_arc is not None
    # Gleicher Kreis: Radius und Mittelpunkt bleiben erhalten.
    assert resized_arc.center.x == pytest.approx(arc.center.x)
    assert resized_arc.center.y == pytest.approx(arc.center.y)
    assert resized_arc.radius == pytest.approx(arc.radius)
    # Der Endpunkt ist die radiale Projektion der Maus auf den alten Kreis.
    direction = (Point2D(150.0, 0.0) - arc.center).normalized()
    expected = arc.center + direction * arc.radius
    assert resized.end.x == pytest.approx(expected.x)
    assert resized.end.y == pytest.approx(expected.y)
    assert resized_arc.length > arc.length
    assert document.undo_stack.undoText() == "Pfeil verlängern"


def test_flow_arrow_start_drag_continues_the_circle() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.PAIR_FLOW)
    document.select_arrow(0)
    arrow = document.arrows[0]
    arc = arrow.arc
    assert arc is not None
    tool = SelectTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_move(Point2D(-50.0, 0.0), _move())
    tool.mouse_release(Point2D(-50.0, 0.0), _release())

    resized = document.arrows[0]
    resized_arc = resized.arc
    assert resized_arc is not None
    assert resized_arc.center.x == pytest.approx(arc.center.x)
    assert resized_arc.center.y == pytest.approx(arc.center.y)
    assert resized_arc.radius == pytest.approx(arc.radius)
    # Das andere Ende bleibt fest, das gezogene liegt auf dem alten Kreis.
    assert resized.end == arrow.end
    assert resized.start.distance_to(arc.center) == pytest.approx(arc.radius)
    assert resized.start != arrow.start
    assert resized_arc.length > arc.length


# -- Krümmung nachträglich ändern ----------------------------------------
def _flow_arrow_document() -> Document:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.PAIR_FLOW)
    document.select_arrow(0)
    return document


def test_curve_handle_sits_on_the_curve() -> None:
    document = _flow_arrow_document()
    arrow = document.arrows[0]

    handle = arrow_curve_handle(arrow)

    assert handle is not None
    assert handle.x == pytest.approx(50.0)
    assert handle.y == pytest.approx(-16.0, abs=0.5)


def test_straight_arrow_has_no_curve_handle() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.FORWARD)

    assert arrow_curve_handle(document.arrows[0]) is None


def test_dragging_the_curve_handle_changes_the_bow() -> None:
    document = _flow_arrow_document()
    arrow = document.arrows[0]
    handle = arrow_curve_handle(arrow)
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(50.0, -46.0), _move())
    tool.mouse_release(Point2D(50.0, -46.0), _release())

    bent = document.arrows[0]
    assert bent.bow == pytest.approx(0.92, abs=0.01)
    assert bent.start == arrow.start and bent.end == arrow.end  # Länge unverändert
    assert document.undo_stack.count() == 2
    assert document.undo_stack.undoText() == "Pfeilkrümmung ändern"


def test_dragging_to_the_other_side_flips_the_curve() -> None:
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(50.0, 30.0), _move())
    tool.mouse_release(Point2D(50.0, 30.0), _release())

    assert document.arrows[0].bow < 0.0


def test_curve_is_limited() -> None:
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(50.0, -400.0), _move())
    tool.mouse_release(Point2D(50.0, -400.0), _release())

    assert document.arrows[0].bow == pytest.approx(MAX_FLOW_BOW)


def test_dragging_along_the_arrow_shifts_the_bow() -> None:
    """Seitliches Ziehen verbiegt den Bogen in diese Richtung."""
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(70.0, -46.0), _move())
    tool.mouse_release(Point2D(70.0, -46.0), _release())

    bent = document.arrows[0]
    assert bent.bow == pytest.approx(0.92, abs=0.01)
    assert bent.bow_along == pytest.approx(0.4, abs=0.01)
    # Der Greifpunkt folgt der Maus (Kurvenmitte).
    new_handle = arrow_curve_handle(bent)
    assert new_handle is not None
    assert new_handle.x == pytest.approx(70.0, abs=1.0)
    assert new_handle.y == pytest.approx(-46.0, abs=1.0)


def test_dragging_back_to_the_middle_straightens_the_skew() -> None:
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(80.0, -16.0), _move())
    tool.mouse_release(Point2D(80.0, -16.0), _release())

    assert document.arrows[0].bow_along == pytest.approx(0.6, abs=0.01)


def test_bow_along_is_limited() -> None:
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(400.0, -40.0), _move())
    tool.mouse_release(Point2D(400.0, -40.0), _release())

    assert document.arrows[0].bow_along == pytest.approx(MAX_FLOW_BOW_ALONG)


def test_bow_drag_is_undoable() -> None:
    document = _flow_arrow_document()
    original = document.arrows[0].bow
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(50.0, -46.0), _move())
    tool.mouse_release(Point2D(50.0, -46.0), _release())
    document.undo_stack.undo()

    assert document.arrows[0].bow == pytest.approx(original)


def test_curvature_drag_shifts_the_bulge_along_the_arrow() -> None:
    """Der Scheitel wandert mit der Maus auch entlang des Pfeils (asymmetrisch)."""
    document = _flow_arrow_document()
    handle = arrow_curve_handle(document.arrows[0])
    assert handle is not None
    tool = SelectTool(document)

    tool.mouse_press(handle, _press())
    tool.mouse_move(Point2D(70.0, -30.0), _move())
    tool.mouse_release(Point2D(70.0, -30.0), _release())

    arrow = document.arrows[0]
    points = arrow.points(samples=200)
    highest = min(points, key=lambda point: point.y)
    assert highest.x == pytest.approx(70.0, abs=0.5)
    assert highest.y == pytest.approx(-30.0, abs=0.2)
    # Links und rechts des Scheitels liegen unterschiedliche Kreisbögen.
    assert len(arrow.arcs) == 2
    assert arrow.arcs[0].radius != pytest.approx(arrow.arcs[1].radius)


def test_asymmetric_flow_arrow_extension_keeps_the_fixed_arc() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW)
    document.set_arrow_object(
        0,
        ArrowObject(
            Point2D(0.0, 0.0),
            Point2D(200.0, 0.0),
            ArrowKind.PAIR_FLOW,
            0.3,
            0.4,
        ),
    )
    document.select_arrow(0)
    before = document.arrows[0]
    first_before, second_before = before.arcs
    target = second_before.point_at_angle(
        second_before.start_angle + second_before.sweep + math.radians(30.0)
    )
    tool = SelectTool(document)

    tool.mouse_press(before.end, _press())
    tool.mouse_move(target, _move())
    tool.mouse_release(target, _release())

    after = document.arrows[0]
    first_after, second_after = after.arcs
    # Der feste Bogen links des Scheitels bleibt unverändert.
    assert first_after.center.distance_to(first_before.center) < 1e-3
    assert first_after.radius == pytest.approx(first_before.radius, abs=1e-3)
    assert first_after.sweep == pytest.approx(first_before.sweep, abs=1e-3)
    # Der verlängerte Bogen liegt weiterhin auf seinem Kreis.
    assert second_after.center.distance_to(second_before.center) < 1e-3
    assert second_after.radius == pytest.approx(second_before.radius, abs=1e-3)
    assert abs(second_after.sweep) > abs(second_before.sweep)


def test_flow_arrow_extends_beyond_180_degrees() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.PAIR_FLOW)
    document.select_arrow(0)
    arrow = document.arrows[0]
    arc = arrow.arc
    assert arc is not None
    target = arc.point_at_angle(arc.start_angle + math.radians(215.0))
    tool = SelectTool(document)

    tool.mouse_press(Point2D(100.0, 0.0), _press())
    tool.mouse_move(target, _move())
    tool.mouse_release(target, _release())

    resized = document.arrows[0]
    assert resized.arc is not None
    assert abs(resized.arc.sweep) > math.pi
    assert resized.end.distance_to(target) == pytest.approx(0.0, abs=1.0)
    assert resized.end.distance_to(arc.center) == pytest.approx(arc.radius, abs=1e-3)


# -- Bindungs-Hover ------------------------------------------------------
@pytest.mark.parametrize("factory", [SelectTool, BondTool])
def test_bond_hover_highlights_bond_under_cursor(factory) -> None:  # noqa: ANN001
    document = Document(ethane())
    tool = factory(document)

    assert tool.mouse_move(Point2D(0.0, 0.0), _move())
    assert tool.hovered_bond == document.molecule.bonds[0]

    assert tool.mouse_move(Point2D(300.0, 300.0), _move())
    assert tool.hovered_bond is None


def test_bond_hover_is_off_over_atoms() -> None:
    """Direkt am Atomende (Label) wird keine Bindung hervorgehoben."""
    document = Document(ethane())
    tool = SelectTool(document)

    tool.mouse_move(Point2D(-BOND_LENGTH / 2, 0.0), _move())

    assert tool.hovered_bond is None


def test_bond_hover_is_off_for_other_tools() -> None:
    document = Document(ethane())
    tool = AtomTool(document)

    tool.mouse_move(Point2D(0.0, 0.0), _move())

    assert tool.hovered_bond is None


def test_clear_hover_removes_bond_highlight() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    tool.mouse_move(Point2D(0.0, 0.0), _move())

    assert tool.clear_hover() is True
    assert tool.hovered_bond is None
    assert tool.clear_hover() is False


def test_eraser_hover_is_cleared_on_leave() -> None:
    document = Document(ethane())
    tool = EraseTool(document)
    tool.mouse_move(Point2D(0.0, 0.0), _move())

    assert tool.clear_hover() is True
    assert tool.clear_hover() is False


# -- Text ----------------------------------------------------------------
def test_text_tool_requests_new_text() -> None:
    document = Document()
    tool = TextTool(document)
    requests: list[tuple[Point2D, object]] = []
    tool.text_requested.connect(lambda position, existing: requests.append((position, existing)))

    assert tool.mouse_press(Point2D(30.0, 40.0), _press())

    assert requests == [(Point2D(30.0, 40.0), None)]


def test_text_tool_requests_existing_text_for_editing() -> None:
    document = Document()
    existing = document.add_text(Point2D(0.0, 0.0), "H_2O")
    tool = TextTool(document)
    requests: list[tuple[Point2D, object]] = []
    tool.text_requested.connect(lambda position, found: requests.append((position, found)))

    tool.mouse_press(Point2D(5.0, 5.0), _press())

    assert requests and requests[0][1] == existing


def test_text_tool_requests_atom_label_on_atom_click() -> None:
    document = Document(ethane())
    tool = TextTool(document)
    labels: list[int] = []
    texts: list[object] = []
    tool.atom_label_requested.connect(labels.append)
    tool.text_requested.connect(lambda position, existing: texts.append(existing))

    assert tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())

    assert labels == [0]
    assert texts == []


def test_text_tool_hits_offset_atom_label() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(left, right)
    document = Document(molecule)
    tool = TextTool(document)
    labels: list[int] = []
    tool.atom_label_requested.connect(labels.append)

    center = label_center(molecule, right)
    # Das Label eines endständigen Atoms liegt außerhalb des reinen Trefferradius.
    assert center.x > BOND_LENGTH + tool.hit_radius
    assert tool.mouse_press(center, _press())

    assert labels == [right]


# -- Hover-Feedback ------------------------------------------------------
def test_bond_tool_highlights_atom_under_cursor() -> None:
    document = Document(ethane())
    tool = BondTool(document)

    assert tool.mouse_move(Point2D(-BOND_LENGTH / 2, 3.0), _move())
    assert tool.snap_atom == 0

    assert tool.mouse_move(Point2D(400.0, 400.0), _move())
    assert tool.snap_atom is None

    tool.mouse_move(Point2D(-BOND_LENGTH / 2, 0.0), _move())
    tool.deactivate()
    assert tool.snap_atom is None


def test_atom_and_ring_tools_highlight_atom_under_cursor() -> None:
    for factory in (AtomTool, RingTool):
        document = Document(ethane())
        tool = factory(document)

        assert tool.mouse_move(Point2D(BOND_LENGTH / 2, 0.0), _move())
        assert tool.snap_atom == 1

        assert tool.clear_hover()
        assert tool.snap_atom is None
        assert not tool.clear_hover()


def test_select_tool_does_not_track_snap_hover() -> None:
    document = Document(ethane())
    tool = SelectTool(document)

    tool.mouse_move(Point2D(BOND_LENGTH / 2, 0.0), _move())

    assert tool.snap_atom is None


# -- Pfeile --------------------------------------------------------------
def test_arrow_tool_creates_snapped_arrow() -> None:
    document = Document()
    tool = ArrowTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_move(Point2D(100.0, 6.0), _move())
    tool.mouse_release(Point2D(100.0, 6.0), _release())

    assert len(document.arrows) == 1
    arrow = document.arrows[0]
    assert arrow.start == Point2D(0.0, 0.0)
    assert arrow.end.y == pytest.approx(0.0, abs=1e-6)
    assert arrow.length == pytest.approx(math.hypot(100.0, 6.0))
    assert document.undo_stack.count() == 1


def test_arrow_tool_uses_selected_kind() -> None:
    document = Document()
    tool = ArrowTool(document)
    tool.kind = ArrowKind.EQUILIBRIUM

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(0.0, 80.0), _release())

    assert document.arrows[0].kind is ArrowKind.EQUILIBRIUM


def test_arrow_tool_ignores_tiny_drags() -> None:
    document = Document()
    tool = ArrowTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(5.0, 5.0), _release())

    assert document.arrows == ()
    assert document.undo_stack.count() == 0


def test_arrow_tool_creates_a_curved_flow_arrow() -> None:
    from PySide6.QtGui import QImage, QPainter

    document = Document()
    tool = ArrowTool(document)
    tool.kind = ArrowKind.PAIR_FLOW

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_move(Point2D(120.0, 4.0), _move())
    image = QImage(40, 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    tool.paint_overlay(painter)  # Vorschau darf nicht scheitern
    painter.end()
    tool.mouse_release(Point2D(120.0, 4.0), _release())

    arrow = document.arrows[0]
    assert arrow.kind is ArrowKind.PAIR_FLOW
    assert arrow.bow == pytest.approx(DEFAULT_FLOW_BOW)
    assert len(arrow.points()) > 2


def test_radical_flow_arrow_gets_the_same_bow() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.RADICAL_FLOW)

    assert document.arrows[0].bow == pytest.approx(DEFAULT_FLOW_BOW)


def test_reaction_arrow_stays_straight() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.FORWARD)

    assert document.arrows[0].bow == 0.0


def test_flow_arrow_move_keeps_the_curve() -> None:
    document = Document()
    arrow = document.add_arrow(
        Point2D(0.0, 0.0), Point2D(100.0, 0.0), ArrowKind.PAIR_FLOW
    )
    document.select_all()

    document.move_selection(Point2D(0.0, 40.0))

    moved = document.arrows[0]
    assert moved.bow == pytest.approx(arrow.bow)
    assert moved.start.y == pytest.approx(40.0)


def test_curved_arrow_is_hit_on_its_bow() -> None:
    """Ein gebogener Pfeil muss auch abseits der Geraden trefferbar sein."""
    document = Document()
    arrow = document.add_arrow(
        Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW
    )
    tool = SelectTool(document)
    points = arrow.points()
    apex = points[len(points) // 2]

    assert apex.y < -20.0  # Kurve liegt deutlich über der Geraden
    assert tool.find_arrow_index(apex) == 0


# -- Radierer: Annotationen ---------------------------------------------
def test_eraser_removes_text() -> None:
    document = Document()
    document.add_text(Point2D(0.0, 0.0), "H_{2}O")
    tool = EraseTool(document)

    tool.mouse_press(Point2D(5.0, 5.0), _press())

    assert document.texts == ()
    document.undo_stack.undo()
    assert len(document.texts) == 1


def test_eraser_removes_arrow() -> None:
    document = Document()
    document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    tool = EraseTool(document)

    tool.mouse_press(Point2D(50.0, 2.0), _press())

    assert document.arrows == ()
    document.undo_stack.undo()
    assert len(document.arrows) == 1


# -- Blattgrenze ---------------------------------------------------------
def test_bond_tool_clamps_new_atom_to_page() -> None:
    document = Document()
    tool = BondTool(document)
    low, high = document.page.bounds
    outside = Point2D(high.x + 500.0, high.y + 500.0)

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(outside, _release())

    assert len(document.molecule) == 2
    for atom in document.molecule.atoms.values():
        assert low.x <= atom.position.x <= high.x
        assert low.y <= atom.position.y <= high.y


def test_select_tool_keeps_dragged_atoms_on_page() -> None:
    document = Document(ethane())
    tool = SelectTool(document)
    atom_id = document.molecule.atom_ids()[0]
    low, high = document.page.bounds

    tool.mouse_press(Point2D(-BOND_LENGTH / 2, 0.0), _press())
    tool.mouse_move(Point2D(high.x + 500.0, high.y + 500.0), _move())
    tool.mouse_release(Point2D(high.x + 500.0, high.y + 500.0), _release())

    moved = document.molecule.atom(atom_id).position
    assert moved.x == pytest.approx(high.x)
    assert moved.y == pytest.approx(high.y)


def test_arrow_tool_clamps_end_to_page() -> None:
    document = Document()
    tool = ArrowTool(document)
    _low, high = document.page.bounds

    tool.mouse_press(Point2D(0.0, 0.0), _press())
    tool.mouse_release(Point2D(high.x + 500.0, 0.0), _release())

    assert len(document.arrows) == 1
    assert document.arrows[0].end.x <= high.x


def test_ring_tool_ignores_ring_leaving_the_page() -> None:
    document = Document()
    tool = RingTool(document)
    _low, high = document.page.bounds

    tool.mouse_press(Point2D(high.x - 10.0, 0.0), _press())

    assert document.is_empty()
    assert document.undo_stack.count() == 0


def test_ring_tool_still_works_inside_the_page() -> None:
    document = Document()
    tool = RingTool(document)

    tool.mouse_press(Point2D(0.0, 0.0), _press())

    assert len(document.molecule) == tool.template.size
    assert document.undo_stack.count() == 1

