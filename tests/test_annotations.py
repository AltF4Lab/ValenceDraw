from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind, ArrowObject, TextObject
from valencedraw.core.geometry import Point2D
from valencedraw.demo import ethane
from valencedraw.document.document import Document


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


# -- Text ----------------------------------------------------------------
def test_add_text_creates_undo_step() -> None:
    document = Document()
    obj = document.add_text(Point2D(10.0, 20.0), "H_2O")

    assert document.texts == (obj,)
    assert obj.position == Point2D(10.0, 20.0)
    assert document.undo_stack.count() == 1

    document.undo_stack.undo()
    assert document.texts == ()
    document.undo_stack.redo()
    assert document.texts == (obj,)


def test_replace_text_keeps_position() -> None:
    document = Document()
    original = document.add_text(Point2D(5.0, 5.0), "alt")

    updated = document.replace_text(original, "neu")

    assert document.texts == (updated,)
    assert updated.position == original.position
    assert updated.markup == "neu"

    document.undo_stack.undo()
    assert document.texts == (original,)


def test_remove_text_is_undoable() -> None:
    document = Document()
    obj = document.add_text(Point2D(0.0, 0.0), "Hallo")
    document.remove_text(obj)

    assert document.texts == ()
    document.undo_stack.undo()
    assert document.texts == (obj,)


def test_removing_unknown_text_is_noop() -> None:
    document = Document()
    document.remove_text(TextObject(Point2D(0.0, 0.0), "gibt es nicht"))
    assert document.undo_stack.count() == 0


# -- Pfeile --------------------------------------------------------------
def test_add_arrow_stores_kind_and_geometry() -> None:
    document = Document()
    arrow = document.add_arrow(Point2D(0.0, 0.0), Point2D(100.0, 0.0))

    assert document.arrows == (arrow,)
    assert arrow.kind is ArrowKind.FORWARD
    assert arrow.length == pytest.approx(100.0)
    assert arrow.midpoint == Point2D(50.0, 0.0)
    assert document.undo_stack.count() == 1


def test_equilibrium_arrow_is_supported() -> None:
    document = Document()
    arrow = document.add_arrow(
        Point2D(0.0, 0.0), Point2D(80.0, 0.0), ArrowKind.EQUILIBRIUM
    )
    assert document.arrows == (arrow,)
    assert arrow.kind is ArrowKind.EQUILIBRIUM


def test_remove_arrow_is_undoable() -> None:
    document = Document()
    arrow = document.add_arrow(Point2D(0.0, 0.0), Point2D(50.0, 0.0))
    document.remove_arrow(arrow)

    assert document.arrows == ()
    document.undo_stack.undo()
    assert document.arrows == (arrow,)


# -- Zustand / Snapshot --------------------------------------------------
def test_is_empty_considers_annotations() -> None:
    document = Document()
    assert document.is_empty()

    document.add_text(Point2D(0.0, 0.0), "x")
    assert not document.is_empty()
    document.undo_stack.undo()
    assert document.is_empty()


def test_state_contains_annotations() -> None:
    document = Document()
    text = document.add_text(Point2D(1.0, 2.0), "A")
    arrow = document.add_arrow(Point2D(0.0, 0.0), Point2D(10.0, 0.0))

    state = document.state()

    assert state.texts == (text,)
    assert state.arrows == (arrow,)
    assert state.molecule == document.molecule


def test_annotations_and_molecule_share_the_undo_stack() -> None:
    document = Document(ethane())
    document.select_only(document.molecule.atom_ids()[0])
    document.add_text(Point2D(0.0, 0.0), "Start")
    document.delete_selection()

    assert document.undo_stack.count() == 2

    document.undo_stack.undo()  # Löschen rückgängig
    assert len(document.molecule) == 2
    assert document.texts

    document.undo_stack.undo()  # Text rückgängig
    assert document.texts == ()


def test_replace_molecule_clears_annotations_by_default() -> None:
    document = Document(ethane())
    document.add_text(Point2D(0.0, 0.0), "Notiz")

    document.replace_molecule(ethane(), "Ersetzen")

    assert document.texts == ()
    assert document.arrows == ()
    document.undo_stack.undo()
    assert document.texts  # Undo holt den Text zurück


def test_replace_molecule_can_keep_annotations() -> None:
    document = Document(ethane())
    document.add_text(Point2D(0.0, 0.0), "Notiz")

    document.replace_molecule(ethane(), "Ersetzen", keep_annotations=True)

    assert len(document.texts) == 1


def test_arrow_object_normal_and_direction() -> None:
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(0.0, 100.0))
    assert arrow.direction == Point2D(0.0, 1.0)
    assert arrow.normal == Point2D(-1.0, 0.0)
    assert arrow.length == pytest.approx(100.0)
