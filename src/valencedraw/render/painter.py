"""Vektorbasiertes Zeichnen eines Moleküls mit ``QPainter``.

Der Renderer kennt nur das Modell und den ``Style`` – keine Widgets. Dadurch
funktioniert dieselbe Zeichenroutine für Canvas, PNG- und SVG-Export.
"""

from __future__ import annotations

import math
from dataclasses import replace
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPolygonF,
    QTextDocument,
)

from ..core.annotations import ArrowKind, ArrowObject, TextObject
from ..core.geometry import Point2D
from ..core.markup import markup_to_html, parse_markup, to_plain_text
from ..core.molecule import (
    Bond,
    BondStereo,
    Molecule,
    charge_text,
    default_double_bond_side,
    partial_charge_text,
)
from ..core.valence import implicit_hydrogens
from .style import DEFAULT_STYLE, RGB, Style

ARROW_HANDLE_FACTOR = 0.22
"""Radius der Pfeil-Greifpunkte als Anteil der Bindungslänge."""

SELECTION_RADIUS_FACTOR = 0.42
"""Radius der runden Auswahlmarkierung je Atom (Anteil der Bindungslänge)."""

MAX_SIDE_TRIM_FACTOR = 0.15
"""Höchstens dieser Anteil der Länge wird je Ende an der seitlichen
Doppelbindungslinie abgeschnitten (damit kurze Bindungen sichtbar bleiben)."""


def qcolor(rgb: RGB, alpha: int = 255) -> QColor:
    color = QColor(rgb[0], rgb[1], rgb[2])
    color.setAlpha(alpha)
    return color


def to_qpoint(point: Point2D) -> QPointF:
    return QPointF(point.x, point.y)


#: Schriftgröße der Ladung relativ zur Labelgröße (hochgestellt).
CHARGE_SCALE = 0.62
#: Schriftgröße der Teilladung relativ zur Labelgröße.
PARTIAL_CHARGE_SCALE = 0.85
#: Abstand zwischen Label und Ladung (Szeneneinheiten).
CHARGE_GAP = 0.75
#: Mögliche Ecken für die Ladung – Reihenfolge = Vorliebe bei Gleichstand.
CHARGE_CORNERS: tuple[tuple[float, float], ...] = (
    (1.0, -1.0),  # oben rechts
    (1.0, 1.0),  # unten rechts
    (-1.0, -1.0),  # oben links
    (-1.0, 1.0),  # unten links
)


def _hydrogen_markup(molecule: Molecule, atom_id: int) -> str:
    """Anhang der impliziten H-Atome (``H``, ``H_2``) – leer, wenn keiner.

    Freie, ungebundene Atome bleiben beim reinen Elementsymbol: Ein einzelnes
    ``O`` auf dem Blatt ist damit keine Wasserstoff-Formel ``OH_2``. Erst eine
    Bindung macht daraus ``OH``; eine zweite Bindung oder eine Doppelbindung
    verbraucht das Bindungsvermögen und lässt das ``H`` wieder verschwinden.
    """
    bonded = molecule.bonded_valence(atom_id)
    if bonded <= 0:
        return ""
    atom = molecule.atom(atom_id)
    count = implicit_hydrogens(atom.element, atom.charge, bonded)
    if count <= 0:
        return ""
    if count == 1:
        return "H"
    return f"H_{count}"


def atom_label_markup(molecule: Molecule, atom_id: int) -> str:
    """Anzeige-Markup des Atoms **ohne** Ladung.

    Die Ladung wird separat gezeichnet (:func:`paint_atom_charge`). So verändert
    sie weder die Labelbreite noch die Bindungsenden oder die Zentrierung des
    Atoms – sie hängt nur optisch daneben. Ein eigenes Label überschreibt das
    Elementsymbol; ein geladenes Kohlenstoffatom wird dadurch sichtbar.

    Heteroatome zeigen ihre impliziten Wasserstoffatome (``OH``, ``NH_2``,
    ``SH``). Kohlenstoff und Wasserstoff bleiben beim reinen Symbol – das
    Skelett zeigt die H-Atome nicht, wie in der Strukturformel üblich.
    """
    atom = molecule.atom(atom_id)
    label = atom.label.strip()
    if label:
        return label
    if atom.element == "C":
        if atom.charge == 0 and atom.partial_charge == 0:
            return ""
        return atom.element
    if atom.element == "H":
        return atom.element
    return atom.element + _hydrogen_markup(molecule, atom_id)


def atom_label(molecule: Molecule, atom_id: int) -> str:
    """Anzeigetext eines Atoms ohne Ladung; leer, wenn es unbeschriftet ist."""
    return to_plain_text(atom_label_markup(molecule, atom_id)).strip()


def atom_label_full(molecule: Molecule, atom_id: int) -> str:
    """Anzeigetext **inklusive** Ladung ohne Markup (``N2+``, ``OTs+``)."""
    charge = charge_text(molecule.atom(atom_id).charge)
    return f"{atom_label(molecule, atom_id)}{charge}"


def _charge_font(style: Style) -> QFont:
    """Schrift der hochgestellten Ladung."""
    font = QFont(style.label_font_family)
    font.setPixelSize(max(1, round(style.label_pixel_size * CHARGE_SCALE)))
    return font


def _partial_charge_font(style: Style) -> QFont:
    """Schrift der Teilladung – etwas größer als die Formalladung.

    Das δ steht in voller Lesegröße, das Vorzeichen ist als hochgestelltes
    Zeichen (``⁺``/``⁻``) im Zeichensatz bereits kleiner.
    """
    font = QFont(style.label_font_family)
    font.setPixelSize(max(1, round(style.label_pixel_size * PARTIAL_CHARGE_SCALE)))
    return font


def charge_corner(molecule: Molecule, atom_id: int) -> tuple[float, float]:
    """Ecke des Labels, an die die Ladung kommt.

    Gewählt wird die Ecke, die am weitesten von allen Bindungen des Atoms
    entfernt liegt: bei einem endständigen Atom die dem Nachbarn abgewandte
    Seite, bei einem Ringatom (z. B. Piperidin-N) eine freie Ecke statt mitten
    in die Ringbindung hinein.
    """
    position = molecule.atom(atom_id).position
    bonds: list[Point2D] = []
    for neighbor in molecule.neighbors(atom_id):
        vector = molecule.atom(neighbor).position - position
        if vector.length > 1e-9:
            bonds.append(vector / vector.length)
    if not bonds:
        return CHARGE_CORNERS[0]

    best = CHARGE_CORNERS[0]
    best_score = max(best[0] * bond.x + best[1] * bond.y for bond in bonds)
    for corner in CHARGE_CORNERS[1:]:
        score = max(corner[0] * bond.x + corner[1] * bond.y for bond in bonds)
        if score < best_score - 1e-9:
            best, best_score = corner, score
    return best


def charge_direction(
    molecule: Molecule,
    atom_id: int,
) -> Point2D:
    """Richtung der Ladung: gespeicherte Position oder automatische freie Ecke."""
    stored = molecule.atom(atom_id).charge_direction
    if stored is not None:
        return stored
    corner_x, corner_y = charge_corner(molecule, atom_id)
    length = math.hypot(corner_x, corner_y) or 1.0
    return Point2D(corner_x / length, corner_y / length)


