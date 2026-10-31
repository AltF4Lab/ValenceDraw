from __future__ import annotations

import pytest

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import MAX_ATOM_CHARGE
from valencedraw.core.page import Orientation, Page, PageFormat
from valencedraw.demo import ethane
from valencedraw.document.document import Document


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    """QUndoStack braucht eine QApplication-Instanz."""
    yield


def test_new_document_is_empty() -> None:
    document = Document()
    assert document.is_empty()
    assert document.selection == frozenset()
    assert document.undo_stack.count() == 0


def test_edit_creates_single_undo_step() -> None:
    document = Document()
    with document.edit("Atom hinzufügen"):
        document.molecule.add_atom("C", Point2D(0.0, 0.0))

    assert document.undo_stack.count() == 1
    assert len(document.molecule) == 1

    document.undo_stack.undo()
    assert len(document.molecule) == 0

    document.undo_stack.redo()
    assert len(document.molecule) == 1


def test_noop_edit_creates_no_undo_step() -> None:
    document = Document(ethane())
    with document.edit("nichts"):
        pass
    assert document.undo_stack.count() == 0


def test_edit_emits_changed_signal() -> None:
    document = Document()
    calls: list[int] = []
    document.changed.connect(lambda: calls.append(1))

    with document.edit("Atom"):
        document.molecule.add_atom()

    assert calls


def test_failed_edit_does_not_commit() -> None:
    document = Document(ethane())
    with pytest.raises(RuntimeError):
        with document.edit("kaputt"):
            document.molecule.add_atom()
            raise RuntimeError("Abbruch")

    # Änderung am Modell ist passiert, aber kein Undo-Schritt entstanden
    assert document.undo_stack.count() == 0


def test_delete_selection_and_undo() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    document.select_only(atom_id)

    document.delete_selection()

    assert len(document.molecule) == 1
    assert document.selection == frozenset()

    document.undo_stack.undo()
    assert len(document.molecule) == 2


def test_selection_ignores_unknown_atoms() -> None:
    document = Document(ethane())
    document.select_only(999)
    assert document.selection == frozenset()


def test_selection_is_pruned_after_undo() -> None:
    document = Document(ethane())
    with document.edit("Atom"):
        new_atom = document.molecule.add_atom("O", Point2D(BOND_LENGTH * 2, 0.0))

    document.select_only(new_atom)
    assert document.selection == frozenset({new_atom})

    document.undo_stack.undo()
    assert document.selection == frozenset()


def test_toggle_and_select_all() -> None:
    document = Document(ethane())
    first, second = document.molecule.atom_ids()

    document.toggle_atom(first)
    assert document.selection == frozenset({first})
    document.toggle_atom(first)
    assert document.selection == frozenset()

    document.select_all()
    assert document.selection == frozenset({first, second})

    document.clear_selection()
    assert document.selection == frozenset()


def test_replace_molecule_is_undoable() -> None:
    document = Document()
    document.replace_molecule(ethane(), "Struktur setzen")
    assert len(document.molecule) == 2
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.is_empty()


def test_move_selection_is_undoable() -> None:
    document = Document(ethane())
    document.select_all()

    document.move_selection(Point2D(10.0, 5.0))

    assert document.molecule.atom(0).position.x == pytest.approx(-BOND_LENGTH / 2 + 10.0)
    document.undo_stack.undo()
    assert document.molecule.atom(0).position.x == pytest.approx(-BOND_LENGTH / 2)


def test_cycle_bond_order_wraps_around() -> None:
    document = Document(ethane())
    bond = document.molecule.bonds[0]

    assert document.cycle_bond_order(bond) == 2
    assert document.molecule.bonds[0].centered
    assert document.molecule.bonds[0].side == 0
    assert document.cycle_bond_order(document.molecule.bonds[0]) == 2
    assert not document.molecule.bonds[0].centered
    assert document.molecule.bonds[0].side == 1
    assert document.cycle_bond_order(document.molecule.bonds[0]) == 2
    assert document.molecule.bonds[0].side == -1
    assert document.cycle_bond_order(document.molecule.bonds[0]) == 3
    assert document.molecule.bonds[0].side == 0
    assert document.cycle_bond_order(document.molecule.bonds[0]) == 1

    assert document.undo_stack.count() == 5
    document.undo_stack.undo()
    assert document.molecule.bonds[0].order == 3


def test_set_atom_charge_is_undoable() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]

    document.set_atom_charge(atom_id, 2)

    assert document.molecule.atom(atom_id).charge == 2
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.molecule.atom(atom_id).charge == 0


def test_cycle_atom_charge_returns_the_new_charge() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]

    assert document.cycle_atom_charge(atom_id) == 1
    assert document.cycle_atom_charge(atom_id) == 2
    assert document.cycle_atom_charge(atom_id, -1) == -1
    assert document.cycle_atom_charge(atom_id, -1) == -2
    assert document.cycle_atom_charge(atom_id, -1) == -3

    assert document.undo_stack.count() == 5


def test_cycle_atom_charge_wraps_at_the_limit() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    document.set_atom_charge(atom_id, MAX_ATOM_CHARGE)

    assert document.cycle_atom_charge(atom_id) == 0


def test_modified_flag_follows_undo_stack() -> None:
    document = Document()
    assert not document.is_modified()

    with document.edit("Atom"):
        document.molecule.add_atom()
    assert document.is_modified()

    document.mark_saved()
    assert not document.is_modified()


def test_set_atom_label_is_undoable() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]

    document.set_atom_label(atom_id, "NO2")
    assert document.molecule.atom_label(atom_id) == "NO2"
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.molecule.atom_label(atom_id) == ""

    document.undo_stack.redo()
    assert document.molecule.atom_label(atom_id) == "NO2"

    document.set_atom_label(atom_id, "")
    assert document.molecule.atom_label(atom_id) == ""
    document.undo_stack.undo()
    assert document.molecule.atom_label(atom_id) == "NO2"


# -- Seite ---------------------------------------------------------------
def test_document_defaults_to_a4_portrait() -> None:
    document = Document()
    assert document.page.width_mm == 210.0
    assert document.page.height_mm == 297.0


def test_set_page_emits_signal_and_does_not_touch_undo() -> None:
    document = Document()
    changes: list[object] = []
    document.page_changed.connect(changes.append)

    document.set_page_format(PageFormat.LETTER)

    assert document.page.format is PageFormat.LETTER
    assert changes == [document.page]
    assert document.undo_stack.count() == 0


def test_setting_the_same_page_does_not_emit() -> None:
    document = Document()
    changes: list[object] = []
    document.page_changed.connect(changes.append)

    document.set_page(document.page)

    assert changes == []


def test_orientation_change_swaps_page_dimensions() -> None:
    document = Document()
    document.set_orientation(Orientation.LANDSCAPE)

    assert document.page.orientation is Orientation.LANDSCAPE
    assert document.page.width > document.page.height


def test_page_can_be_passed_to_constructor() -> None:
    page = Page(PageFormat.A3, Orientation.LANDSCAPE)
    document = Document(page=page)
    assert document.page == page
