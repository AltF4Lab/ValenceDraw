"""Integrationstests für den echten Qt-Ereignispfad von ``Canvas``."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QNativeGestureEvent, QPointingDevice, QWheelEvent
from PySide6.QtTest import QTest

from valencedraw.core.page import SCENE_UNITS_PER_MM, Orientation
from valencedraw.demo import ethane
from valencedraw.document.document import Document
from valencedraw.ui.canvas import Canvas
from valencedraw.ui.tools import AtomTool, BondTool, SelectTool


def _canvas(qapp):  # noqa: ANN001
    document = Document(ethane())
    view = Canvas(document)
    view.resize(600, 400)
    view.show()
    qapp.processEvents()
    view.centerOn(0.0, 0.0)
    return view


@pytest.fixture
def canvas(qapp):  # noqa: ANN001
    view = _canvas(qapp)
    yield view
    view.close()


def _bond_center(view: Canvas):
    return view.mapFromScene(QPointF(0.0, 0.0))


def _wheel(
    angle: QPoint,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    pixel: QPoint | None = None,
    position: QPointF | None = None,
) -> QWheelEvent:
    pos = position if position is not None else QPointF(0.0, 0.0)
    return QWheelEvent(
        pos,
        pos,
        pixel if pixel is not None else QPoint(0, 0),
        angle,
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def _native_pan(
    dx: float,
    dy: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QNativeGestureEvent:
    origin = QPointF(0.0, 0.0)
    event = QNativeGestureEvent(
        Qt.NativeGestureType.PanNativeGesture,
        QPointingDevice.primaryPointingDevice(),
        2,
        origin,
        origin,
        origin,
        0.0,
        QPointF(dx, dy),
    )
    event.setModifiers(modifiers)
    return event


def test_click_cycles_bond_order_with_select_tool(canvas) -> None:  # noqa: ANN001
    canvas.set_tool(SelectTool(canvas.document))
    point = _bond_center(canvas)

    expected = (
        (2, 0, True),
        (2, 1, False),
        (2, -1, False),
        (3, 0, False),
        (1, 0, False),
    )
    for expected_order, expected_side, expected_centered in expected:
        QTest.mouseClick(
            canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
        )
        bond = canvas.document.molecule.bonds[0]
        assert bond.order == expected_order
        assert bond.side == expected_side
        assert bond.centered is expected_centered


def test_click_cycles_bond_order_with_bond_tool(canvas) -> None:  # noqa: ANN001
    canvas.set_tool(BondTool(canvas.document))
    point = _bond_center(canvas)

    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )

    assert canvas.document.molecule.bonds[0].order == 2
    assert canvas.document.undo_stack.count() == 1


def test_click_on_bond_does_not_clear_selection(canvas) -> None:  # noqa: ANN001
    canvas.set_tool(SelectTool(canvas.document))
    atom_id = canvas.document.molecule.atom_ids()[0]
    canvas.document.select_only(atom_id)
    point = _bond_center(canvas)

    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )

    assert canvas.document.molecule.bonds[0].order == 2
    assert canvas.document.selection == frozenset({atom_id})


def test_click_on_empty_canvas_adds_bond(canvas) -> None:  # noqa: ANN001
    canvas.set_tool(BondTool(canvas.document))
    point = canvas.mapFromScene(QPointF(300.0, 200.0))

    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )

    # Ethan bleibt unverändert, auf freier Fläche entsteht eine neue Bindung.
    assert len(canvas.document.molecule) == 4
    assert canvas.document.molecule.bonds[0].order == 1
    assert len(canvas.document.molecule.bonds) == 2


def test_click_cycle_is_undoable_via_shortcut(canvas) -> None:  # noqa: ANN001
    canvas.set_tool(SelectTool(canvas.document))
    point = _bond_center(canvas)

    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )
    canvas.document.undo_stack.undo()

    assert canvas.document.molecule.bonds[0].order == 1


# -- Seite ---------------------------------------------------------------
def test_page_rect_is_centred_a4(canvas) -> None:  # noqa: ANN001
    rect = canvas.page_rect()

    assert rect.width() == pytest.approx(2100.0)
    assert rect.height() == pytest.approx(2970.0)
    assert rect.center() == QPointF(0.0, 0.0)


def test_page_rect_follows_orientation(canvas) -> None:  # noqa: ANN001
    canvas.document.set_orientation(Orientation.LANDSCAPE)

    rect = canvas.page_rect()

    assert rect.width() == pytest.approx(2970.0)
    assert rect.height() == pytest.approx(2100.0)


def test_fit_to_view_shows_the_whole_page(canvas) -> None:  # noqa: ANN001
    canvas.fit_to_view()
    page = canvas.page_rect()
    top_left = canvas.mapFromScene(page.topLeft())
    bottom_right = canvas.mapFromScene(page.bottomRight())
    viewport = canvas.viewport().rect()

    assert top_left.x() >= -1 and top_left.y() >= -1
    assert bottom_right.x() <= viewport.width() + 1
    assert bottom_right.y() <= viewport.height() + 1


def test_page_is_drawn_on_grey_workspace(qapp) -> None:  # noqa: ANN001
    view = Canvas(Document())
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.fit_to_view()
    qapp.processEvents()

    image = view.grab().toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    corner = image.pixelColor(2, 2)

    assert center.lightness() > 240
    assert corner.lightness() < 220
    view.close()


def test_scrollbar_policies(canvas) -> None:  # noqa: ANN001
    assert canvas.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert canvas.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOn


def test_scene_rect_follows_the_page(canvas) -> None:  # noqa: ANN001
    canvas.document.set_orientation(Orientation.LANDSCAPE)
    page = canvas.page_rect()

    assert canvas.sceneRect().width() == pytest.approx(page.width())
    assert canvas.sceneRect().height() == pytest.approx(page.height() + 2 * Canvas.PAGE_MARGIN)
    assert canvas.sceneRect().width() > canvas.sceneRect().height()


def test_scene_rect_has_margin_above_and_below_the_page(canvas) -> None:  # noqa: ANN001
    page = canvas.page_rect()
    rect = canvas.sceneRect()

    assert rect.top() == pytest.approx(page.top() - Canvas.PAGE_MARGIN)
    assert rect.bottom() == pytest.approx(page.bottom() + Canvas.PAGE_MARGIN)
    assert rect.left() == pytest.approx(page.left())
    assert rect.right() == pytest.approx(page.right())


def test_scene_rect_margin_is_7_5_mm(canvas) -> None:  # noqa: ANN001
    """Über dem Blatt bleiben 7,5 mm graue Arbeitsfläche (zuvor 15 mm)."""
    page = canvas.page_rect()
    assert page.top() - canvas.sceneRect().top() == pytest.approx(
        7.5 * SCENE_UNITS_PER_MM
    )


def test_scrolling_to_the_top_shows_the_margin(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(2.0)
    bar = canvas.verticalScrollBar()
    assert bar.maximum() > bar.minimum()

    bar.setValue(bar.minimum())

    # Über dem Blatt bleibt graue Arbeitsfläche sichtbar.
    assert canvas.mapFromScene(canvas.page_rect().topLeft()).y() > 1.0


def test_page_stays_centred_while_the_whole_page_is_visible(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    bar = canvas.horizontalScrollBar()
    assert bar.maximum() == bar.minimum()

    bar.setValue(bar.maximum())

    centre = canvas.mapFromScene(QPointF(0.0, 0.0))
    assert centre.x() == pytest.approx(canvas.viewport().width() / 2.0, abs=1.0)


def test_horizontal_scrolling_is_allowed_when_zoomed_into_the_page(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    assert bar.maximum() > bar.minimum()

    bar.setValue(bar.maximum())

    left = canvas.mapFromScene(canvas.page_rect().topLeft())
    right = canvas.mapFromScene(canvas.page_rect().topRight())
    assert left.x() < 0
    assert right.x() <= canvas.viewport().width() + 1


def test_horizontal_wheel_is_ignored_while_the_page_fits(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    bar = canvas.horizontalScrollBar()
    before = bar.value()

    canvas.wheelEvent(_wheel(QPoint(0, 0), pixel=QPoint(40, 0)))

    assert bar.value() == before


def test_fit_page_width_uses_full_width_and_allows_scrolling(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    page = canvas.page_rect()
    left = canvas.mapFromScene(page.topLeft())
    right = canvas.mapFromScene(page.topRight())
    bar = canvas.verticalScrollBar()

    assert left.x() >= 0
    assert right.x() <= canvas.viewport().width()
    assert right.x() - left.x() >= canvas.viewport().width() * 0.9
    assert bar.maximum() > bar.minimum()
    assert bar.minimum() <= bar.value() <= bar.maximum()


def test_vertical_scrolling_is_possible(canvas) -> None:  # noqa: ANN001
    canvas.zoom_by(3.0)
    bar = canvas.verticalScrollBar()
    assert bar.maximum() > bar.minimum()

    bar.setValue(bar.maximum())

    top_left = canvas.mapFromScene(canvas.page_rect().topLeft())
    assert top_left.y() < 0


def test_click_outside_the_page_does_not_draw(canvas) -> None:  # noqa: ANN001
    canvas.fit_to_view()
    canvas.set_tool(AtomTool(canvas.document))
    before = len(canvas.document.molecule)

    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(3, canvas.viewport().height() // 2),
    )

    assert len(canvas.document.molecule) == before


def test_click_inside_the_page_draws(canvas) -> None:  # noqa: ANN001
    canvas.fit_to_view()
    canvas.set_tool(AtomTool(canvas.document))
    before = len(canvas.document.molecule)
    point = canvas.mapFromScene(QPointF(250.0, 250.0))

    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )

    assert len(canvas.document.molecule) == before + 1
    new_atom = canvas.document.molecule.atom(canvas.document.molecule.atom_ids()[-1])
    assert canvas.document.page.bounds[0].x <= new_atom.position.x <= canvas.document.page.bounds[1].x


# -- Mausrad / Touchpad ---------------------------------------------------
def test_wheel_scrolls_vertically_instead_of_zooming(canvas) -> None:  # noqa: ANN001
    canvas.zoom_by(3.0)
    bar = canvas.verticalScrollBar()
    bar.setValue(bar.minimum())
    zoom = canvas.zoom_level()

    canvas.wheelEvent(_wheel(QPoint(0, -120)))

    assert bar.value() > bar.minimum()
    assert canvas.zoom_level() == pytest.approx(zoom)


def test_touchpad_pixel_delta_scrolls_vertically(canvas) -> None:  # noqa: ANN001
    canvas.zoom_by(3.0)
    bar = canvas.verticalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    canvas.wheelEvent(_wheel(QPoint(0, 0), pixel=QPoint(0, 40)))

    assert bar.value() == before - 40


def test_ctrl_wheel_zooms(canvas) -> None:  # noqa: ANN001
    canvas.fit_to_view()
    zoom = canvas.zoom_level()

    canvas.wheelEvent(_wheel(QPoint(0, 120), Qt.KeyboardModifier.ControlModifier))

    assert canvas.zoom_level() > zoom


def test_ctrl_wheel_zooms_under_the_mouse(canvas) -> None:  # noqa: ANN001
    """Der Punkt unter dem Mauszeiger bleibt beim Zoomen stehen."""
    canvas.fit_page_width()
    anchor = QPointF(
        canvas.viewport().width() * 0.7,
        canvas.viewport().height() * 0.6,
    )
    scene_point = canvas.mapToScene(anchor.toPoint())

    canvas.wheelEvent(
        _wheel(
            QPoint(0, 120),
            Qt.KeyboardModifier.ControlModifier,
            position=anchor,
        )
    )

    mapped = canvas.mapFromScene(scene_point)
    assert mapped.x() == pytest.approx(anchor.x(), abs=1.5)
    assert mapped.y() == pytest.approx(anchor.y(), abs=1.5)


def test_zoom_in_keeps_the_view_center(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    center = QPointF(canvas.viewport().rect().center())
    scene_point = canvas.mapToScene(center.toPoint())

    canvas.zoom_in()

    mapped = canvas.mapFromScene(scene_point)
    assert mapped.x() == pytest.approx(center.x(), abs=1.5)
    assert mapped.y() == pytest.approx(center.y(), abs=1.5)


def test_horizontal_wheel_scrolls_when_zoomed_into_the_page(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    canvas.wheelEvent(_wheel(QPoint(0, 0), pixel=QPoint(40, 0)))

    assert bar.value() == before - 40


def test_shift_wheel_scrolls_horizontally_when_zoomed_into_the_page(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    canvas.wheelEvent(_wheel(QPoint(0, -120), Qt.KeyboardModifier.ShiftModifier))

    assert bar.value() == before + 60


def test_shift_does_not_swallow_horizontal_touchpad_deltas(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    canvas.wheelEvent(
        _wheel(QPoint(0, 0), Qt.KeyboardModifier.ShiftModifier, pixel=QPoint(40, 0))
    )

    assert bar.value() == before - 40


def test_tiny_wheel_delta_is_not_lost(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    bar = canvas.verticalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    canvas.wheelEvent(_wheel(QPoint(0, 1)))

    assert bar.value() == before - 1


def test_horizontal_wheel_reaches_canvas_through_viewport(canvas, qapp) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    qapp.sendEvent(canvas.viewport(), _wheel(QPoint(0, 0), pixel=QPoint(40, 0)))

    assert bar.value() == before - 40


def test_shift_wheel_reaches_canvas_through_viewport(canvas, qapp) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    bar = canvas.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()

    qapp.sendEvent(
        canvas.viewport(),
        _wheel(QPoint(0, -120), Qt.KeyboardModifier.ShiftModifier),
    )

    assert bar.value() == before + 60


def test_mixed_pixel_and_angle_deltas_scroll_both_axes(canvas) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    hbar = canvas.horizontalScrollBar()
    vbar = canvas.verticalScrollBar()
    hbar.setValue((hbar.minimum() + hbar.maximum()) // 2)
    vbar.setValue((vbar.minimum() + vbar.maximum()) // 2)
    h_before, v_before = hbar.value(), vbar.value()

    # Treiber meldet die horizontale Bewegung nur als angleDelta.x.
    canvas.wheelEvent(_wheel(QPoint(-120, 0), pixel=QPoint(0, 5)))

    assert hbar.value() == h_before + 60
    assert vbar.value() == v_before - 5


def test_native_two_finger_pan_scrolls_both_axes(canvas, qapp) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    hbar = canvas.horizontalScrollBar()
    vbar = canvas.verticalScrollBar()
    hbar.setValue((hbar.minimum() + hbar.maximum()) // 2)
    vbar.setValue((vbar.minimum() + vbar.maximum()) // 2)
    h_before, v_before = hbar.value(), vbar.value()

    qapp.sendEvent(canvas.viewport(), _native_pan(40.0, 10.0))

    assert hbar.value() == h_before - 40
    assert vbar.value() == v_before - 10


def test_shift_vertical_native_pan_scrolls_horizontally(canvas, qapp) -> None:  # noqa: ANN001
    canvas.fit_page_width()
    canvas.zoom_by(3.0)
    hbar = canvas.horizontalScrollBar()
    vbar = canvas.verticalScrollBar()
    hbar.setValue((hbar.minimum() + hbar.maximum()) // 2)
    vbar.setValue((vbar.minimum() + vbar.maximum()) // 2)
    h_before, v_before = hbar.value(), vbar.value()

    qapp.sendEvent(
        canvas.viewport(),
        _native_pan(0.0, 40.0, Qt.KeyboardModifier.ShiftModifier),
    )

    assert hbar.value() == h_before - 40
    assert vbar.value() == v_before