def _outside_text_rect(
    molecule: Molecule,
    atom_id: int,
    text: str,
    direction: Point2D,
    style: Style,
    font: QFont,
) -> QRectF | None:
    """Fläche eines hochgestellten Textes außerhalb der Label-Box.

    Gemeinsame Grundlage für Formalladung (``+``, ``2+`` …) und Teilladung
    (``δ⁺``/``δ⁻``): Der Text sitzt in Richtung ``direction`` vor dem Label und
    verändert dessen Größe, Zentrierung und Bindungsenden nicht.
    """
    if not text or not atom_label_markup(molecule, atom_id):
        return None
    half_width, half_height = label_half_size(molecule, atom_id, style)
    center = label_center(molecule, atom_id, style)
    metrics = QFontMetricsF(font)
    bounds = metrics.boundingRect(text)
    width = max(metrics.horizontalAdvance(text), bounds.width(), 1.0)
    height = max(metrics.capHeight(), bounds.height(), 1.0)
    distance = (
        _rounded_extent(half_width, half_height, direction)
        + CHARGE_GAP
        + max(width, height) / 2.0
    )
    point = center + direction * distance
    return QRectF(point.x - width / 2.0, point.y - height / 2.0, width, height)


def charge_rect_at(
    molecule: Molecule,
    atom_id: int,
    direction: Point2D,
    style: Style = DEFAULT_STYLE,
) -> QRectF | None:
    """Fläche der Ladung in Richtung ``direction`` (für Vorschau und Zeichnen)."""
    atom = molecule.atom(atom_id)
    if atom.charge == 0:
        return None
    return _outside_text_rect(
        molecule, atom_id, charge_text(atom.charge), direction, style, _charge_font(style)
    )


