"""Auswahl und Verschieben von Texten und Pfeilen (Dokument-Ebene)."""

from __future__ import annotations

import pytest

from valencedraw.core.geometry import Point2D
from valencedraw.demo import ethane
from valencedraw.document.document import Document


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    """QUndoStack braucht eine QApplication-Instanz."""
    yield


def _document_with_objects() -> Document:
    document = Document(ethane())
    document.add_text(Point2D(100.0, 100.0), "Ph")
    document.add_arrow(Point2D(0.0, 200.0), Point2D(120.0, 200.0))
    document.undo_stack.clear()
    return document


def test_select_text_clears_other_selection() -> None:
    document = _document_with_objects()
    document.select_all()

    document.select_text(0)

    assert document.text_selection == frozenset({0})
    assert document.selection == frozenset()
    assert document.arrow_selection == frozenset()
    assert document.selected_texts == (document.texts[0],)


def test_select_arrow_clears_other_selection() -> None:
    document = _document_with_objects()

    document.select_arrow(0)

    assert document.arrow_selection == frozenset({0})
    assert document.text_selection == frozenset()
    assert document.selected_arrows == (document.arrows[0],)


def test_select_text_additive_toggles() -> None:
    document = _document_with_objects()

    document.select_text(0, additive=True)
    assert document.is_text_selected(0)

    document.select_text(0, additive=True)
    assert not document.is_text_selected(0)


def test_select_all_includes_texts_and_arrows() -> None:
    document = _document_with_objects()

    document.select_all()

    assert document.selection == frozenset(document.molecule.atom_ids())
    assert document.text_selection == frozenset({0})
    assert document.arrow_selection == frozenset({0})


def test_move_selection_moves_atoms_texts_and_arrows() -> None:
    document = _document_with_objects()
    text_before = document.texts[0]
    arrow_before = document.arrows[0]
    atom_before = document.molecule.atom(0).position
    document.select_all()

    document.move_selection(Point2D(10.0, 5.0))

    assert document.texts[0].position == text_before.position + Point2D(10.0, 5.0)
    assert document.arrows[0].start == arrow_before.start + Point2D(10.0, 5.0)
    assert document.arrows[0].end == arrow_before.end + Point2D(10.0, 5.0)
    assert document.molecule.atom(0).position == atom_before + Point2D(10.0, 5.0)
    assert document.undo_stack.count() == 1


def test_move_selection_is_undoable() -> None:
    document = _document_with_objects()
    text_before = document.texts[0]
    document.select_text(0)

    document.move_selection(Point2D(20.0, 0.0))
    document.undo_stack.undo()

    assert document.texts[0] == text_before


def test_delete_selection_removes_texts_and_arrows() -> None:
    document = _document_with_objects()
    document.select_all()

    document.delete_selection()

    assert document.texts == ()
    assert document.arrows == ()
    assert len(document.molecule) == 0
    assert not document.has_selection()
    assert document.undo_stack.canUndo()
