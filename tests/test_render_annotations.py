from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind, ArrowObject, TextObject
from valencedraw.core.geometry import Point2D, distance_to_segment
from valencedraw.demo import ethane
from valencedraw.render.export import content_bounds, render_image, save_png, save_svg
from valencedraw.render.painter import (
    arrow_head_polygon,
    arrow_heads,
    arrow_shafts,
    flow_arrow_head,
    radical_barb,
    text_bounds,
    text_size,
)
from valencedraw.render.style import DEFAULT_STYLE


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _dark_pixels(image, step: int = 3) -> int:
    return sum(
        1
        for x in range(0, image.width(), step)
        for y in range(0, image.height(), step)
        if image.pixelColor(x, y).lightness() < 120
    )


def test_text_size_is_positive() -> None:
    size = text_size("H_2O")
    assert size.width() > 0
    assert size.height() > 0


def test_text_bounds_use_position() -> None:
    obj = TextObject(Point2D(10.0, 20.0), "Probe")
    bounds = text_bounds(obj)
    assert bounds.topLeft().x() == pytest.approx(10.0)
    assert bounds.topLeft().y() == pytest.approx(20.0)
    assert bounds.width() > 0


def test_content_bounds_include_annotations() -> None:
    texts = (TextObject(Point2D(500.0, 500.0), "weit weg"),)
    bounds = content_bounds(None, texts=texts)
    assert bounds.right() > 500.0
    assert bounds.bottom() > 500.0


def test_render_text_only() -> None:
    """Text muss ohne Molekül und ohne Pfeile sichtbar sein."""
    texts = (TextObject(Point2D(0.0, 0.0), "Fe^{3+}"),)

    image = render_image(None, width=200, height=100, texts=texts)

    assert _dark_pixels(image, step=1) > 0


def test_render_text_and_arrows_without_molecule() -> None:
    texts = (TextObject(Point2D(0.0, 0.0), "Fe^{3+} + e^{-}"),)
    arrows = (ArrowObject(Point2D(0.0, 80.0), Point2D(150.0, 80.0), ArrowKind.EQUILIBRIUM),)

    image = render_image(None, width=300, height=200, texts=texts, arrows=arrows)

    assert not image.isNull()
    assert _dark_pixels(image) > 0


def test_render_scene_with_annotations() -> None:
    texts = (TextObject(Point2D(-120.0, -90.0), "H_{2}O"),)
    arrows = (ArrowObject(Point2D(-60.0, 60.0), Point2D(60.0, 60.0)),)

    image = render_image(ethane(), width=400, height=300, texts=texts, arrows=arrows)

    assert _dark_pixels(image) > 0


def test_export_with_annotations(tmp_path) -> None:  # noqa: ANN001
    texts = (TextObject(Point2D(0.0, -80.0), "SO_4^{2-}"),)
    arrows = (ArrowObject(Point2D(-50.0, 40.0), Point2D(50.0, 40.0), ArrowKind.FORWARD),)

    png = save_png(ethane(), tmp_path / "szene.png", 300, 200, texts=texts, arrows=arrows)
    svg = save_svg(ethane(), tmp_path / "szene.svg", 300, 200, texts=texts, arrows=arrows)

    assert png.stat().st_size > 0
    content = svg.read_text(encoding="utf-8")
    assert "<svg" in content
    # Superscript wird als SVG-Text mit `tspan`-Baseline exportiert
    assert "tspan" in content or "text" in content


# -- Pfeilspitzen ---------------------------------------------------------
def test_forward_arrow_has_exactly_one_head_at_the_end() -> None:
    arrow = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.FORWARD)

    heads = arrow_heads(arrow)

    assert len(heads) == 1
    tip, direction = heads[0]
    assert tip == Point2D(100.0, 0.0)
    assert direction == Point2D(1.0, 0.0)


def test_equilibrium_heads_sit_only_on_the_outer_ends() -> None:
    arrow = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.EQUILIBRIUM)

    heads = arrow_heads(arrow)

    assert len(heads) == 2
    tips = [tip for tip, _direction in heads]
    assert {tip.x for tip in tips} == {-100.0, 100.0}
    assert {tuple(direction) for _tip, direction in heads} == {(1.0, 0.0), (-1.0, 0.0)}
    # obere Linie zeigt nach rechts, untere nach links
    top = min(tips, key=lambda tip: tip.y)
    bottom = max(tips, key=lambda tip: tip.y)
    assert top.x == 100.0
    assert bottom.x == -100.0


def test_right_to_left_equilibrium_is_normalized_to_the_standard_symbol() -> None:
    arrow = ArrowObject(Point2D(100.0, 0.0), Point2D(-100.0, 0.0), ArrowKind.EQUILIBRIUM)

    heads = arrow_heads(arrow)

    tips = [tip for tip, _direction in heads]
    top = min(tips, key=lambda tip: tip.y)
    bottom = max(tips, key=lambda tip: tip.y)
    assert top.x == 100.0
    assert bottom.x == -100.0


