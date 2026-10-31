from __future__ import annotations

import math

import pytest

from valencedraw.core.geometry import (
    BOND_LENGTH,
    Point2D,
    angle_between,
    bounding_box,
    distance_to_segment,
    polar,
    snap_to_grid_angle,
)


def test_point_arithmetic() -> None:
    a = Point2D(3.0, 4.0)
    b = Point2D(1.0, 2.0)

    assert a + b == Point2D(4.0, 6.0)
    assert a - b == Point2D(2.0, 2.0)
    assert a * 2 == Point2D(6.0, 8.0)
    assert 2 * a == Point2D(6.0, 8.0)
    assert a / 2 == Point2D(1.5, 2.0)
    assert -a == Point2D(-3.0, -4.0)
    assert a.length == pytest.approx(5.0)


def test_point_normalize_and_distance() -> None:
    assert Point2D(0.0, 0.0).normalized() == Point2D(0.0, 0.0)
    assert Point2D(3.0, 4.0).normalized().length == pytest.approx(1.0)
    assert Point2D(0.0, 0.0).distance_to(Point2D(3.0, 4.0)) == pytest.approx(5.0)


def test_point_rotation() -> None:
    rotated = Point2D(10.0, 0.0).rotated(90.0)
    assert rotated.x == pytest.approx(0.0, abs=1e-9)
    assert rotated.y == pytest.approx(10.0)


def test_polar() -> None:
    point = polar(Point2D(5.0, 5.0), 0.0, 10.0)
    assert point.x == pytest.approx(15.0)
    assert point.y == pytest.approx(5.0)


def test_snap_to_grid_angle_snaps_to_horizontal() -> None:
    snapped = snap_to_grid_angle(Point2D(), Point2D(100.0, 4.0), length=BOND_LENGTH)
    assert snapped.x == pytest.approx(BOND_LENGTH)
    assert snapped.y == pytest.approx(0.0, abs=1e-9)


def test_snap_to_grid_angle_snaps_to_diagonal() -> None:
    snapped = snap_to_grid_angle(Point2D(), Point2D(100.0, 95.0), length=BOND_LENGTH)
    expected = BOND_LENGTH / math.sqrt(2.0)
    assert snapped.x == pytest.approx(expected)
    assert snapped.y == pytest.approx(expected)


def test_snap_to_grid_angle_keeps_length() -> None:
    snapped = snap_to_grid_angle(Point2D(10.0, 10.0), Point2D(30.0, 10.0))
    assert snapped.distance_to(Point2D(10.0, 10.0)) == pytest.approx(20.0)


def test_distance_to_segment() -> None:
    start, end = Point2D(0.0, 0.0), Point2D(100.0, 0.0)
    assert distance_to_segment(Point2D(50.0, 10.0), start, end) == pytest.approx(10.0)
    # hinter dem Endpunkt -> Abstand zum Endpunkt
    assert distance_to_segment(Point2D(110.0, 0.0), start, end) == pytest.approx(10.0)


def test_bounding_box() -> None:
    assert bounding_box([]) is None
    low, high = bounding_box([Point2D(5.0, 1.0), Point2D(-2.0, 8.0), Point2D(0.0, 0.0)])
    assert low == Point2D(-2.0, 0.0)
    assert high == Point2D(5.0, 8.0)


def test_angle_between_uses_the_smallest_angle() -> None:
    assert angle_between(Point2D(1.0, 0.0), Point2D(0.0, 1.0)) == pytest.approx(90.0)
    assert angle_between(Point2D(1.0, 0.0), Point2D(-1.0, 0.0)) == pytest.approx(180.0)
    # Über die 0°/360°-Grenze hinweg (330° und 30° liegen 60° auseinander).
    assert angle_between(polar(Point2D(), 330.0, 1.0), polar(Point2D(), 30.0, 1.0)) == pytest.approx(60.0)
