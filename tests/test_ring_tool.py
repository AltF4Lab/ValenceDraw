from __future__ import annotations

import pytest

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.templates import (
    BENZENE,
    CYCLOHEXANE,
    CYCLOPENTANE,
    RING_TEMPLATES,
    RingTemplate,
)
from valencedraw.demo import ethane
from valencedraw.document.document import Document
from valencedraw.ui.tools import RingTool
from qt_helpers import move as _move
from qt_helpers import press as _press


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _edge_lengths(vertices: list[Point2D]) -> list[float]:
    return [
        vertices[index].distance_to(vertices[(index + 1) % len(vertices)])
        for index in range(len(vertices))
    ]


# -- Templates -----------------------------------------------------------
def test_templates_produce_equal_edge_lengths() -> None:
    for template in RING_TEMPLATES:
        vertices = template.vertices(Point2D(10.0, 20.0))
        assert len(vertices) == template.size
        for length in _edge_lengths(vertices):
            assert length == pytest.approx(BOND_LENGTH)


def test_benzene_circumradius_equals_bond_length() -> None:
    assert BENZENE.circumradius == pytest.approx(BOND_LENGTH)
    assert CYCLOHEXANE.circumradius == pytest.approx(BOND_LENGTH)


def test_vertices_are_centered_around_center() -> None:
    center = Point2D(100.0, -50.0)
    vertices = BENZENE.vertices(center)
    average = Point2D(
        sum(vertex.x for vertex in vertices) / len(vertices),
        sum(vertex.y for vertex in vertices) / len(vertices),
    )
    assert average.x == pytest.approx(center.x)
    assert average.y == pytest.approx(center.y)


def test_template_validates_size_and_orders() -> None:
    with pytest.raises(ValueError):
        RingTemplate("Zu klein", 2, (1, 1))
    with pytest.raises(ValueError):
        RingTemplate("Falsche Ordnungen", 6, (1, 1, 1))


# -- RingTool ------------------------------------------------------------
def test_ring_tool_inserts_benzene() -> None:
    document = Document()
    tool = RingTool(document)

    assert tool.mouse_press(Point2D(0.0, 0.0), _press())

    assert len(document.molecule) == 6
    assert len(document.molecule.bonds) == 6
    assert sum(1 for bond in document.molecule.bonds if bond.order == 2) == 3
    for bond in document.molecule.bonds:
        start = document.molecule.atom(bond.a).position
        end = document.molecule.atom(bond.b).position
        assert start.distance_to(end) == pytest.approx(BOND_LENGTH)

    assert document.undo_stack.count() == 1
    document.undo_stack.undo()
    assert document.is_empty()


def test_ring_tool_inserts_cyclopentane() -> None:
    document = Document()
    tool = RingTool(document, template=CYCLOPENTANE)

    tool.mouse_press(Point2D(0.0, 0.0), _press())

    assert len(document.molecule) == 5
    assert len(document.molecule.bonds) == 5
    assert all(bond.order == 1 for bond in document.molecule.bonds)


def test_ring_tool_attaches_to_existing_atom() -> None:
    document = Document(ethane())
    tool = RingTool(document)
    anchor = document.molecule.atom_ids()[0]
    anchor_position = document.molecule.atom(anchor).position

    tool.mouse_press(anchor_position, _press())

    # 6 Ringatome, eines davon ist das vorhandene Ankeratom
    assert len(document.molecule) == 7
    assert len(document.molecule.bonds) == 7
    # alte Bindung + zwei Ringbindungen
    assert document.molecule.degree(anchor) == 3

    assert document.undo_stack.count() == 1
    document.undo_stack.undo()
    assert len(document.molecule) == 2
    assert document.molecule.atom(anchor).position == anchor_position


def test_ring_tool_preview_matches_placement() -> None:
    document = Document()
    tool = RingTool(document)

    tool.mouse_move(Point2D(0.0, 0.0), _move())
    assert len(tool.placement(Point2D(0.0, 0.0))) == BENZENE.size
    assert document.is_empty()


def test_ring_tool_second_clicks_are_undoable_step_by_step() -> None:
    document = Document()
    tool = RingTool(document, template=CYCLOHEXANE)

    tool.mouse_press(Point2D(-200.0, 0.0), _press())
    tool.mouse_press(Point2D(200.0, 0.0), _press())

    assert len(document.molecule) == 12
    assert document.undo_stack.count() == 2

    document.undo_stack.undo()
    assert len(document.molecule) == 6
    document.undo_stack.undo()
    assert document.is_empty()