def test_equilibrium_has_two_parallel_shifted_shafts() -> None:
    arrow = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.EQUILIBRIUM)

    shafts = arrow_shafts(arrow)

    assert len(shafts) == 2
    (top_start, top_end), (bottom_start, bottom_end) = shafts
    overlap = DEFAULT_STYLE.arrow_head_length * DEFAULT_STYLE.equilibrium_head_scale
    assert top_start.x == pytest.approx(-100.0)
    assert top_end.x == pytest.approx(100.0 - overlap)
    assert bottom_start.x == pytest.approx(100.0)
    assert bottom_end.x == pytest.approx(-100.0 + overlap)
    # Der Abstand der beiden Linien ist der Symbolabstand (nicht der doppelte).
    assert abs(top_start.y - bottom_start.y) == pytest.approx(DEFAULT_STYLE.arrow_gap)
    assert abs(bottom_start.y - bottom_end.y) == pytest.approx(0.0)


def test_equilibrium_head_is_a_one_sided_half_head() -> None:
    """⇌ besteht aus zwei halben Spitzen, nicht aus zwei vollen Dreiecken."""
    arrow = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.EQUILIBRIUM)
    up = Point2D(0.0, -1.0)

    (top_tip, top_direction), (bottom_tip, bottom_direction) = arrow_heads(arrow)
    top_head = arrow_head_polygon(
        top_tip, top_direction, DEFAULT_STYLE, DEFAULT_STYLE.equilibrium_head_scale, up
    )
    bottom_head = arrow_head_polygon(
        bottom_tip,
        bottom_direction,
        DEFAULT_STYLE,
        DEFAULT_STYLE.equilibrium_head_scale,
        -up,
    )

    def points(polygon) -> list[tuple[float, float]]:  # noqa: ANN001
        return [(point.x(), point.y()) for point in polygon]

    top = points(top_head)
    bottom = points(bottom_head)
    assert len(top) == 3
    # Die flache Seite liegt bündig auf der Innenkante der Linie, der
    # Widerhaken steht nach außen ab; die Spitze sitzt auf der Linienmitte.
    inner_offset = DEFAULT_STYLE.bond_width / 2.0
    assert max(y for _x, y in top) == pytest.approx(top_tip.y + inner_offset)
    assert min(y for _x, y in top) < top_tip.y
    assert min(y for _x, y in bottom) == pytest.approx(bottom_tip.y - inner_offset)
    assert max(y for _x, y in bottom) > bottom_tip.y


def test_equilibrium_heads_are_smaller_than_forward_heads() -> None:
    equilibrium = ArrowObject(
        Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.EQUILIBRIUM
    )
    forward = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.FORWARD)

    eq_tip, eq_direction = arrow_heads(equilibrium)[0]
    fw_tip, fw_direction = arrow_heads(forward)[0]
    eq_head = arrow_head_polygon(
        eq_tip, eq_direction, DEFAULT_STYLE, DEFAULT_STYLE.equilibrium_head_scale
    ).boundingRect()
    fw_head = arrow_head_polygon(fw_tip, fw_direction, DEFAULT_STYLE).boundingRect()

    assert eq_head.height() < fw_head.height()
    assert eq_head.width() < fw_head.width()


def test_forward_shaft_stops_inside_the_head() -> None:
    arrow = ArrowObject(Point2D(-100.0, 0.0), Point2D(100.0, 0.0), ArrowKind.FORWARD)

    (start, end), = arrow_shafts(arrow)

    assert start == Point2D(-100.0, 0.0)
    assert end.x == pytest.approx(
        100.0 - DEFAULT_STYLE.arrow_head_length * 0.85
    )


def test_arrow_head_is_a_pointed_filled_triangle() -> None:
    polygon = arrow_head_polygon(Point2D(100.0, 0.0), Point2D(1.0, 0.0))

    assert polygon.count() == 3
    xs = [polygon.at(index).x() for index in range(3)]
    ys = [polygon.at(index).y() for index in range(3)]
    assert max(xs) == pytest.approx(100.0)
    assert min(xs) == pytest.approx(100.0 - DEFAULT_STYLE.arrow_head_length)
    assert max(ys) - min(ys) == pytest.approx(DEFAULT_STYLE.arrow_head_width)


def test_arrow_kinds_cover_reactions_and_electron_flow() -> None:
    assert set(ArrowKind) == {
        ArrowKind.FORWARD,
        ArrowKind.EQUILIBRIUM,
        ArrowKind.PAIR_FLOW,
        ArrowKind.RADICAL_FLOW,
    }


