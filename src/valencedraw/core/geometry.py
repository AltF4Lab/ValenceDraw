"""Reine Geometrie-Helfer – bewusst ohne Qt-Abhängigkeit.

Interne Koordinaten sind bildschirmähnlich: ``x`` nach rechts, ``y`` nach unten.
``BOND_LENGTH`` ist die Standard-Bindungslänge in Szeneneinheiten; bei Zoom 1.0
entspricht eine Bindung damit 40 Pixeln.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import NamedTuple

BOND_LENGTH: float = 40.0
"""Standard-Bindungslänge in Szeneneinheiten."""

ANGSTROM: float = BOND_LENGTH / 1.5
"""Umrechnung Å -> Szeneneinheiten (RDKit rechnet in Å, ~1.5 Å pro Bindung)."""

SNAP_STEP_DEG: float = 15.0
"""Rasterweite für das Einrasten von Bindungswinkeln."""


class Point2D(NamedTuple):
    """Unveränderlicher 2D-Punkt/Vektor."""

    x: float = 0.0
    y: float = 0.0

    # -- Vektorarithmetik ------------------------------------------------
    def __add__(self, other: "Point2D") -> "Point2D":
        return Point2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point2D") -> "Point2D":
        return Point2D(self.x - other.x, self.y - other.y)

    def __mul__(self, factor: float) -> "Point2D":
        return Point2D(self.x * factor, self.y * factor)

    def __rmul__(self, factor: float) -> "Point2D":
        return self * factor

    def __truediv__(self, factor: float) -> "Point2D":
        if factor == 0:
            raise ZeroDivisionError("Division eines Point2D durch 0")
        return Point2D(self.x / factor, self.y / factor)

    def __neg__(self) -> "Point2D":
        return Point2D(-self.x, -self.y)

    # -- Eigenschaften ---------------------------------------------------
    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def angle_deg(self) -> float:
        """Winkel in Grad, gemessen ab der positiven x-Achse."""
        return math.degrees(math.atan2(self.y, self.x))

    def normalized(self) -> "Point2D":
        n = self.length
        return Point2D() if n == 0 else Point2D(self.x / n, self.y / n)

    def distance_to(self, other: "Point2D") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def rotated(self, degrees: float, center: "Point2D | None" = None) -> "Point2D":
        origin = center if center is not None else Point2D()
        rad = math.radians(degrees)
        cos, sin = math.cos(rad), math.sin(rad)
        dx, dy = self.x - origin.x, self.y - origin.y
        return Point2D(origin.x + dx * cos - dy * sin, origin.y + dx * sin + dy * cos)

    def __str__(self) -> str:  # pragma: no cover - nur Diagnose
        return f"({self.x:.2f}, {self.y:.2f})"


def as_point(value: "Point2D | tuple[float, float] | list[float]") -> Point2D:
    """Nimmt einen ``Point2D`` oder ein 2-Tupel und liefert immer einen ``Point2D``."""
    if isinstance(value, Point2D):
        return value
    x, y = value
    return Point2D(float(x), float(y))


def polar(origin: Point2D, angle_deg: float, length: float) -> Point2D:
    """Punkt im gegebenen Winkel und Abstand von ``origin``."""
    rad = math.radians(angle_deg)
    return Point2D(origin.x + math.cos(rad) * length, origin.y + math.sin(rad) * length)


def angle_between(first: Point2D, second: Point2D) -> float:
    """Kleinster Winkel zwischen zwei Richtungen in Grad (0 … 180).

    >>> angle_between(Point2D(1.0, 0.0), Point2D(0.0, 1.0))
    90.0
    >>> angle_between(Point2D(1.0, 0.0), Point2D(-1.0, 0.0))
    180.0
    """
    difference = abs(first.angle_deg - second.angle_deg) % 360.0
    return min(difference, 360.0 - difference)


def snap_to_grid_angle(
    origin: Point2D,
    point: Point2D,
    step_deg: float = SNAP_STEP_DEG,
    length: float | None = None,
) -> Point2D:
    """Rastet den Winkel von ``origin`` nach ``point`` auf ein Vielfaches von ``step_deg``.

    Die Länge wird – falls nicht vorgegeben – von ``point`` übernommen.
    """
    delta = point - origin
    if length is None:
        length = delta.length
    if delta.length == 0:
        return origin + Point2D(length, 0.0)

    angle_deg = round(delta.angle_deg / step_deg) * step_deg
    rad = math.radians(angle_deg)
    return Point2D(origin.x + math.cos(rad) * length, origin.y + math.sin(rad) * length)


def distance_to_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
    """Kürzester Abstand von ``point`` zur Strecke ``start``–``end``."""
    delta = end - start
    length_sq = delta.x * delta.x + delta.y * delta.y
    if length_sq == 0:
        return point.distance_to(start)
    t = ((point.x - start.x) * delta.x + (point.y - start.y) * delta.y) / length_sq
    t = max(0.0, min(1.0, t))
    projection = Point2D(start.x + t * delta.x, start.y + t * delta.y)
    return point.distance_to(projection)


def bounding_box(points: Iterable[Point2D]) -> tuple[Point2D, Point2D] | None:
    """Minimaler und maximaler Punkt einer Punktmenge (oder ``None``)."""
    iterator = iter(points)
    try:
        first = next(iterator)
    except StopIteration:
        return None
    min_x = max_x = first.x
    min_y = max_y = first.y
    for point in iterator:
        min_x = min(min_x, point.x)
        max_x = max(max_x, point.x)
        min_y = min(min_y, point.y)
        max_y = max(max_y, point.y)
    return Point2D(min_x, min_y), Point2D(max_x, max_y)


def clamp(value: float, low: float, high: float) -> float:
    """Begrenzt ``value`` auf den Bereich ``low`` … ``high``."""
    return max(low, min(high, value))
