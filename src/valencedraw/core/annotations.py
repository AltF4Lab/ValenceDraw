"""Freie Objekte auf der Zeichenfläche: Textbeschriftungen und Reaktionspfeile.

Diese Objekte gehören wie das Molekül zum Dokument und werden zusammen mit ihm
in Undo-Snapshots gesichert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from .colors import RGB, normalize_color
from .geometry import Point2D, as_point
from .markup import TextRun, parse_markup


@dataclass(frozen=True)
class TextObject:
    """Textbeschriftung; ``position`` ist die linke obere Ecke.

    ``color`` überschreibt die Standardfarbe (``None`` = schwarz).
    """

    position: Point2D
    markup: str
    color: RGB | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", as_point(self.position))
        object.__setattr__(self, "color", normalize_color(self.color))

    @property
    def runs(self) -> tuple[TextRun, ...]:
        return parse_markup(self.markup)

    def is_blank(self) -> bool:
        return not self.markup.strip()

    def moved_to(self, position: Point2D) -> "TextObject":
        return replace(self, position=as_point(position))

    def with_markup(self, markup: str) -> "TextObject":
        return replace(self, markup=markup)


class ArrowKind(Enum):
    """Art des Reaktionspfeils. Die Richtung ergibt sich aus der Ziehrichtung."""

    FORWARD = "forward"
    EQUILIBRIUM = "equilibrium"
    PAIR_FLOW = "pair_flow"
    """Elektronenfluss eines Elektronenpaares (gebogener Pfeil, volle Spitze)."""
    RADICAL_FLOW = "radical_flow"
    """Elektronenfluss eines einzelnen Elektrons (gebogen, halbe Spitze)."""


FLOW_KINDS: frozenset[ArrowKind] = frozenset({ArrowKind.PAIR_FLOW, ArrowKind.RADICAL_FLOW})

ARROW_LABELS: dict[ArrowKind, str] = {
    ArrowKind.FORWARD: "Reaktion →",
    ArrowKind.EQUILIBRIUM: "Gleichgewicht ⇌",
    ArrowKind.PAIR_FLOW: "Paar ↷",
    ArrowKind.RADICAL_FLOW: "Radikal ↷",
}

DEFAULT_FLOW_BOW = 0.32
"""Standardkrümmung der Elektronenfluss-Pfeile (Anteil der Pfeillänge)."""

MAX_FLOW_BOW = 1.2
"""Grenze für das Ziehen der Krümmung (Kurve höchstens 0,6 × Länge)."""

MAX_FLOW_BOW_ALONG = 0.8
"""Grenze für das Verschieben des Bogens entlang des Pfeils."""

_ANGLE_EPS = 1e-12


def _signed_angle(angle: float) -> float:
    """Normalisiert einen Winkel auf ``(-π, π]``."""
    return (angle + math.pi) % math.tau - math.pi


@dataclass(frozen=True)
class ArrowArc:
    """Kreisbogen, auf dem ein Elektronenfluss-Pfeil verläuft.

    Winkel werden in Bogenmaß im Szenenkoordinatensystem gemessen (``x`` nach
    rechts, ``y`` nach unten). ``sweep`` ist der vorzeichenbehaftete Winkel von
    ``start_angle`` bis zum Ende; ein positives Vorzeichen bedeutet zunehmenden
    Winkel und damit auf dem Bildschirm im Uhrzeigersinn.
    """

    center: Point2D
    radius: float
    start_angle: float
    sweep: float

    @property
    def end_angle(self) -> float:
        return self.start_angle + self.sweep

    @property
    def length(self) -> float:
        """Bogenlänge."""
        return abs(self.sweep) * self.radius

    def point_at_angle(self, angle: float) -> Point2D:
        """Punkt auf dem Kreis zum angegebenen Winkel."""
        return Point2D(
            self.center.x + self.radius * math.cos(angle),
            self.center.y + self.radius * math.sin(angle),
        )

    def point(self, t: float) -> Point2D:
        """Punkt bei Parameter ``t`` (0 = Anfang, 1 = Ende)."""
        return self.point_at_angle(self.start_angle + self.sweep * t)

    def tangent_at_angle(self, angle: float) -> Point2D:
        """Einheits-Tangente in Bewegungsrichtung."""
        sign = 1.0 if self.sweep >= 0.0 else -1.0
        return Point2D(-math.sin(angle) * sign, math.cos(angle) * sign)

    def tangent(self, t: float) -> Point2D:
        return self.tangent_at_angle(self.start_angle + self.sweep * t)

    def angle_from_end(self, distance: float) -> float:
        """Winkel ``distance`` Bogenlänge vor dem Ende."""
        if self.radius <= 1e-9:
            return self.end_angle
        step = distance / self.radius
        return self.end_angle - math.copysign(step, self.sweep)

    def point_from_end(self, distance: float) -> Point2D:
        return self.point_at_angle(self.angle_from_end(distance))

    def tangent_from_end(self, distance: float) -> Point2D:
        return self.tangent_at_angle(self.angle_from_end(distance))

    def contains_angle(self, angle: float) -> bool:
        """Liegt ``angle`` auf dem überstrichenen Bogen (auch über 180°)?"""
        if abs(self.sweep) >= math.tau - 1e-9:
            return True
        sign = 1.0 if self.sweep >= 0.0 else -1.0
        return _directed_angle(self.start_angle, angle, sign) <= abs(self.sweep) + 1e-12


def _circumcenter(a: Point2D, b: Point2D, c: Point2D) -> Point2D | None:
    """Mittelpunkt des Kreises durch drei Punkte (``None`` bei Kollinearität)."""
    scale = max(a.distance_to(b), b.distance_to(c), a.distance_to(c))
    if scale <= 1e-9:
        return None
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    cx, cy = c.x, c.y
    determinant = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) <= 1e-9 * scale * scale:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    return Point2D(
        (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant,
        (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant,
    )


def _bow_from_apex(
    start: Point2D,
    end: Point2D,
    apex: Point2D,
) -> tuple[float, float]:
    """Zerlegt die Lage des Scheitels in ``bow`` und ``bow_along``."""
    vector = end - start
    length = vector.length
    if length <= 1e-9:
        return 0.0, 0.0
    direction = vector / length
    left = Point2D(direction.y, -direction.x)
    midpoint = Point2D((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
    offset = apex - midpoint
    scale = 2.0 / length
    return (
        (offset.x * left.x + offset.y * left.y) * scale,
        (offset.x * direction.x + offset.y * direction.y) * scale,
    )


def _directed_angle(start_angle: float, end_angle: float, sign: float) -> float:
    """Positiver Winkel von ``start_angle`` nach ``end_angle`` in Richtung ``sign``."""
    delta = end_angle - start_angle if sign >= 0.0 else start_angle - end_angle
    return delta % math.tau


def _arc_with_tangent(
    start: Point2D,
    end: Point2D,
    tangent: Point2D,
    *,
    at_end: bool,
) -> ArrowArc | None:
    """Kreisbogen von ``start`` nach ``end`` mit Tangente an einem der Enden.

    ``at_end=True`` setzt die Tangente ans Ende, ``False`` an den Anfang.
    """
    span = end - start if at_end else start - end
    anchor = end if at_end else start
    span_length = span.length
    tangent = tangent.normalized()
    if span_length <= 1e-9 or tangent.length <= 1e-9:
        return None
    normal = Point2D(-tangent.y, tangent.x)
    denominator = normal.x * span.x + normal.y * span.y
    if abs(denominator) <= 1e-9 * max(1.0, span_length):
        return None
    distance = -(span_length * span_length) / (2.0 * denominator)
    if abs(distance) <= 1e-9:
        return None
    center = anchor + normal * distance
    sign = 1.0 if distance > 0.0 else -1.0
    start_angle = math.atan2(start.y - center.y, start.x - center.x)
    end_angle = math.atan2(end.y - center.y, end.x - center.x)
    sweep = sign * _directed_angle(start_angle, end_angle, sign)
    if abs(sweep) <= _ANGLE_EPS:
        return None
    return ArrowArc(center, abs(distance), start_angle, sweep)


def _same_circle(first: ArrowArc, second: ArrowArc) -> bool:
    """Liegen beide Bögen auf demselben Kreis?"""
    scale = max(first.radius, second.radius, 1.0)
    return (
        first.center.distance_to(second.center) <= 1e-5 * scale
        and abs(first.radius - second.radius) <= 1e-5 * scale
    )


def _circumcircle_arc(start: Point2D, apex: Point2D, end: Point2D) -> ArrowArc | None:
    """Kreisbogen durch drei Punkte (Rückfallebene bei entarteter Tangente)."""
    center = _circumcenter(start, apex, end)
    if center is None:
        return None
    radius = center.distance_to(start)
    if radius <= 1e-9:
        return None
    start_angle = math.atan2(start.y - center.y, start.x - center.x)
    end_angle = math.atan2(end.y - center.y, end.x - center.x)
    apex_angle = math.atan2(apex.y - center.y, apex.x - center.x)
    delta = _signed_angle(end_angle - start_angle)
    apex_offset = _signed_angle(apex_angle - start_angle)
    if delta >= 0.0:
        sweep = (
            delta
            if -_ANGLE_EPS <= apex_offset <= delta + _ANGLE_EPS
            else delta - math.tau
        )
    else:
        sweep = (
            delta
            if delta - _ANGLE_EPS <= apex_offset <= _ANGLE_EPS
            else delta + math.tau
        )
    if abs(sweep) <= _ANGLE_EPS:
        return None
    return ArrowArc(center, radius, start_angle, sweep)


def _arc_bounds(arc: ArrowArc) -> tuple[Point2D, Point2D]:
    """Exakte Bounding-Box eines Bogens (auch über 180°)."""
    start = arc.point_at_angle(arc.start_angle)
    end = arc.point_at_angle(arc.end_angle)
    xs = [start.x, end.x]
    ys = [start.y, end.y]
    candidates = (
        (0.0, arc.center.x + arc.radius, xs),
        (math.pi, arc.center.x - arc.radius, xs),
        (math.pi / 2.0, arc.center.y + arc.radius, ys),
        (-math.pi / 2.0, arc.center.y - arc.radius, ys),
    )
    for angle, value, axis in candidates:
        if arc.contains_angle(angle):
            axis.append(value)
    return Point2D(min(xs), min(ys)), Point2D(max(xs), max(ys))


def resize_flow_arrow(
    arrow: "ArrowObject",
    position: Point2D,
    which: str,
    min_length: float = 1e-6,
) -> "ArrowObject | None":
    """Zieht ein Ende eines gebogenen Pfeils entlang seines Kreisbogens.

    Das gezogene Ende wandert auf demselben Kreis wie der übrige Pfeil weiter,
    sodass Radius und Krümmung erhalten bleiben – auch über 180° hinaus.
    ``which`` ist ``"start"`` oder ``"end"``. Liefert ``None``, wenn der Pfeil
    gerade ist oder unter ``min_length`` verkürzt würde.
    """
    arcs = arrow.arcs
    if not arcs:
        return None
    arc = arcs[-1] if which == "end" else arcs[0]
    if arc.radius <= 1e-9:
        return None

    sign = 1.0 if arc.sweep >= 0.0 else -1.0
    current_angle = arc.end_angle if which == "end" else arc.start_angle
    mouse_angle = math.atan2(
        position.y - arc.center.y,
        position.x - arc.center.x,
    )
    # Winkel nahe der aktuellen Position wählen, damit der Punkt nicht auf die
    # andere Seite des Kreises springt.
    moved_angle = current_angle + _signed_angle(mouse_angle - current_angle)
    delta = _signed_angle(moved_angle - current_angle)
    if which != "end":
        delta = -delta
    travel = abs(arc.sweep) + sign * delta
    # Nie durch den Scheitel hindurch und insgesamt höchstens ein Vollkreis
    # (sonst überlappt sich der Pfeil selbst).
    other_travel = sum(abs(piece.sweep) for piece in arcs if piece is not arc)
    limit = max(0.0, math.tau - 1e-6 - other_travel)
    travel = min(max(travel, 0.0), limit)
    if travel <= 1e-9:
        return None
    new_sweep = sign * travel

    if which == "end":
        start = arrow.start
        end = arc.point_at_angle(arc.start_angle + new_sweep)
    else:
        start = arc.point_at_angle(arc.end_angle - new_sweep)
        end = arrow.end

    if start.distance_to(end) < min_length:
        return None

    bow, bow_along = _bow_from_apex(start, end, arrow.curve_midpoint)
    tangent = arrow.apex_tangent
    if tangent is None or tangent.length <= 1e-9:
        tangent = arrow.direction
    return ArrowObject(
        start,
        end,
        arrow.kind,
        round(bow, 9),
        round(bow_along, 9),
        tangent.normalized(),
        arrow.color,
    )


@dataclass(frozen=True)
class ArrowObject:
    """Reaktionspfeil von ``start`` nach ``end``.

    ``bow`` krümmt den Pfeil (Elektronenfluss): Der Scheitel liegt um
    ``bow * Länge / 2`` senkrecht zur Verbindungslinie versetzt. ``bow_along``
    verschiebt den Scheitel zusätzlich **entlang** des Pfeils. Die Kurve besteht
    aus zwei Kreisbögen, die sich im Scheitel mit gemeinsamer Tangente treffen
    (:attr:`apex_tangent`). Liegen beide auf demselben Kreis, ist der Pfeil ein
    einziger Kreisbogen; ein entlang verschobener Scheitel macht ihn asymmetrisch.
    """

    start: Point2D
    end: Point2D
    kind: ArrowKind = ArrowKind.FORWARD
    bow: float = 0.0
    bow_along: float = 0.0
    apex_tangent: Point2D | None = None
    """Tangente im Scheitel; ``None`` = parallel zur Verbindungslinie."""
    color: RGB | None = None
    """Linienfarbe (``None`` = Standardfarbe)."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", as_point(self.start))
        object.__setattr__(self, "end", as_point(self.end))
        if self.apex_tangent is not None:
            tangent = as_point(self.apex_tangent).normalized()
            object.__setattr__(self, "apex_tangent", tangent)
        object.__setattr__(self, "color", normalize_color(self.color))

    @property
    def vector(self) -> Point2D:
        return self.end - self.start

    @property
    def length(self) -> float:
        return self.vector.length

    @property
    def direction(self) -> Point2D:
        return self.vector.normalized()

    @property
    def normal(self) -> Point2D:
        direction = self.direction
        return Point2D(-direction.y, direction.x)

    @property
    def midpoint(self) -> Point2D:
        return Point2D((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)

    # -- Krümmung (Elektronenfluss) ---------------------------------------
    @property
    def is_flow(self) -> bool:
        """Ist das ein Elektronenfluss-Pfeil (gebogen)?"""
        return self.kind in FLOW_KINDS

    @property
    def control(self) -> Point2D:
        """Hilfspunkt der bisherigen Bézier-Parametrisierung.

        Positive ``bow``-Werte krümmen den Pfeil nach links (bei einem Pfeil
        nach rechts also nach oben); ``bow_along`` verschiebt den Scheitel
        entlang des Pfeils (positiv = zum Ende hin). Der gezeichnete Bogen
        führt durch :attr:`curve_midpoint`.
        """
        if not self.bow and not self.bow_along:
            return self.midpoint
        direction = self.direction
        left_normal = Point2D(direction.y, -direction.x)
        return (
            self.midpoint
            + direction * (self.length * self.bow_along)
            + left_normal * (self.length * self.bow)
        )

    @property
    def curve_midpoint(self) -> Point2D:
        """Punkt auf halbem Weg zwischen Start und Ende.

        Bei gebogenen Pfeilen liegt er auf dem gezeichneten Kreisbogen; der
        mittlere Greifpunkt zieht diesen Punkt direkt unter die Maus.
        """
        if not self.bow and not self.bow_along:
            return self.midpoint
        return self.start * 0.25 + self.control * 0.5 + self.end * 0.25

    @property
    def apex_direction(self) -> Point2D:
        """Tangente im Scheitel (gespeichert oder parallel zur Sehne)."""
        if self.apex_tangent is not None and self.apex_tangent.length > 1e-9:
            return self.apex_tangent
        return self.direction

    @property
    def arcs(self) -> tuple[ArrowArc, ...]:
        """Kreisbögen des Pfeils (zwei bei asymmetrischer Wölbung, sonst einer)."""
        if not self.is_flow:
            return ()
        chord = self.vector
        chord_length = chord.length
        if chord_length <= 1e-9:
            return ()
        direction = chord / chord_length
        normal = Point2D(-direction.y, direction.x)
        apex = self.curve_midpoint
        offset = apex - self.start
        if abs(offset.x * normal.x + offset.y * normal.y) <= 1e-9 * max(
            1.0, chord_length
        ):
            return ()
        tangent = self.apex_direction
        if tangent.length <= 1e-9:
            return ()
        first = _arc_with_tangent(self.start, apex, tangent, at_end=True)
        second = _arc_with_tangent(apex, self.end, tangent, at_end=False)
        if first is None or second is None:
            fallback = _circumcircle_arc(self.start, apex, self.end)
            return (fallback,) if fallback is not None else ()
        if _same_circle(first, second):
            return (
                ArrowArc(
                    first.center,
                    first.radius,
                    first.start_angle,
                    first.sweep + second.sweep,
                ),
            )
        return (first, second)

    @property
    def is_curved(self) -> bool:
        """Hat der Pfeil einen gebogenen Verlauf?"""
        return bool(self.arcs)

    @property
    def arc(self) -> ArrowArc | None:
        """Einziger Kreisbogen (``None`` bei geradem oder asymmetrischem Verlauf)."""
        arcs = self.arcs
        return arcs[0] if len(arcs) == 1 else None

    @property
    def end_direction(self) -> Point2D:
        """Tangentenrichtung am Ende (für die Pfeilspitze)."""
        arcs = self.arcs
        if arcs:
            return arcs[-1].tangent(1.0)
        return self.direction

    def translated(self, delta: Point2D) -> "ArrowObject":
        """Kopie, deren Endpunkte um ``delta`` verschoben sind."""
        return replace(self, start=self.start + delta, end=self.end + delta)

    def points(self, samples: int = 16) -> tuple[Point2D, ...]:
        """Polygonzug der Pfeillinie (Stützpunkte der Kreisbögen)."""
        arcs = self.arcs
        if not arcs:
            return (self.start, self.end)
        samples = max(2, samples)
        curve = [self.start]
        if len(arcs) == 1:
            arc = arcs[0]
            curve.extend(arc.point(index / samples) for index in range(1, samples + 1))
        else:
            total = sum(arc.length for arc in arcs)
            remaining = samples
            for index, arc in enumerate(arcs):
                if index == len(arcs) - 1:
                    count = max(1, remaining)
                else:
                    count = max(1, round(samples * arc.length / total))
                    count = min(count, remaining - (len(arcs) - index - 1))
                curve.extend(
                    arc.point(step / count) for step in range(1, count + 1)
                )
                remaining -= count
        # Exakte Endpunkte (ohne Rundungsreste aus Sinus/Kosinus).
        curve[0] = self.start
        curve[-1] = self.end
        return tuple(curve)

    def extent(self) -> tuple[Point2D, Point2D]:
        """Linke obere und rechte untere Ecke der Pfeillinie."""
        xs = [self.start.x, self.end.x]
        ys = [self.start.y, self.end.y]
        for arc in self.arcs:
            low, high = _arc_bounds(arc)
            xs.extend((low.x, high.x))
            ys.extend((low.y, high.y))
        return Point2D(min(xs), min(ys)), Point2D(max(xs), max(ys))