def charge_rect(
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> QRectF | None:
    """Fläche der gezeichneten Ladung (Szenenkoordinaten); ``None`` bei 0.

    Die Ladung sitzt außerhalb der Label-Box – in der vom Anwender gewählten
    Richtung oder (ohne Wahl) in der freien Ecke. Label, Zentrierung und
    Bindungsenden bleiben dadurch unverändert.
    """
    return charge_rect_at(molecule, atom_id, charge_direction(molecule, atom_id), style)


def paint_atom_charge(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Zeichnet die Formalladung an ihrer Position neben dem Atomlabel."""
    rect = charge_rect(molecule, atom_id, style)
    if rect is None:
        return
    painter.save()
    painter.setFont(_charge_font(style))
    painter.setPen(QPen(qcolor(_label_color(molecule, atom_id, style))))
    # Etwas größer als die Textfläche zeichnen, sonst schneidet Qt breite
    # Ladungen wie „+5“ am Rand ab.
    painter.drawText(
        rect.adjusted(-2.0, -2.0, 2.0, 2.0),
        Qt.AlignmentFlag.AlignCenter,
        charge_text(molecule.atom(atom_id).charge),
    )
    painter.restore()


# -- Teilladung (δ⁺ / δ⁻) ------------------------------------------------
def partial_charge_direction(
    molecule: Molecule,
    atom_id: int,
) -> Point2D:
    """Richtung der Teilladung: gespeicherte Position oder freie Ecke.

    Zeigt das Atom zusätzlich eine Formalladung, sitzt die Teilladung in der
    **gegenüberliegenden** Ecke – sonst würden sich beide Texte überdecken.
    """
    atom = molecule.atom(atom_id)
    stored = atom.partial_charge_direction
    if stored is not None:
        return stored
    direction = charge_direction(molecule, atom_id)
    if atom.charge != 0:
        return Point2D(-direction.x, -direction.y)
    return direction


def partial_charge_rect_at(
    molecule: Molecule,
    atom_id: int,
    direction: Point2D,
    style: Style = DEFAULT_STYLE,
) -> QRectF | None:
    """Fläche der Teilladung in Richtung ``direction`` (Vorschau und Zeichnen)."""
    atom = molecule.atom(atom_id)
    if atom.partial_charge == 0:
        return None
    return _outside_text_rect(
        molecule,
        atom_id,
        partial_charge_text(atom.partial_charge),
        direction,
        style,
        _partial_charge_font(style),
    )


def partial_charge_rect(
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> QRectF | None:
    """Fläche der gezeichneten Teilladung (``None``, wenn keine gesetzt ist)."""
    return partial_charge_rect_at(
        molecule, atom_id, partial_charge_direction(molecule, atom_id), style
    )


def paint_atom_partial_charge(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Zeichnet δ⁺/δ⁻ an der Position neben dem Atomlabel."""
    rect = partial_charge_rect(molecule, atom_id, style)
    if rect is None:
        return
    painter.save()
    painter.setFont(_partial_charge_font(style))
    painter.setPen(QPen(qcolor(_label_color(molecule, atom_id, style))))
    painter.drawText(
        rect.adjusted(-2.0, -2.0, 2.0, 2.0),
        Qt.AlignmentFlag.AlignCenter,
        partial_charge_text(molecule.atom(atom_id).partial_charge),
    )
    painter.restore()


def _label_color(molecule: Molecule, atom_id: int, style: Style) -> RGB:
    """Farbe des Atomlabels, der Ladungen und Elektronen.

    Ohne eigene Farbe wird – wie bei Bindungen und Pfeilen – der Bindungston
    verwendet. Die Zeichnung startet dadurch einfarbig (schwarz) und wird erst
    über die Farbpalette eingefärbt.
    """
    return molecule.atom(atom_id).color or style.bond_color


def _electron_center(
    molecule: Molecule,
    atom_id: int,
    direction: Point2D,
    style: Style,
) -> Point2D:
    """Mittelpunkt der Elektronen in Richtung ``direction`` (vor dem Label).

    Ausgegangen wird vom **Label-Mittelpunkt**, nicht vom Atomzentrum: bei
    endständigen Atomen sitzt das Label seitlich versetzt, sonst läge der
    Punktekreis schief über der Bindung und die Abstände würden stark
    schwanken. Der Abstand folgt der abgerundeten Label-Box, damit die Punkte
    rundum gleich weit außen liegen.
    """
    atom = molecule.atom(atom_id)
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        center = atom.position
        distance = style.electron_min_distance
    else:
        center = label_center(molecule, atom_id, style)
        distance = _rounded_extent(half_width, half_height, direction)
    distance = max(distance, style.electron_min_distance)
    return center + direction * (distance + style.electron_gap + style.electron_dot_radius)


def electron_anchor(
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> Point2D:
    """Bezugspunkt der Elektronen: Label-Mittelpunkt (sonst das Atomzentrum)."""
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        return molecule.atom(atom_id).position
    return label_center(molecule, atom_id, style)


def electron_dots(
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> tuple[Point2D, ...]:
    """Positionen aller Elektronenpunkte eines Atoms.

    Ein Elektronenpaar besteht aus **zwei einzelnen Punkten**, die quer zur
    Richtung nebeneinander liegen; ein Radikal ist ein einzelner Punkt.
    """
    atom = molecule.atom(atom_id)
    dots: list[Point2D] = []
    for direction in atom.lone_pairs:
        dots.extend(electron_preview(molecule, atom_id, direction, False, style))
    for direction in atom.radicals:
        dots.extend(electron_preview(molecule, atom_id, direction, True, style))
    return tuple(dots)


def electron_preview(
    molecule: Molecule,
    atom_id: int,
    direction: Point2D,
    radical: bool = False,
    style: Style = DEFAULT_STYLE,
) -> tuple[Point2D, ...]:
    """Punkte, die in Richtung ``direction`` entstehen würden (Vorschau)."""
    center = _electron_center(molecule, atom_id, direction, style)
    if radical:
        return (center,)
    offset = Point2D(-direction.y, direction.x) * (style.electron_pair_gap / 2.0)
    return (center - offset, center + offset)


def electron_targets(
    molecule: Molecule,
    style: Style = DEFAULT_STYLE,
) -> tuple[tuple[int, str, int, Point2D], ...]:
    """Alle Elektronenpunkte als ``(atom_id, art, index, position)``."""
    targets: list[tuple[int, str, int, Point2D]] = []
    for atom_id in molecule.atom_ids():
        atom = molecule.atom(atom_id)
        for index, direction in enumerate(atom.lone_pairs):
            targets.extend(
                (atom_id, "pair", index, dot)
                for dot in electron_preview(molecule, atom_id, direction, False, style)
            )
        for index, direction in enumerate(atom.radicals):
            targets.extend(
                (atom_id, "radical", index, dot)
                for dot in electron_preview(molecule, atom_id, direction, True, style)
            )
    return tuple(targets)


def electron_hit(
    molecule: Molecule,
    position: Point2D,
    style: Style = DEFAULT_STYLE,
    tolerance: float | None = None,
) -> tuple[int, str, int] | None:
    """Elektron unter der Maus: ``(atom_id, art, index)`` oder ``None``."""
    if tolerance is None:
        tolerance = style.electron_dot_radius + style.hit_radius * 0.45
    best: tuple[int, str, int] | None = None
    best_distance = tolerance
    for atom_id, kind, index, dot in electron_targets(molecule, style):
        distance = dot.distance_to(position)
        if distance <= best_distance:
            best, best_distance = (atom_id, kind, index), distance
    return best


def electron_bounds(molecule: Molecule, style: Style = DEFAULT_STYLE) -> QRectF | None:
    """Bounding-Box aller Elektronenpunkte (für Export/Inhaltsgrenzen)."""
    dots = [dot for atom_id in molecule.atom_ids() for dot in electron_dots(molecule, atom_id, style)]
    if not dots:
        return None
    radius = style.electron_dot_radius
    rect = QRectF(dots[0].x - radius, dots[0].y - radius, 2 * radius, 2 * radius)
    for dot in dots[1:]:
        rect = rect.united(QRectF(dot.x - radius, dot.y - radius, 2 * radius, 2 * radius))
    return rect


def paint_electrons(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Zeichnet Elektronenpaare (zwei Punkte) und Radikale (ein Punkt)."""
    dots = electron_dots(molecule, atom_id, style)
    if not dots:
        return
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(qcolor(molecule.atom(atom_id).color or style.bond_color)))
    radius = style.electron_dot_radius
    for dot in dots:
        painter.drawEllipse(to_qpoint(dot), radius, radius)
    painter.restore()


def _atom_uses_rich_label(molecule: Molecule, atom_id: int) -> bool:
    """Eigene Beschriftung oder tiefgestellte H-Zahl → Rendering als Rich-Text.

    Reine Elementsymbole (auch mit angehängtem ``H`` wie ``OH``) laufen weiter
    über die schnelle Font-Metrik, damit ihre Geometrie (Bindungsenden, Hover,
    Trefferfläche) unverändert bleibt – auch wenn eine Ladung daneben steht.
    """
    if molecule.atom(atom_id).label.strip():
        return True
    return "_" in atom_label_markup(molecule, atom_id)


def _font(style: Style) -> QFont:
    font = QFont(style.label_font_family)
    font.setPixelSize(style.label_pixel_size)
    return font


@lru_cache(maxsize=512)
def _text_metrics(family: str, pixel_size: int, text: str) -> tuple[float, float, float, float]:
    """(Breite, Höhe, Versalhöhe, Vorschub) eines Labels – gecacht."""
    font = QFont(family)
    font.setPixelSize(pixel_size)
    metrics = QFontMetricsF(font)
    tight = metrics.tightBoundingRect(text)
    return tight.width(), tight.height(), metrics.capHeight(), metrics.horizontalAdvance(text)


def _first_glyph_width(markup: str, style: Style) -> float:
    """Breite des ersten gezeichneten Zeichens eines Labels.

    Damit lässt sich das erste Zeichen eines mehrbuchstabigen Labels mittig
    über die Bindungsachse setzen (``NH`` → das ``N`` sitzt auf der Achse).
    """
    for run in parse_markup(markup):
        if not run.text:
            continue
        font = _font(style)
        font.setBold(run.bold)
        font.setItalic(run.italic)
        return QFontMetricsF(font).horizontalAdvance(run.text[0])
    return 0.0


def _atom_label_document(molecule: Molecule, atom_id: int, style: Style) -> QTextDocument | None:
    """Rich-Text-Dokument für ein Label mit Auszeichnung (oder ``None``)."""
    if not _atom_uses_rich_label(molecule, atom_id):
        return None
    return _text_document(
        atom_label_markup(molecule, atom_id), style.label_font_family, style.label_pixel_size
    )


def _atom_label_size(molecule: Molecule, atom_id: int, style: Style) -> QSizeF:
    """Größe des Atomlabels in Szeneneinheiten (leer, wenn unbeschriftet)."""
    markup = atom_label_markup(molecule, atom_id)
    if not markup:
        return QSizeF()
    if _atom_uses_rich_label(molecule, atom_id):
        _ink_x, _ink_y, ink_width, ink_height = _rich_label_ink(
            markup, style.label_font_family, style.label_pixel_size
        )
        return QSizeF(ink_width, ink_height)
    width, height, _cap, _advance = _text_metrics(
        style.label_font_family, style.label_pixel_size, markup
    )
    return QSizeF(width, height)


def label_half_size(molecule: Molecule, atom_id: int, style: Style = DEFAULT_STYLE) -> tuple[float, float]:
    """Halbe Labelgröße inkl. Rand; ``(0, 0)`` wenn das Atom unbeschriftet ist."""
    size = _atom_label_size(molecule, atom_id, style)
    if size.isEmpty():
        return 0.0, 0.0
    padding = style.label_padding
    return size.width() / 2.0 + padding, size.height() / 2.0 + padding


def _rounded_extent(half_width: float, half_height: float, toward: Point2D) -> float:
    """Abstand vom Zentrum bis zum Rand einer abgerundeten Label-Box.

    Die Box wird als Kapsel (Rechteck mit halbkreisförmigen Ecken) aufgefasst.
    Eine schräge Bindung endet dadurch nicht an der vollen Rechteck-Ecke, die
    deutlich weiter außen liegt als die Glyphen selbst – sonst wirkt die
    Bindung unnötig kurz.
    """
    length = math.hypot(toward.x, toward.y)
    if length < 1e-9 or half_width <= 0.0 or half_height <= 0.0:
        return 0.0
    ux, uy = toward.x / length, toward.y / length
    radius = min(half_width, half_height)
    ax = max(half_width - radius, 0.0)
    ay = max(half_height - radius, 0.0)

    candidates: list[float] = []
    if abs(ux) > 1e-9:  # gerade Kante links/rechts
        hit = half_width / abs(ux)
        if hit * abs(uy) <= ay + 1e-9:
            candidates.append(hit)
    if abs(uy) > 1e-9:  # gerade Kante oben/unten
        hit = half_height / abs(uy)
        if hit * abs(ux) <= ax + 1e-9:
            candidates.append(hit)
    for cx in ((ax, -ax) if ax > 1e-9 else (0.0,)):  # abgerundete Ecken
        for cy in ((ay, -ay) if ay > 1e-9 else (0.0,)):
            if cx * ux < -1e-9 or cy * uy < -1e-9:
                continue
            dot = cx * ux + cy * uy
            discriminant = dot * dot - cx * cx - cy * cy + radius * radius
            if discriminant >= 0.0:
                candidates.append(dot + math.sqrt(discriminant))

    # Die Kapsel ist konvex: Der Strahl verlässt sie an der **äußeren** der
    # berechneten Grenzen. Bei breiten Labels (``OH``, ``OTs``) durchstößt er
    # auch die Eckenkreise, die im Labelinneren liegen – dort wäre das Minimum
    # deutlich zu kurz.
    return max(candidates) if candidates else radius


def label_offset(
    molecule: Molecule,
    atom_id: int,
    style: Style = DEFAULT_STYLE,
) -> Point2D:
    """Verschiebung des Label-Mittelpunkts gegenüber dem Atomzentrum.

    Endständige Atome (Grad 1) tragen ihr Label **außerhalb** der Bindung. Die
    Verschiebung läuft entlang der dominanten Bindungsachse: bei einer eher
    waagerechten Bindung seitlich, bei einer eher senkrechten nach oben bzw.
    unten. So bleibt der Text auf der Höhe des Bindungsendes; eine Verschiebung
    entlang der Bindungsdiagonale würde breite Gruppen wie ``OTs`` sichtbar zu
    tief setzen.

    Das Label schließt immer mit dem bindungsnahen Rand an das Atom an: bei
    waagerechter Bindung liegt die Textkante am Bindungsende, bei senkrechter
    Bindung beginnt der Text **linksbündig** am Bindungsende. Sonst endete die
    Bindung mitten im Text (z. B. zwischen ``N`` und ``H`` von ``NH``).
    """
    if molecule.degree(atom_id) != 1:
        return Point2D()
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        return Point2D()
    neighbors = molecule.neighbors(atom_id)
    if not neighbors:
        return Point2D()
    away = molecule.atom(atom_id).position - molecule.atom(neighbors[0]).position
    length = away.length
    if length < 1e-9:
        return Point2D()
    away = away / length

    if abs(away.x) >= abs(away.y):
        sign = 1.0 if away.x >= 0.0 else -1.0
        return Point2D(sign * half_width, 0.0)

    sign = 1.0 if away.y >= 0.0 else -1.0
    text = atom_label(molecule, atom_id)
    # Mehrbuchstabige Labels (Gruppenlabels und automatische H-Anhänge wie
    # ``OH``) setzen ihr erstes Zeichen mittig über die Bindungsachse, der Rest
    # läuft nach rechts weiter. Sonst endete die Bindung neben dem ersten
    # Buchstaben (z. B. links neben dem N von ``NH``). Reine Elementsymbole
    # wie ``Cl`` bleiben weiterhin als Ganzes zentriert.
    is_group_text = bool(molecule.atom(atom_id).label.strip()) or len(text) > len(
        molecule.atom(atom_id).element
    )
    if is_group_text and len(text) > 1:
        # ``half_width`` enthält bereits den weißen Rand.
        ink_half_width = half_width - style.label_padding
        first_width = _first_glyph_width(text, style)
        return Point2D(ink_half_width - first_width / 2.0, sign * half_height)
    # Einzelnes Elementsymbol bleibt mittig unter/über der Bindung.
    return Point2D(0.0, sign * half_height)


def label_center(molecule: Molecule, atom_id: int, style: Style = DEFAULT_STYLE) -> Point2D:
    """Mittelpunkt des gezeichneten Labels (Atomposition plus ``label_offset``)."""
    return molecule.atom(atom_id).position + label_offset(molecule, atom_id, style)


def label_rect(molecule: Molecule, atom_id: int, style: Style = DEFAULT_STYLE) -> QRectF | None:
    """Rechteck des Labels (inkl. Rand) in Szenenkoordinaten.

    Eine vorhandene Ladung wird mit eingeschlossen, damit ein Klick darauf das
    Atom trifft; die Bindungsenden richten sich weiterhin nur nach dem Label.
    """
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        return None
    center = label_center(molecule, atom_id, style)
    rect = QRectF(
        center.x - half_width,
        center.y - half_height,
        2 * half_width,
        2 * half_height,
    )
    for extra in (
        charge_rect(molecule, atom_id, style),
        partial_charge_rect(molecule, atom_id, style),
    ):
        if extra is not None:
            rect = rect.united(extra)
    return rect


def label_extent(
    molecule: Molecule,
    atom_id: int,
    toward: Point2D,
    style: Style = DEFAULT_STYLE,
) -> float:
    """Abstand vom Atomzentrum bis zum Labelrand in Richtung ``toward``.

    ``toward`` ist ein Einheitsvektor; so enden Bindungen genau am Label und
    nicht davor oder darin. Bei endständigen Atomen liegt das Label seitlich
    versetzt – der Versatz wird mitprojiziert, damit die Bindung dort ebenso
    korrekt endet.
    """
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        return 0.0
    offset = label_offset(molecule, atom_id, style)
    projected = offset.x * toward.x + offset.y * toward.y
    return max(0.0, projected + _rounded_extent(half_width, half_height, toward))


def bond_end_inset(
    molecule: Molecule,
    atom_id: int,
    toward: Point2D,
    style: Style = DEFAULT_STYLE,
) -> float:
    """Abstand vom Atomzentrum, an dem eine Bindung zu enden hat.

    Die Linie wird mit ``RoundCap`` gezeichnet. Damit die runde Kappe nicht
    wieder halb von der weißen Label-Maske überdeckt wird (das ergäbe den
    typischen „gerade abgeschnittenen“ Bindungsabschluss), endet die Linie um
    den Kappenradius – die halbe Strichbreite – früher. Zusätzlich sorgt
    ``style.bond_label_gap`` für einen sichtbaren Abstand zum Text. Ohne Label
    bleibt der Wert 0: dort bleibt die Bindung bis zum Atomzentrum stehen.
    """
    half_width, half_height = label_half_size(molecule, atom_id, style)
    if half_width <= 0.0 or half_height <= 0.0:
        return 0.0

    extent = label_extent(molecule, atom_id, toward, style)
    return extent + style.bond_label_gap + style.bond_width / 2.0


def _trim(segment: tuple[Point2D, Point2D], start_length: float, end_length: float) -> tuple[Point2D, Point2D]:
    """Kürzt ein Segment um absolute Längen an beiden Enden."""
    start, end = segment
    delta = end - start
    length = delta.length
    if length < 1e-6:
        return segment
    direction = delta / length
    trim_start = min(max(start_length, 0.0), length * 0.45)
    trim_end = min(max(end_length, 0.0), length * 0.45)
    return start + direction * trim_start, end - direction * trim_end


def _shorten_side_line(
    segment: tuple[Point2D, Point2D],
    amount: float,
) -> tuple[Point2D, Point2D]:
    """Kürzt die seitliche Doppelbindungslinie an beiden Enden um ``amount``.

    Der Schnitt ist auf ``MAX_SIDE_TRIM_FACTOR`` der Linienlänge begrenzt,
    damit kurze Bindungen (z. B. neben einem Label) nicht fast verschwinden.
    """
    start, end = segment
    length = start.distance_to(end)
    trim = min(amount, length * MAX_SIDE_TRIM_FACTOR)
    return _trim(segment, trim, trim)


def _bond_extents(
    molecule: Molecule,
    bond: Bond,
    style: Style,
) -> tuple[Point2D, Point2D, Point2D, Point2D] | None:
    """Anfang, Ende, Richtung und Normale einer Bindung.

    Die Enden sind bereits an den Atomlabels gekürzt (``bond_end_inset``).
    Liefert ``None``, wenn ein Atom fehlt oder die Bindung zu kurz ist.
    """
    try:
        start_position = molecule.atom(bond.a).position
        end_position = molecule.atom(bond.b).position
    except KeyError:  # pragma: no cover - inkonsistentes Modell
        return None

    delta = end_position - start_position
    total = delta.length
    if total < 1e-6:
        return None
    direction = delta / total
    normal = Point2D(-direction.y, direction.x)

    trim_start = bond_end_inset(molecule, bond.a, direction, style)
    trim_end = bond_end_inset(molecule, bond.b, -direction, style)
    if total <= trim_start + trim_end + 2.0:
        trim_start = trim_end = 0.0

    start = start_position + direction * trim_start
    end = end_position - direction * trim_end
    return start, end, direction, normal


def bond_segments(molecule: Molecule, bond: Bond, style: Style = DEFAULT_STYLE) -> list[tuple[Point2D, Point2D]]:
    """Liniensegmente einer Bindung (inkl. Doppel-/Dreifachbindung und Label-Lücken).

    Doppelbindungen gibt es zentriert (beide Linien symmetrisch zur Achse,
    gleich lang) und einseitig (Hauptlinie auf der Achse, die seitliche Linie
    ist etwas kürzer und liegt im Ring innen).
    """
    extents = _bond_extents(molecule, bond, style)
    if extents is None:
        return []
    start, end, _direction, normal = extents

    if bond.order <= 1:
        return [(start, end)]

    gap = style.double_bond_offset if bond.order == 2 else style.triple_bond_offset

    if bond.order == 2 and bond.centered:
        # Zentriert: beide Linien liegen symmetrisch zur Bindungsachse und
        # sind gleich lang (Hauptlinie auf der Achse entfällt).
        offset = normal * (gap / 2.0)
        return [(start + offset, end + offset), (start - offset, end - offset)]

    # Die seitliche Linie ist an beiden Enden etwas kürzer als die Hauptlinie.
    corner = gap * 0.55
    cycle = molecule.shortest_cycle(bond)
    if cycle is not None:
        # Im Ring liegt die Hauptlinie auf der Kante, die zusätzliche Linie
        # wird zur Ringmitte hin versetzt und an den Ecken gekürzt. Die Seite
        # kommt aus dem kürzesten Ringweg (nicht aus der Reihenfolge der
        # Nachbarbindungen) – so liegen alle Benzol-Doppelbindungen innen.
        side = bond.side if bond.side != 0 else default_double_bond_side(
            molecule, bond, cycle
        )
        if side == 0:
            side = 1
        offset = normal * (gap * side)
        if bond.order == 2:
            return [(start, end), _shorten_side_line((start + offset, end + offset), corner)]
        return [
            (start, end),
            _shorten_side_line((start + offset, end + offset), corner),
            _shorten_side_line((start - offset, end - offset), corner),
        ]

    # Kette: Hauptlinie auf der Bindungsachse, die zweite Linie liegt auf der
    # gewählten (bzw. positiven) Seite und endet etwas vor der Hauptlinie.
    if bond.order == 2:
        side = bond.side if bond.side != 0 else 1
        offset = normal * (gap * side)
        return [(start, end), _shorten_side_line((start + offset, end + offset), corner)]

    offset = normal * (gap / 2.0)
    return [(start, end), (start + offset, end + offset), (start - offset, end - offset)]


# -- Keilstrich (Stereobindungen) ----------------------------------------
def wedge_triangle(start: Point2D, end: Point2D, width: float) -> QPolygonF:
    """Gefülltes Dreieck eines Keils: Spitze bei ``start``, Breite bei ``end``."""
    delta = end - start
    length = delta.length
    if length < 1e-6:
        return QPolygonF()
    normal = Point2D(-delta.y / length, delta.x / length)
    half = width / 2.0
    return QPolygonF(
        [
            to_qpoint(start),
            to_qpoint(end + normal * half),
            to_qpoint(end - normal * half),
        ]
    )


def hashed_wedge_lines(
    start: Point2D,
    end: Point2D,
    width: float,
    spacing: float,
) -> list[tuple[Point2D, Point2D]]:
    """Querstriche eines Strichkeils – die Breite wächst zur breiten Seite."""
    delta = end - start
    length = delta.length
    if length < 1e-6:
        return []
    normal = Point2D(-delta.y / length, delta.x / length)
    count = max(3, round(length / max(spacing, 1.0)))
    lines: list[tuple[Point2D, Point2D]] = []
    for index in range(1, count + 1):
        ratio = index / count
        center = start + delta * ratio
        half = width * 0.5 * ratio
        lines.append((center + normal * half, center - normal * half))
    return lines


def stereo_bond_ends(
    molecule: Molecule,
    bond: Bond,
    style: Style = DEFAULT_STYLE,
) -> tuple[Point2D, Point2D] | None:
    """Schmale Spitze und breite Mitte einer Keilbindung (oder ``None``)."""
    if bond.stereo is BondStereo.NONE:
        return None
    extents = _bond_extents(molecule, bond, style)
    if extents is None:
        return None
    start, end = extents[0], extents[1]
    return (start, end) if bond.narrow_atom == bond.a else (end, start)


def stereo_bond_triangle(
    molecule: Molecule,
    bond: Bond,
    style: Style = DEFAULT_STYLE,
) -> QPolygonF | None:
    """Dreieck einer Keilbindung (``None`` bei Strichkeil oder ohne Stereo)."""
    if bond.stereo is not BondStereo.WEDGE:
        return None
    ends = stereo_bond_ends(molecule, bond, style)
    if ends is None:
        return None
    narrow, wide = ends
    return wedge_triangle(narrow, wide, style.wedge_width)


def stereo_bond_hatches(
    molecule: Molecule,
    bond: Bond,
    style: Style = DEFAULT_STYLE,
) -> list[tuple[Point2D, Point2D]]:
    """Querstriche einer Strichkeilbindung (leer, wenn keine)."""
    if bond.stereo is not BondStereo.HASHED:
        return []
    ends = stereo_bond_ends(molecule, bond, style)
    if ends is None:
        return []
    narrow, wide = ends
    return hashed_wedge_lines(narrow, wide, style.wedge_width, style.wedge_hatch_spacing)


def paint_bond(
    painter: QPainter,
    molecule: Molecule,
    bond: Bond,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Zeichnet eine Bindung – als Linie(n), Keil oder Strichkeil."""
    color = qcolor(bond.color or style.bond_color)
    if bond.stereo is BondStereo.WEDGE:
        triangle = stereo_bond_triangle(molecule, bond, style)
        if triangle is not None and not triangle.isEmpty():
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawPolygon(triangle)
            painter.restore()
            return
    elif bond.stereo is BondStereo.HASHED:
        hatches = stereo_bond_hatches(molecule, bond, style)
        if hatches:
            painter.save()
            painter.setPen(
                QPen(
                    color,
                    style.bond_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for start, end in hatches:
                painter.drawLine(to_qpoint(start), to_qpoint(end))
            painter.restore()
            return

    painter.setPen(
        QPen(
            color,
            style.bond_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for segment_start, segment_end in bond_segments(molecule, bond, style):
        painter.drawLine(to_qpoint(segment_start), to_qpoint(segment_end))


def _paint_selection(
    painter: QPainter,
    molecule: Molecule,
    selection: frozenset[int],
    style: Style,
) -> None:
    if not selection:
        return
    color = qcolor(style.selection_color, style.selection_alpha)
    pen = QPen(
        color,
        style.selection_width,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for bond in molecule.bonds:
        if bond.a in selection or bond.b in selection:
            painter.drawLine(
                to_qpoint(molecule.atom(bond.a).position),
                to_qpoint(molecule.atom(bond.b).position),
            )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    radius = style.bond_length * SELECTION_RADIUS_FACTOR
    for atom_id in selection:
        if atom_id in molecule:
            painter.drawEllipse(to_qpoint(label_center(molecule, atom_id, style)), radius, radius)


def _text_context(
    style: Style,
    color: RGB | None = None,
) -> QAbstractTextDocumentLayout.PaintContext:
    """PaintContext mit expliziter Textfarbe – ohne Palette zeichnet Qt nichts."""
    context = QAbstractTextDocumentLayout.PaintContext()
    palette = context.palette
    palette.setColor(QPalette.ColorRole.Text, qcolor(color or style.bond_color))
    context.palette = palette
    return context


@lru_cache(maxsize=256)
def _rich_label_ink(
    markup: str,
    family: str,
    pixel_size: int,
) -> tuple[float, float, float, float]:
    """Tinten-Bounding-Box eines Rich-Text-Labels: ``(x, y, Breite, Höhe)``.

    ``QTextDocument`` meldet als Größe die komplette Zeilenhöhe inklusive
    Durchschuss. Für Label-Maske und Bindungsenden zählt aber nur der
    tatsächlich gezeichnete Bereich – sonst sitzt ein Gruppenlabel (z. B.
    ``OTs``) weiter von der Bindung entfernt als ein Elementlabel wie ``O``.
    """
    document = _text_document(markup, family, pixel_size)
    size = document.size()
    width = max(1, math.ceil(size.width()) + 2)
    height = max(1, math.ceil(size.height()) + 2)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.translate(1.0, 1.0)
        document.drawContents(painter)
    finally:
        painter.end()

    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return 0.0, 0.0, 0.0, 0.0
    return float(left), float(top), float(right - left + 1), float(bottom - top + 1)


def _label_mask_rect(
    center: QPointF,
    half_width: float,
    half_height: float,
) -> QRectF:
    """Rechteck der weißen Label-Maske (Kapsel) um ``center``."""
    return QRectF(
        center.x() - half_width,
        center.y() - half_height,
        2.0 * half_width,
        2.0 * half_height,
    )


def _paint_label_mask(painter: QPainter, mask: QRectF, style: Style) -> None:
    """Zeichnet die weiße, kapselförmige Maske hinter einem Atomlabel."""
    radius = min(mask.width(), mask.height()) / 2.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(qcolor(style.background)))
    painter.drawRoundedRect(mask, radius, radius)


def _paint_rich_atom_label(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int,
    document: QTextDocument,
    style: Style,
) -> None:
    """Zeichnet ein Label mit Hoch-/Tiefstellung zentriert auf das Label-Zentrum."""
    markup = atom_label_markup(molecule, atom_id)
    ink_x, ink_y, ink_width, ink_height = _rich_label_ink(
        markup, style.label_font_family, style.label_pixel_size
    )
    center = to_qpoint(label_center(molecule, atom_id, style))
    padding = style.label_padding
    half_width = ink_width / 2.0 + padding
    half_height = ink_height / 2.0 + padding
    mask = _label_mask_rect(center, half_width, half_height)
    _paint_label_mask(painter, mask, style)

    painter.save()
    # Dokument so verschieben, dass seine Tintenfläche mittig in der Maske sitzt.
    painter.translate(mask.x() + padding - ink_x, mask.y() + padding - ink_y)
    document.documentLayout().draw(
        painter, _text_context(style, _label_color(molecule, atom_id, style))
    )
    painter.restore()


def _paint_atom_label(painter: QPainter, molecule: Molecule, atom_id: int, style: Style) -> None:
    document = _atom_label_document(molecule, atom_id, style)
    if document is not None:
        _paint_rich_atom_label(painter, molecule, atom_id, document, style)
    else:
        text = atom_label(molecule, atom_id)
        if text:
            _paint_plain_atom_label(painter, molecule, atom_id, text, style)
    paint_atom_charge(painter, molecule, atom_id, style)
    paint_atom_partial_charge(painter, molecule, atom_id, style)


def _paint_plain_atom_label(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int,
    text: str,
    style: Style,
) -> None:
    """Zeichnet ein einfaches Elementsymbol mittig auf das Label-Zentrum."""
    center = to_qpoint(label_center(molecule, atom_id, style))
    width, height, cap_height, advance = _text_metrics(
        style.label_font_family, style.label_pixel_size, text
    )
    padding = style.label_padding

    half_width = width / 2.0 + padding
    half_height = height / 2.0 + padding
    mask = _label_mask_rect(center, half_width, half_height)
    # Kapselform: passend zur abgerundeten Label-Ausdehnung (``bond_end_inset``).
    _paint_label_mask(painter, mask, style)

    painter.setFont(_font(style))
    painter.setPen(QPen(qcolor(_label_color(molecule, atom_id, style))))
    # Baseline so legen, dass die Glyphen vertikal im Atomzentrum sitzen.
    baseline = QPointF(center.x() - advance / 2.0, center.y() + cap_height / 2.0)
    painter.drawText(baseline, text)


def paint_molecule(
    painter: QPainter,
    molecule: Molecule,
    style: Style = DEFAULT_STYLE,
    selection: frozenset[int] | set[int] | None = None,
) -> None:
    """Zeichnet das komplette Molekül in den aktuellen Painter-Kontext."""
    if molecule.is_empty():
        return
    selected: frozenset[int] = frozenset(selection or ())

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    _paint_selection(painter, molecule, selected, style)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    for bond in molecule.bonds:
        paint_bond(painter, molecule, bond, style)

    for atom_id in molecule.atom_ids():
        _paint_atom_label(painter, molecule, atom_id, style)
        paint_electrons(painter, molecule, atom_id, style)

    painter.restore()


def paint_hover_atom(
    painter: QPainter,
    molecule: Molecule,
    atom_id: int | None,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Markiert das Atom, auf dem ein Klick einrasten würde.

    Rein visueller Hinweis: ein Ring um das Label (bzw. ein Kreis um
    unbeschriftete Atome), damit man sieht, dass ein Klick an dieser Stelle
    sicher auf dem Atom bzw. Bindungsende landet.
    """
    if atom_id is None or atom_id not in molecule:
        return

    color = qcolor(style.preview_color, style.hover_alpha)
    pen = QPen(color)
    pen.setCosmetic(True)
    pen.setWidthF(style.preview_width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    rect = label_rect(molecule, atom_id, style)
    if rect is not None:
        radius = min(rect.width(), rect.height()) / 2.0
        painter.drawRoundedRect(rect, radius, radius)
        return

    center = to_qpoint(molecule.atom(atom_id).position)
    radius = style.bond_length * 0.3
    painter.drawEllipse(center, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawEllipse(center, style.bond_length * 0.08, style.bond_length * 0.08)


def paint_hover_bond(
    painter: QPainter,
    molecule: Molecule,
    bond: Bond | None,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Hebt die Bindung unter dem Cursor hervor.

    Ein breiter, halbtransparenter Strich liegt über der Bindung – so sieht man
    vor dem Klick, dass dieser Klick die Bindungsordnung ändert.
    """
    if bond is None or bond.a not in molecule or bond.b not in molecule:
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(
        qcolor(style.preview_color, style.bond_hover_alpha),
        style.bond_width * 4.0,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for start, end in bond_segments(molecule, bond, style):
        painter.drawLine(to_qpoint(start), to_qpoint(end))
    painter.restore()


# -- Freie Objekte: Text und Pfeile --------------------------------------
@lru_cache(maxsize=256)
def _text_document(markup: str, family: str, pixel_size: int) -> QTextDocument:
    """Layout-Dokument für ein Textobjekt (gecacht)."""
    document = QTextDocument()
    document.setDocumentMargin(0.0)
    font = QFont(family)
    font.setPixelSize(pixel_size)
    document.setDefaultFont(font)
    document.setHtml(f"<div>{markup_to_html(markup)}</div>")
    return document


def text_size(markup: str, style: Style = DEFAULT_STYLE) -> QSizeF:
    """Gerenderte Größe einer Beschriftung in Szeneneinheiten."""
    document = _text_document(markup, style.text_font_family, style.text_pixel_size)
    return document.size()


def text_bounds(obj: TextObject, style: Style = DEFAULT_STYLE) -> QRectF:
    """Rechteck einer Beschriftung (Szeneneinheiten) – für Hit-Tests und Bounds."""
    size = text_size(obj.markup, style)
    return QRectF(obj.position.x, obj.position.y, size.width(), size.height())


def paint_text(painter: QPainter, obj: TextObject, style: Style = DEFAULT_STYLE) -> None:
    """Zeichnet eine Beschriftung inkl. hoch-/tiefgestellter Abschnitte."""
    if obj.is_blank():
        return
    document = _text_document(obj.markup, style.text_font_family, style.text_pixel_size)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.translate(obj.position.x, obj.position.y)
    document.documentLayout().draw(
        painter, _text_context(style, obj.color)
    )
    painter.restore()


def _equilibrium_arrow(arrow: ArrowObject) -> ArrowObject:
    """Richtet einen Gleichgewichtspfeil kanonisch aus.

    Waagerechte Pfeile werden immer von links nach rechts aufgebaut, damit das
    Symbol unabhängig von der Ziehrichtung wie ⇌ aussieht (oben rechts, unten
    links). Senkrechte Pfeile werden entsprechend von oben nach unten gedreht.
    """
    if arrow.kind is not ArrowKind.EQUILIBRIUM:
        return arrow
    vector = arrow.vector
    if abs(vector.x) >= abs(vector.y):
        if vector.x < 0:
            return replace(arrow, start=arrow.end, end=arrow.start)
    elif vector.y < 0:
        return replace(arrow, start=arrow.end, end=arrow.start)
    return arrow


def _equilibrium_gap(arrow: ArrowObject, style: Style) -> Point2D:
    """Versatz der beiden Linien; die obere Linie liegt auf dem Bildschirm oben."""
    normal = arrow.normal
    if normal.y > 0:
        normal = -normal
    return normal * (style.arrow_gap / 2.0)


def _head_scale(arrow: ArrowObject, style: Style) -> float:
    """Größenfaktor der Pfeilspitzen (Gleichgewichtsspitzen sind kleiner)."""
    if arrow.kind is ArrowKind.EQUILIBRIUM:
        return style.equilibrium_head_scale
    return 1.0


def arrow_shafts(
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> tuple[tuple[Point2D, Point2D], ...]:
    """Liniensegmente eines Pfeils (bei Gleichgewicht zwei parallele Linien).

    Die Linien enden leicht **in** der gefüllten Spitze, damit der gerade
    Linienabschluss nicht über die Dreiecksspitze hinausragt.
    """
    head_length = style.arrow_head_length * _head_scale(arrow, style)
    if arrow.kind is ArrowKind.FORWARD:
        # Die Linie verschwindet unter der symmetrischen Spitze.
        overlap = head_length * 0.85
        return ((arrow.start, arrow.end - arrow.direction * overlap),)
    # Halbe Spitzen: die Linie endet exakt an der Spitzenbasis, damit sie nicht
    # unter dem Widerhaken hervorschaut.
    overlap = head_length
    arrow = _equilibrium_arrow(arrow)
    gap = _equilibrium_gap(arrow, style)
    return (
        (
            arrow.start + gap,
            arrow.end + gap - arrow.direction * overlap,
        ),
        (
            arrow.end - gap,
            arrow.start - gap + arrow.direction * overlap,
        ),
    )


def arrow_heads(
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> tuple[tuple[Point2D, Point2D], ...]:
    """(Spitze, Richtung) aller Pfeilspitzen.

    Beim Gleichgewicht sitzen die Spitzen an den **äußeren** Enden: oben rechts,
    unten links (bzw. gespiegelt bei einem nach links gezogenen Pfeil).
    """
    if arrow.kind is ArrowKind.FORWARD:
        return ((arrow.end, arrow.direction),)
    arrow = _equilibrium_arrow(arrow)
    gap = _equilibrium_gap(arrow, style)
    return (
        (arrow.end + gap, arrow.direction),
        (arrow.start - gap, -arrow.direction),
    )


def arrow_head_polygon(
    tip: Point2D,
    direction: Point2D,
    style: Style = DEFAULT_STYLE,
    scale: float = 1.0,
    barb: Point2D | None = None,
) -> QPolygonF:
    """Gefüllte Pfeilspitze.

    Ohne ``barb`` entsteht ein symmetrisches Dreieck (Reaktionspfeil). Mit
    ``barb`` als Einheitsvektor wird eine **halbe** Spitze gezeichnet: eine Kante
    liegt auf der Linie, der Widerhaken zeigt in Richtung ``barb`` (⇌-Symbol).
    """
    normal = Point2D(-direction.y, direction.x)
    base = tip - direction * style.arrow_head_length * scale
    half = style.arrow_head_width * scale / 2.0
    if barb is None:
        return QPolygonF(
            [
                to_qpoint(tip),
                to_qpoint(base + normal * half),
                to_qpoint(base - normal * half),
            ]
        )
    # Halbe Spitze (Harpune): Die flache Seite liegt bündig auf der Innenkante
    # der Linie, der Widerhaken wächst von dort nach außen. Die Spitze selbst
    # sitzt mittig auf der Linie – so entsteht kein Versatz an der Basis.
    inner = base - barb * (style.bond_width / 2.0)
    outer = inner + barb * (style.bond_width + half * 2.0)
    return QPolygonF(
        [
            to_qpoint(tip),
            to_qpoint(inner),
            to_qpoint(outer),
        ]
    )


def paint_arrow(painter: QPainter, arrow: ArrowObject, style: Style = DEFAULT_STYLE) -> None:
    """Zeichnet einen Reaktionspfeil (→, ⇌) oder einen Elektronenfluss-Pfeil."""
    if arrow.length < 1e-6:
        return
    if arrow.is_flow:
        paint_flow_arrow(painter, arrow, style)
        return

    color = qcolor(arrow.color or style.bond_color)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(
        QPen(
            color,
            style.bond_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
            Qt.PenJoinStyle.MiterJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for start, end in arrow_shafts(arrow, style):
        painter.drawLine(to_qpoint(start), to_qpoint(end))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    head_scale = _head_scale(arrow, style)
    heads = arrow_heads(arrow, style)
    if arrow.kind is ArrowKind.EQUILIBRIUM:
        # Zwei einseitige halbe Spitzen: der Widerhaken zeigt jeweils nach außen.
        outward = _equilibrium_gap(arrow, style).normalized()
        for (tip, direction), barb in zip(heads, (outward, -outward), strict=True):
            painter.drawPolygon(
                arrow_head_polygon(tip, direction, style, head_scale, barb)
            )
    else:
        for tip, direction in heads:
            painter.drawPolygon(arrow_head_polygon(tip, direction, style, head_scale))

    painter.restore()


def arrow_path(arrow: ArrowObject, trim_end: float = 0.0) -> QPainterPath:
    """Pfeilpfad als Qt-Pfad – gerade Linie oder Folge von Kreisbögen.

    ``trim_end`` kürzt den Pfad am Pfeilende um diese Bogenlänge, damit der
    Schaft nicht unter einer gefüllten Spitze hervorlugt.
    """
    arcs = arrow.arcs
    path = QPainterPath()
    if not arcs:
        end = arrow.end
        if trim_end > 0.0 and arrow.length > 1e-9:
            end = arrow.end - arrow.direction * min(trim_end, arrow.length)
        path.moveTo(to_qpoint(arrow.start))
        path.lineTo(to_qpoint(end))
        return path

    path.moveTo(to_qpoint(arcs[0].point_at_angle(arcs[0].start_angle)))
    for index, arc in enumerate(arcs):
        end_angle = arc.end_angle
        if index == len(arcs) - 1 and trim_end > 0.0:
            # Nie über den Anfang hinaus kürzen (kurze Pfeile).
            end_angle = arc.angle_from_end(min(trim_end, arc.length * 0.95))
        rect = QRectF(
            arc.center.x - arc.radius,
            arc.center.y - arc.radius,
            2.0 * arc.radius,
            2.0 * arc.radius,
        )
        path.arcTo(
            rect,
            -math.degrees(arc.start_angle),
            -math.degrees(end_angle - arc.start_angle),
        )
    return path


def _flow_head_frame(
    arrow: ArrowObject,
    style: Style,
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    """Rahmen der Spitze: ``(Tip, Basis, Normale, Tangente)``.

    Bei gebogenen Pfeilen liegt die Basis der Spitze auf demselben Kreisbogen
    wie der Schaft. Dadurch dreht die Spitze mit der Krümmung mit, statt
    schief am Pfeilende zu sitzen.
    """
    tip = arrow.end
    arcs = arrow.arcs
    length = style.arrow_head_length
    if not arcs:
        tangent = arrow.direction
        base = tip - tangent * length
        return tip, base, Point2D(-tangent.y, tangent.x), tangent
    arc = arcs[-1]
    tangent = arc.tangent(1.0)
    base = arc.point_from_end(length)
    base_tangent = arc.tangent_from_end(length)
    return tip, base, Point2D(-base_tangent.y, base_tangent.x), tangent


def flow_arrow_head(
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> QPolygonF:
    """Gefüllte Spitze eines gebogenen Pfeils (Elektronenpaar).

    Die Basis der Spitze liegt auf dem Kreisbogen des Pfeils. Dadurch dreht die
    Spitze mit der Krümmung mit, statt schief am Pfeilende zu sitzen.
    """
    tip, base, normal, _tangent = _flow_head_frame(arrow, style)
    half_width = style.arrow_head_width / 2.0
    return QPolygonF(
        [
            to_qpoint(tip),
            to_qpoint(base + normal * half_width),
            to_qpoint(base - normal * half_width),
        ]
    )


def radical_barb(
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> Point2D:
    """Endpunkt des einzelnen Widerhakens eines Radikal-Pfeils.

    Der Widerhaken beginnt exakt an der Pfeilspitze und läuft von dort nach
    hinten und auf die Außenseite der Krümmung. Auf der Innenseite würde er
    optisch mit dem Schaft verschmelzen.
    """
    tip = arrow.end
    tangent = arrow.end_direction
    normal = Point2D(-tangent.y, tangent.x)
    side = -1.0
    arcs = arrow.arcs
    if arcs:
        to_center = arcs[-1].center - tip
        side = -1.0 if to_center.x * normal.x + to_center.y * normal.y >= 0.0 else 1.0
    return (
        tip
        - tangent * style.arrow_head_length
        + normal * (side * style.arrow_head_width)
    )


def paint_flow_arrow(
    painter: QPainter,
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Zeichnet einen gebogenen Elektronenfluss-Pfeil.

    Elektronenpaar: volle, gefüllte Spitze, die der Krümmung folgt. Radikal:
    halbe Spitze („Fischhaken“) – daran erkennt man den Transfer eines
    einzelnen Elektrons.
    """
    if arrow.length < 1e-6:
        return
    color = qcolor(arrow.color or style.bond_color)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(
        QPen(
            color,
            style.bond_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if arrow.kind is ArrowKind.RADICAL_FLOW:
        # Klassischer Fischhaken: Der Schaft endet mit seiner Rundkappe exakt
        # an der Spitze, der einzelne Widerhaken setzt dort an.
        painter.drawPath(arrow_path(arrow, trim_end=style.bond_width / 2.0))
        painter.setPen(
            QPen(
                color,
                style.bond_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.FlatCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawLine(
            to_qpoint(arrow.end),
            to_qpoint(radical_barb(arrow, style)),
        )
    else:
        painter.drawPath(arrow_path(arrow, trim_end=style.arrow_head_length * 0.9))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(flow_arrow_head(arrow, style))
    painter.restore()


def paint_text_selection(
    painter: QPainter,
    obj: TextObject,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Heller Rahmen hinter einer ausgewählten Beschriftung."""
    padding = style.label_padding * 2.0
    rect = text_bounds(obj, style).adjusted(-padding, -padding, padding, padding)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(qcolor(style.selection_color, style.selection_alpha)))
    painter.drawRoundedRect(rect, padding, padding)
    painter.restore()


def paint_arrow_selection(
    painter: QPainter,
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Helles Band hinter einem ausgewählten Pfeil."""
    if arrow.length < 1e-6:
        return
    painter.save()
    painter.setPen(
        QPen(
            qcolor(style.selection_color, style.selection_alpha),
            style.selection_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(arrow_path(arrow))
    painter.restore()


def arrow_curve_handle(arrow: ArrowObject) -> Point2D | None:
    """Greifpunkt für die Krümmung (Mitte der Kurve); ``None`` bei geraden Pfeilen."""
    if not arrow.is_flow or arrow.length < 1e-6:
        return None
    return arrow.curve_midpoint


def paint_arrow_handles(
    painter: QPainter,
    arrow: ArrowObject,
    style: Style = DEFAULT_STYLE,
) -> None:
    """Greifpunkte an beiden Enden und (bei Bögen) für die Krümmung."""
    radius = style.bond_length * ARROW_HANDLE_FACTOR
    painter.save()
    painter.setPen(QPen(qcolor(style.background), style.bond_width))
    painter.setBrush(QBrush(qcolor(style.selection_color)))
    for point in (arrow.start, arrow.end):
        painter.drawEllipse(to_qpoint(point), radius, radius)
    handle = arrow_curve_handle(arrow)
    if handle is not None:
        painter.setPen(QPen(qcolor(style.selection_color), style.bond_width))
        painter.setBrush(QBrush(qcolor(style.background)))
        painter.drawEllipse(to_qpoint(handle), radius * 0.8, radius * 0.8)
    painter.restore()


def paint_scene(
    painter: QPainter,
    molecule: Molecule | None = None,
    texts: tuple[TextObject, ...] = (),
    arrows: tuple[ArrowObject, ...] = (),
    style: Style = DEFAULT_STYLE,
    selection: frozenset[int] | set[int] | None = None,
    text_selection: frozenset[int] | set[int] | None = None,
    arrow_selection: frozenset[int] | set[int] | None = None,
) -> None:
    """Zeichnet Molekül, Pfeile und Texte in der richtigen Reihenfolge."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    selected_texts = set(text_selection or ())
    selected_arrows = set(arrow_selection or ())

    if molecule is not None and not molecule.is_empty():
        paint_molecule(painter, molecule, style, selection)
    for index, arrow in enumerate(arrows):
        if index in selected_arrows:
            paint_arrow_selection(painter, arrow, style)
        paint_arrow(painter, arrow, style)
    for index, text in enumerate(texts):
        if index in selected_texts:
            paint_text_selection(painter, text, style)
        paint_text(painter, text, style)
    for index, arrow in enumerate(arrows):
        if index in selected_arrows:
            paint_arrow_handles(painter, arrow, style)
    painter.restore()