def test_flow_arrow_is_curved_upwards() -> None:
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.3)

    points = arrow.points()

    assert points[0] == arrow.start
    assert points[-1] == arrow.end
    assert min(point.y for point in points) < -20.0
    assert arrow.is_flow is True
    # Die Spitze folgt der Kurve (kommt von oben ins Ziel), nicht der Geraden.
    assert arrow.end_direction != arrow.direction
    assert arrow.end_direction.y > 0.0


def test_flow_arrow_runs_on_a_circle() -> None:
    """Der gebogene Pfeil ist ein echter Kreisbogen mit konstantem Radius."""
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.3)
    arc = arrow.arc

    assert arc is not None
    for point in arrow.points(samples=48):
        assert point.distance_to(arc.center) == pytest.approx(arc.radius, abs=1e-6)
    # Die Tangente am Ende ist die Kreistangente.
    tangent = arc.tangent(1.0)
    assert arrow.end_direction.x == pytest.approx(tangent.x)
    assert arrow.end_direction.y == pytest.approx(tangent.y)


def test_flow_arrow_head_sits_on_the_curve() -> None:
    """Die Spitzenbasis liegt auf dem Bogen, nicht auf der Sehne."""
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.3)
    arc = arrow.arc
    assert arc is not None

    head = flow_arrow_head(arrow)
    tip = head.at(0)
    base_left = head.at(1)
    base_right = head.at(2)
    assert (tip.x(), tip.y()) == pytest.approx((200.0, 0.0))

    base_mid = Point2D(
        (base_left.x() + base_right.x()) / 2.0,
        (base_left.y() + base_right.y()) / 2.0,
    )
    expected = arc.point_from_end(DEFAULT_STYLE.arrow_head_length)
    assert base_mid.x == pytest.approx(expected.x)
    assert base_mid.y == pytest.approx(expected.y)
    # Die beiden Widerhaken sind gleich weit von der Bogenbasis entfernt.
    left = Point2D(base_left.x(), base_left.y())
    right = Point2D(base_right.x(), base_right.y())
    assert left.distance_to(base_mid) == pytest.approx(right.distance_to(base_mid))


def test_radical_flow_head_is_a_half_head_on_the_outside() -> None:
    arrow = ArrowObject(
        Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.RADICAL_FLOW, 0.3
    )
    arc = arrow.arc
    assert arc is not None

    barb = radical_barb(arrow)
    tip = arrow.end
    tangent = arrow.end_direction
    # Der Widerhaken beginnt exakt an der Spitze und läuft nach hinten …
    assert tip.distance_to(barb) > 0.0
    assert (tip - barb).x * tangent.x + (tip - barb).y * tangent.y > 0.0
    # … und steht auf der Außenseite der Krümmung.
    assert barb.distance_to(arc.center) > arc.radius


def test_straight_arrow_has_a_two_point_outline() -> None:
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(100.0, 0.0))

    assert arrow.points() == (arrow.start, arrow.end)
    assert arrow.is_flow is False
    assert arrow.end_direction == arrow.direction


def test_bow_along_shifts_the_apex_along_the_arrow() -> None:
    arrow = ArrowObject(
        Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.3, 0.4
    )

    points = arrow.points(samples=200)
    far_right = max(points, key=lambda point: point.x)
    highest = min(points, key=lambda point: point.y)

    assert arrow.control.x == pytest.approx(100.0 + 200.0 * 0.4)
    assert arrow.curve_midpoint.x == pytest.approx(140.0)
    assert arrow.curve_midpoint.y == pytest.approx(-30.0)
    # Der Greifpunkt liegt auf der gezeichneten Kurve …
    distance = min(
        distance_to_segment(arrow.curve_midpoint, start, end)
        for start, end in zip(points, points[1:])
    )
    assert distance == pytest.approx(0.0, abs=1e-6)
    # … und bildet jetzt den höchsten Punkt (asymmetrische Wölbung).
    assert highest.x == pytest.approx(140.0, abs=0.5)
    assert highest.y == pytest.approx(-30.0, abs=0.1)
    # Zwei unterschiedliche Kreisbögen links und rechts des Scheitels.
    arcs = arrow.arcs
    assert len(arcs) == 2
    assert arrow.arc is None
    assert arcs[0].radius != pytest.approx(arcs[1].radius)
    assert far_right.x == pytest.approx(200.0)


def test_arrow_extent_covers_the_curve() -> None:
    arrow = ArrowObject(Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.3)

    low, high = arrow.extent()

    assert low.y < -20.0
    assert low.x == pytest.approx(0.0)
    assert high.x == pytest.approx(200.0)


def test_straight_flow_arrow_with_bow_along_has_no_arc() -> None:
    """Ohne Wölbung bleibt der Weg gerade – auch wenn der Scheitel verschoben ist."""
    arrow = ArrowObject(
        Point2D(0.0, 0.0), Point2D(200.0, 0.0), ArrowKind.PAIR_FLOW, 0.0, 0.4
    )

    assert arrow.arc is None
    assert arrow.points() == (arrow.start, arrow.end)
