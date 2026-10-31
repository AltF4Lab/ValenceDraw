"""Tests für Kopieren/Einfügen (Zwischenablage)."""

from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind
from valencedraw.core.geometry import Point2D
from valencedraw.demo import ethane
from valencedraw.document.clipboard import Fragment, fragment_from_json, fragment_to_json
from valencedraw.document.document import Document
from valencedraw.document.project import ProjectError


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    """QUndoStack braucht eine QApplication-Instanz."""
    yield


def test_copy_selection_copies_atoms_and_bonds() -> None:
    document = Document(ethane())
    document.select_all()

    fragment = document.copy_selection()

    assert len(fragment.molecule) == 2
    assert len(fragment.molecule.bonds) == 1


def test_copy_single_atom_has_no_bond() -> None:
    document = Document(ethane())
    document.select_only(0)

    fragment = document.copy_selection()

    assert len(fragment.molecule) == 1
    assert fragment.molecule.bonds == ()


def test_copy_selection_includes_texts_and_arrows() -> None:
    document = Document(ethane())
    document.add_text(Point2D(10.0, 20.0), "Ph")
    document.add_arrow(
        Point2D(0.0, 100.0), Point2D(80.0, 100.0), ArrowKind.EQUILIBRIUM
    )
    document.select_all()

    fragment = document.copy_selection()

    assert [obj.markup for obj in fragment.texts] == ["Ph"]
    assert [arrow.kind for arrow in fragment.arrows] == [ArrowKind.EQUILIBRIUM]


def test_copy_and_paste_keep_double_bond_side() -> None:
    document = Document(ethane())
    document.molecule.set_bond_order(document.molecule.bonds[0], 2, side=-1)
    document.select_all()

    fragment = document.copy_selection()
    assert fragment.molecule.bonds[0].side == -1

    target = Document()
    target.paste_fragment(fragment)
    assert target.molecule.bonds[0].side == -1


def test_copy_and_paste_keep_centered_double_bond() -> None:
    document = Document(ethane())
    document.molecule.set_bond_order(document.molecule.bonds[0], 2, centered=True)
    document.select_all()

    fragment = document.copy_selection()
    assert fragment.molecule.bonds[0].centered

    target = Document()
    target.paste_fragment(fragment)
    assert target.molecule.bonds[0].centered


def test_copy_keeps_atom_labels_and_charge() -> None:
    document = Document()
    atom_id = document.molecule.add_atom("O", Point2D(0.0, 0.0), charge=-1)
    document.set_atom_label(atom_id, "OTs")
    document.select_only(atom_id)

    fragment = document.copy_selection()

    copied = fragment.molecule.atom(0)
    assert copied.element == "O"
    assert copied.charge == -1
    assert copied.label == "OTs"


def test_paste_fragment_adds_offset_copies_and_selects_them() -> None:
    document = Document(ethane())
    document.select_all()
    fragment = document.copy_selection()

    assert document.paste_fragment(fragment, Point2D(20.0, 20.0))

    assert len(document.molecule) == 4
    assert len(document.molecule.bonds) == 2
    assert document.selection == frozenset({2, 3})
    positions = {document.molecule.atom(atom_id).position for atom_id in (2, 3)}
    assert positions == {Point2D(0.0, 20.0), Point2D(40.0, 20.0)}


def test_paste_fragment_is_undoable() -> None:
    document = Document(ethane())
    document.select_all()
    fragment = document.copy_selection()
    document.paste_fragment(fragment, Point2D(20.0, 20.0))

    document.undo_stack.undo()

    assert len(document.molecule) == 2
    assert len(document.molecule.bonds) == 1


def test_paste_copies_texts_and_arrows() -> None:
    document = Document(ethane())
    document.add_text(Point2D(10.0, 20.0), "Ph")
    document.add_arrow(Point2D(0.0, 100.0), Point2D(80.0, 100.0))
    document.select_all()
    fragment = document.copy_selection()

    document.paste_fragment(fragment, Point2D(10.0, 10.0))

    assert [obj.markup for obj in document.texts] == ["Ph", "Ph"]
    assert document.texts[1].position == Point2D(20.0, 30.0)
    assert len(document.arrows) == 2
    assert document.arrows[1].start == Point2D(10.0, 110.0)
    assert document.text_selection == frozenset({1})
    assert document.arrow_selection == frozenset({1})


def test_paste_empty_fragment_does_nothing() -> None:
    document = Document(ethane())

    assert document.paste_fragment(Fragment()) is False
    assert len(document.molecule) == 2
    assert document.undo_stack.count() == 0


def test_fragment_json_roundtrip() -> None:
    document = Document(ethane())
    document.add_text(Point2D(1.0, 2.0), "H_2O")
    document.add_arrow(Point2D(0.0, 5.0), Point2D(50.0, 5.0))
    document.select_all()
    fragment = document.copy_selection()

    assert fragment_from_json(fragment_to_json(fragment)) == fragment


def test_invalid_fragment_json_raises() -> None:
    with pytest.raises(ProjectError):
        fragment_from_json("kein json")
