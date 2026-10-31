"""Werkzeuge (Tools) für den Canvas.

Ein Werkzeug bekommt Mausereignisse in Szenenkoordinaten und darf einen
Vorschau-Overlay zeichnen. Alle Änderungen am Molekül laufen über
``Document.edit``/``begin_edit``/``commit_edit``, damit Undo korrekt bleibt.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from ..core.annotations import (
    DEFAULT_FLOW_BOW,
    FLOW_KINDS,
    MAX_FLOW_BOW,
    MAX_FLOW_BOW_ALONG,
    ArrowKind,
    ArrowObject,
    TextObject,
    resize_flow_arrow,
)
from ..core.elements import DEFAULT_ELEMENT
from ..core.geometry import (
    SNAP_STEP_DEG,
    Point2D,
    angle_between,
    clamp,
    distance_to_segment,
    polar,
    snap_to_grid_angle,
)
from ..core.molecule import Bond, BondStereo
from ..core.templates import BENZENE, RingTemplate
from ..render.painter import (
    ARROW_HANDLE_FACTOR,
    SELECTION_RADIUS_FACTOR,
    arrow_curve_handle,
    arrow_path,
    arrow_shafts,
    atom_label,
    electron_anchor,
    electron_hit,
    electron_preview,
    hashed_wedge_lines,
    label_center,
    label_half_size,
    label_rect,
    qcolor,
    text_bounds,
    to_qpoint,
    wedge_triangle,
)
from ..render.style import DEFAULT_STYLE, Style
from .charge_dialog import ChargeDialog

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtGui import QMouseEvent

    from ..document.document import Document
    from ..core.molecule import Molecule


class Tool(QObject):
    """Basisklasse aller Werkzeuge."""

    changed = Signal()
    """Werkzeug möchte neu gezeichnet werden (z. B. nach einem Timer)."""

    name = "Werkzeug"
    hint = ""
    cursor = Qt.CursorShape.ArrowCursor
    highlights_snap_atom = False
    """Hover-Ring um Atome zeigen, auf denen ein Klick einrasten würde."""
    highlights_bond = False
    """Bindung unter dem Cursor hervorheben (Klick ändert die Bindungsordnung)."""

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._document = document
        self._style = style
        self._snap_atom: int | None = None
        self._bond_hover: Bond | None = None

    @property
    def snap_atom(self) -> int | None:
        """Atom unter dem Cursor, auf dem ein Klick einrasten würde."""
        return self._snap_atom

    @property
    def hovered_bond(self) -> Bond | None:
        """Bindung unter dem Cursor (nur bei Werkzeugen mit ``highlights_bond``)."""
        return self._bond_hover

    # -- Lebenszyklus ----------------------------------------------------
    def activate(self) -> None:
        """Werkzeug wurde ausgewählt."""

    def deactivate(self) -> None:
        """Werkzeug wird gewechselt – laufende Aktionen abbrechen."""
        self._snap_atom = None
        self._bond_hover = None
        self._document.cancel_edit()

    def set_style(self, style: Style) -> None:
        """Übernimmt einen geänderten Zeichenstil (Einstellungen)."""
        self._style = style

    # -- Ereignisse (True => Canvas neu zeichnen) ------------------------
    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        return False

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        atom_changed = self._update_snap_hover(position)
        bond_changed = self._update_bond_hover(position)
        return atom_changed or bond_changed

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        return False

    def mouse_double_click(self, position: Point2D, event: "QMouseEvent") -> bool:
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        """Vorschau zeichnen (Szenenkoordinaten)."""

    # -- Hilfen ----------------------------------------------------------
    @property
    def hit_radius(self) -> float:
        return self._style.hit_radius

    @property
    def molecule(self) -> "Molecule":
        return self._document.molecule

    @property
    def page_bounds(self) -> tuple[Point2D, Point2D]:
        """Linke obere und rechte untere Ecke des Blatts."""
        return self._document.page.bounds

    def is_on_page(self, position: Point2D, margin: float = 0.0) -> bool:
        """Liegt ``position`` (mit optionalem Rand) auf dem Blatt?"""
        low, high = self.page_bounds
        return (
            low.x - margin <= position.x <= high.x + margin
            and low.y - margin <= position.y <= high.y + margin
        )

    def clamp_to_page(self, position: Point2D, margin: float = 0.0) -> Point2D:
        """Begrenzt eine Position auf das Blatt (mit optionalem Rand)."""
        low, high = self.page_bounds
        return Point2D(
            clamp(position.x, low.x + margin, high.x - margin),
            clamp(position.y, low.y + margin, high.y - margin),
        )

    def all_on_page(self, positions: list[Point2D]) -> bool:
        return all(self.is_on_page(position) for position in positions)

    def _find_atom(self, position: Point2D) -> int | None:
        molecule = self._document.molecule
        atom_id = molecule.find_atom_near(position, self.hit_radius)
        if atom_id is not None:
            return atom_id
        # Endständige Labels liegen neben dem Atomzentrum und müssen trotzdem
        # als Atom treffbar bleiben (Label anklicken = Atom anklicken).
        for candidate in reversed(molecule.atom_ids()):
            rect = label_rect(molecule, candidate, self._style)
            if rect is not None and rect.contains(to_qpoint(position)):
                return candidate
        return None

    def _update_snap_hover(self, position: Point2D) -> bool:
        """Aktualisiert das Einrast-Ziel unter dem Cursor (``True`` = neu zeichnen)."""
        atom_id = self._find_atom(position) if self.highlights_snap_atom else None
        if atom_id == self._snap_atom:
            return False
        self._snap_atom = atom_id
        return True

    def _update_bond_hover(self, position: Point2D) -> bool:
        """Hebt die Bindung unter dem Cursor hervor (``True`` = neu zeichnen).

        Über den Atomenden (Labels) bleibt die Hervorhebung aus – dort würde
        ein Klick das Atom treffen, nicht die Bindung.
        """
        bond: Bond | None = None
        if self.highlights_bond and self._find_atom(position) is None:
            bond = self.molecule.find_bond_near(position, self.hit_radius * 0.8)
        if bond == self._bond_hover:
            return False
        self._bond_hover = bond
        return True

    def clear_hover(self) -> bool:
        """Entfernt die Hover-Hinweise (``True``, wenn einer sichtbar war)."""
        if self._snap_atom is None and self._bond_hover is None:
            return False
        self._snap_atom = None
        self._bond_hover = None
        return True

    def cycle_bond_at(self, position: Point2D) -> bool:
        """Schaltet die Bindung unter dem Cursor weiter (1→2A→2B→3→1)."""
        bond = self.molecule.find_bond_near(position, self.hit_radius * 0.8)
        if bond is None:
            return False
        self._document.cycle_bond_order(bond)
        return True

    def find_text_index(self, position: Point2D) -> int | None:
        """Index der obersten Beschriftung unter der Maus (``None`` = keine)."""
        texts = self._document.texts
        for index in range(len(texts) - 1, -1, -1):
            if text_bounds(texts[index], self._style).contains(to_qpoint(position)):
                return index
        return None

    def find_text(self, position: Point2D) -> TextObject | None:
        """Oberste Beschriftung unter der Maus (oder ``None``)."""
        index = self.find_text_index(position)
        return None if index is None else self._document.texts[index]

    def find_arrow_index(self, position: Point2D) -> int | None:
        """Index des obersten Pfeils unter der Maus (``None`` = keiner)."""
        tolerance = self.hit_radius * 0.8
        arrows = self._document.arrows
        for index in range(len(arrows) - 1, -1, -1):
            if self._arrow_distance(arrows[index], position) <= tolerance:
                return index
        return None

    @staticmethod
    def _arrow_distance(arrow: ArrowObject, position: Point2D) -> float:
        """Kürzester Abstand zur Pfeillinie (bei Bogen entlang der Kurve)."""
        return min(
            distance_to_segment(position, start, end)
            for start, end in pairwise(arrow.points())
        )

    def find_arrow(self, position: Point2D) -> ArrowObject | None:
        """Oberster Pfeil unter der Maus (oder ``None``)."""
        index = self.find_arrow_index(position)
        return None if index is None else self._document.arrows[index]


class _DirectionChooserTool(Tool):
    """Basis für Werkzeuge mit gehaltener Positionsauswahl.

    Wird die Maustaste auf einem Atom gedrückt gehalten, erscheinen nach
    ``CHOOSER_DELAY_MS`` acht Richtungen rund um das Atom; die markierte
    Richtung folgt der Maus. Beim Loslassen wertet das jeweilige Werkzeug die
    gewählte Richtung aus. Unterklassen liefern in :meth:`_chooser_selection`
    das Atom samt Vergleichspunkt und merken sich dort ihre Zusatzdaten.
    """

    CHOOSER_DELAY_MS = 450
    """Wartezeit, bis die Positionsauswahl beim Halten erscheint."""
    CHOOSER_STEPS = 8
    """Angebotene Richtungen im Kreis um das Atom."""
    OPTION_RADIUS_FACTOR = 0.13
    """Radius eines Positionspunkts relativ zur Bindungslänge."""

    _pending: tuple | None = None

    def __init__(
        self,
        document: "Document",
        style: Style = DEFAULT_STYLE,
        parent: QObject | None = None,
        initial_direction: Point2D | None = None,
    ) -> None:
        super().__init__(document, style, parent)
        self._chooser_atom: int | None = None
        self._chooser_direction = (
            Point2D(1.0, 0.0) if initial_direction is None else initial_direction
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.CHOOSER_DELAY_MS)
        self._timer.timeout.connect(self._show_chooser)

    # -- Auswahl der Position ---------------------------------------------
    @property
    def chooser_active(self) -> bool:
        """Ist gerade die Positionsauswahl sichtbar?"""
        return self._chooser_atom is not None

    @property
    def chooser_direction(self) -> Point2D | None:
        """Aktuell markierte Richtung in der Positionsauswahl."""
        return self._chooser_direction if self.chooser_active else None

    def chooser_directions(self) -> tuple[Point2D, ...]:
        """Alle angebotenen Richtungen (im Kreis, beginnend bei 0°)."""
        return tuple(
            polar(Point2D(), 360.0 * index / self.CHOOSER_STEPS, 1.0)
            for index in range(self.CHOOSER_STEPS)
        )

    def _nearest_direction(self, atom_id: int, position: Point2D) -> Point2D:
        """Richtung der Auswahl, die der Mausposition am nächsten liegt."""
        anchor = electron_anchor(self.molecule, atom_id, self._style)
        vector = position - anchor
        if vector.length < 1e-6:
            return self._chooser_direction
        step = 360.0 / self.CHOOSER_STEPS
        index = round(vector.angle_deg / step) % self.CHOOSER_STEPS
        return self.chooser_directions()[index]

    def _chooser_selection(self) -> tuple[int, Point2D] | None:
        """Atom und Vergleichspunkt der gehaltenen Auswahl (``None`` = nichts)."""
        raise NotImplementedError

    def _show_chooser(self) -> None:
        """Zeigt die Positionsauswahl (wird vom Timer ausgelöst)."""
        selection = self._chooser_selection()
        if selection is None:
            return
        atom_id, position = selection
        self._chooser_atom = atom_id
        self._chooser_direction = self._nearest_direction(atom_id, position)
        self._snap_atom = None
        self.changed.emit()

    def _cancel_chooser(self) -> None:
        self._timer.stop()
        self._pending = None
        if self._chooser_atom is not None:
            self._chooser_atom = None
            self.changed.emit()

    def deactivate(self) -> None:
        self._cancel_chooser()
        super().deactivate()

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        if self.chooser_active and self._chooser_atom is not None:
            direction = self._nearest_direction(self._chooser_atom, position)
            if direction == self._chooser_direction:
                return False
            self._chooser_direction = direction
            return True
        return super().mouse_move(position, event)

    def paint_chooser_options(self, painter: QPainter) -> None:
        """Zeichnet den Ring möglicher Positionen um das gehaltene Atom."""
        atom_id = self._chooser_atom
        if atom_id is None or atom_id not in self.molecule:
            return
        anchor = electron_anchor(self.molecule, atom_id, self._style)
        radius = self._style.bond_length * self.OPTION_RADIUS_FACTOR
        ring = (
            max(label_half_size(self.molecule, atom_id, self._style))
            + radius
            + self._style.electron_gap
        )
        painter.save()
        for direction in self.chooser_directions():
            center = anchor + direction * ring
            if direction == self._chooser_direction:
                painter.setPen(QPen(qcolor(self._style.selection_color), 1.5))
                painter.setBrush(QBrush(qcolor(self._style.selection_color, 200)))
            else:
                painter.setPen(QPen(qcolor(self._style.page_border), 1.2))
                painter.setBrush(QBrush(qcolor(self._style.background)))
            painter.drawEllipse(to_qpoint(center), radius, radius)
        painter.restore()


class SelectTool(Tool):
    """Atome, Texte und Pfeile auswählen, verschieben und bearbeiten."""

    name = "Auswahl"
    hint = (
        "Klick wählt Atom, Text oder Pfeil aus; Ziehen verschiebt die Auswahl, "
        "auf freier Fläche zieht man ein Auswahlrechteck (Shift+Klick erweitert). "
        "Klick auf eine Bindung schaltet 1→2 (Seitenwechsel)→3→1; an den Greifpunkten eines "
        "Pfeils lässt sich seine Länge ändern (gebogene Pfeile folgen dabei ihrer "
        "Krümmung), bei Elektronenfluss-Pfeilen der mittlere Punkt für die "
        "Krümmung."
    )
    cursor = Qt.CursorShape.ArrowCursor
    highlights_bond = True

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent)
        self._dragging = False
        self._moved = False
        self._press_position = Point2D()
        self._start_positions: dict[int, Point2D] = {}
        self._start_texts: dict[int, TextObject] = {}
        self._start_arrows: dict[int, ArrowObject] = {}
        self._resize_arrow: int | None = None
        self._resize_end = "end"
        self._box_select = False
        self._box_start = Point2D()
        self._box_end = Point2D()

    def deactivate(self) -> None:
        super().deactivate()
        self._dragging = False
        self._box_select = False

    # -- Ereignisse ------------------------------------------------------
    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Greifpunkt eines bereits ausgewählten Pfeils: Länge ändern.
        handle = self._arrow_handle_at(position)
        if handle is not None:
            self._resize_arrow, self._resize_end = handle
            self._begin_drag(position)
            return True
        self._resize_arrow = None

        text_index = self.find_text_index(position)
        if text_index is not None:
            if additive:
                self._document.select_text(text_index, additive=True)
            elif not self._document.is_text_selected(text_index):
                self._document.select_text(text_index)
            self._begin_drag(position)
            return True

        atom_id = self._find_atom(position)
        if atom_id is not None:
            if additive:
                self._document.toggle_atom(atom_id)
            elif atom_id not in self._document.selection:
                self._document.select_only(atom_id)
            self._begin_drag(position)
            return True

        arrow_index = self.find_arrow_index(position)
        if arrow_index is not None:
            if additive:
                self._document.select_arrow(arrow_index, additive=True)
            elif not self._document.is_arrow_selected(arrow_index):
                self._document.select_arrow(arrow_index)
            self._begin_drag(position)
            return True

        if additive:
            return True
        # Freie Fläche: Auswahlrechteck aufziehen. Ein Klick ohne Ziehen
        # schaltet eine Bindung weiter bzw. hebt die Auswahl auf.
        self._box_select = True
        self._box_start = position
        self._box_end = position
        self._press_position = position
        self._moved = False
        return True

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        if self._box_select:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._box_select = False
                return True
            return self._update_box(position)
        if not self._dragging or not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouse_move(position, event)
        if self._resize_arrow is not None:
            return self._resize_arrow_at(position)

        delta = position - self._press_position
        if not self._moved and delta.length < self._style.bond_length * 0.1:
            return False
        self._moved = True
        for atom_id, start in self._start_positions.items():
            if atom_id in self.molecule:
                self.molecule.set_position(atom_id, self.clamp_to_page(start + delta))
        for index, text in self._start_texts.items():
            self._document.set_text_object(index, text.moved_to(text.position + delta))
        for index, arrow in self._start_arrows.items():
            self._document.set_arrow_object(index, arrow.translated(delta))
        self._document.touch()
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if self._box_select:
            return self._finish_box(event)
        if not self._dragging:
            return False
        resizing = self._resize_arrow is not None
        self._dragging = False
        self._resize_arrow = None
        if self._moved:
            if resizing:
                text = (
                    "Pfeilkrümmung ändern"
                    if self._resize_end == "bow"
                    else "Pfeil verlängern"
                )
            else:
                text = "Objekte verschieben"
            self._document.commit_edit(text)
        else:
            self._document.cancel_edit()
        self._start_positions = {}
        self._start_texts = {}
        self._start_arrows = {}
        return True

    # -- Hilfen ----------------------------------------------------------
    def _begin_drag(self, position: Point2D) -> None:
        """Merkt sich Positionen/Objekte für einen Drag und startet den Undo-Block."""
        self._dragging = True
        self._moved = False
        self._press_position = position
        document = self._document
        self._start_positions = {
            atom_id: self.molecule.atom(atom_id).position
            for atom_id in document.selection
        }
        self._start_texts = {
            index: document.texts[index] for index in document.text_selection
        }
        self._start_arrows = {
            index: document.arrows[index] for index in document.arrow_selection
        }
        document.begin_edit()

    def _arrow_handle_at(self, position: Point2D) -> tuple[int, str] | None:
        """Greifpunkt eines ausgewählten Pfeils: ``start``, ``end`` oder ``bow``."""
        radius = self._style.bond_length * ARROW_HANDLE_FACTOR
        arrows = self._document.arrows
        for index in sorted(self._document.arrow_selection):
            if index >= len(arrows):
                continue
            arrow = arrows[index]
            for end, point in (("start", arrow.start), ("end", arrow.end)):
                if point.distance_to(position) <= radius:
                    return index, end
            curve_handle = arrow_curve_handle(arrow)
            if curve_handle is not None and curve_handle.distance_to(position) <= radius:
                return index, "bow"
        return None

    def _resize_arrow_at(self, position: Point2D) -> bool:
        """Zieht ein Pfeilende (oder die Krümmung) nach."""
        index = self._resize_arrow
        arrows = self._document.arrows
        if index is None or index >= len(arrows):
            return False
        arrow = arrows[index]
        if self._resize_end == "bow":
            return self._bend_arrow_at(index, arrow, position)
        minimum = self._style.bond_length * ArrowTool.MIN_LENGTH_FACTOR
        if arrow.is_curved:
            # Gebogene Pfeile wachsen auf ihrem Kreis weiter – der Radius
            # (die Krümmung) bleibt dabei unverändert.
            curved = resize_flow_arrow(
                arrow,
                self.clamp_to_page(position),
                self._resize_end,
                minimum,
            )
            if curved is None or curved == arrow:
                return False
            self._document.set_arrow_object(index, curved)
            self._document.touch()
            self._moved = True
            return True
        anchor = arrow.start if self._resize_end == "end" else arrow.end
        distance = (position - anchor).length
        if distance < minimum:
            return False
        target = self.clamp_to_page(snap_to_grid_angle(anchor, position, length=distance))
        resized = (
            replace(arrow, end=target)
            if self._resize_end == "end"
            else replace(arrow, start=target)
        )
        if resized == arrow:
            return False
        self._document.set_arrow_object(index, resized)
        self._document.touch()
        self._moved = True
        return True

    def _bend_arrow_at(self, index: int, arrow: ArrowObject, position: Point2D) -> bool:
        """Setzt die Krümmung so, dass die Kurvenmitte unter der Maus liegt.

        Der Versatz wird in zwei Anteile zerlegt: senkrecht zur Verbindungslinie
        (``bow`` – Wölbung) und entlang des Pfeils (``bow_along`` – Verschiebung
        des Scheitels, damit der Bogen nach links/rechts wandert).
        """
        if arrow.length < 1e-6:
            return False
        direction = arrow.direction
        left = Point2D(direction.y, -direction.x)
        offset = position - arrow.midpoint
        along = offset.x * direction.x + offset.y * direction.y
        perpendicular = offset.x * left.x + offset.y * left.y
        # Die Kurvenmitte liegt bei halbem Kontrollpunkt-Versatz.
        scale = 2.0 / arrow.length
        bow = max(-MAX_FLOW_BOW, min(MAX_FLOW_BOW, round(perpendicular * scale, 3)))
        bow_along = max(
            -MAX_FLOW_BOW_ALONG,
            min(MAX_FLOW_BOW_ALONG, round(along * scale, 3)),
        )
        if bow == arrow.bow and bow_along == arrow.bow_along:
            return False
        self._document.set_arrow_object(
            index,
            ArrowObject(
                arrow.start,
                arrow.end,
                arrow.kind,
                bow,
                bow_along,
                color=arrow.color,
            ),
        )
        self._document.touch()
        self._moved = True
        return True

    # -- Auswahlrechteck --------------------------------------------------
    def _box_rect(self) -> QRectF:
        """Aktuelles Auswahlrechteck in Szenenkoordinaten."""
        return QRectF(to_qpoint(self._box_start), to_qpoint(self._box_end)).normalized()

    def _update_box(self, position: Point2D) -> bool:
        if not self._moved and (position - self._box_start).length < self._style.bond_length * 0.15:
            return False
        self._moved = True
        self._box_end = position
        return True

    def _finish_box(self, event: "QMouseEvent") -> bool:
        """Beendet das Aufziehen: auswählen – oder bei einem Klick weiter-/abwählen."""
        self._box_select = False
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if not self._moved:
            if additive:
                return True
            # Klick ohne Ziehen auf eine Bindung schaltet die Ordnung weiter.
            if not self.cycle_bond_at(self._box_start):
                self._document.clear_selection()
            return True

        rect = self._box_rect()
        self._document.select_objects(
            self._atoms_in(rect),
            self._texts_in(rect),
            self._arrows_in(rect),
            additive=additive,
        )
        return True

    def _atoms_in(self, rect: QRectF) -> set[int]:
        """Atome, deren Zentrum im Rechteck liegt."""
        return {
            atom_id
            for atom_id in self.molecule.atom_ids()
            if rect.contains(to_qpoint(self.molecule.atom(atom_id).position))
        }

    def _texts_in(self, rect: QRectF) -> set[int]:
        """Beschriftungen, die das Rechteck berühren."""
        return {
            index
            for index, obj in enumerate(self._document.texts)
            if rect.intersects(text_bounds(obj, self._style))
        }

    def _arrows_in(self, rect: QRectF) -> set[int]:
        """Pfeile, deren Linie das Rechteck berührt."""
        margin = self._style.bond_width
        result: set[int] = set()
        for index, arrow in enumerate(self._document.arrows):
            low, high = arrow.extent()
            box = QRectF(to_qpoint(low), to_qpoint(high)).normalized()
            if rect.intersects(box.adjusted(-margin, -margin, margin, margin)):
                result.add(index)
        return result

    def paint_overlay(self, painter: QPainter) -> None:
        if not self._box_select or not self._moved:
            return
        painter.save()
        painter.setPen(
            QPen(
                qcolor(self._style.preview_color),
                self._style.preview_width,
                Qt.PenStyle.DashLine,
            )
        )
        painter.setBrush(QBrush(qcolor(self._style.preview_color, 30)))
        painter.drawRect(self._box_rect())
        painter.restore()


class BondTool(Tool):
    """Bindungen zeichnen – von Atom zu Atom oder frei ins Leere."""
    name = "Bindung"
    hint = (
        "Ziehen zeichnet eine Bindung in Ziehrichtung. Klick auf ein Atom oder "
        "auf das leere Blatt setzt eine Bindung in der günstigsten Richtung; "
        "Klick auf eine Bindung schaltet die Bindungsordnung weiter."
    )
    cursor = Qt.CursorShape.CrossCursor
    highlights_snap_atom = True
    highlights_bond = True

    AUTO_MIN_ANGLE = 50.0
    """Mindestwinkel zu vorhandenen Bindungen beim automatischen Setzen (Grad)."""
    AUTO_IDEAL_ANGLE = 120.0
    """Bevorzugter Winkel zu vorhandenen Bindungen (Grad)."""
    AUTO_ATOM_CLEARANCE = 0.6
    """Mindestabstand des neuen Atoms zu anderen Atomen (Anteil der Bindungslänge)."""

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent)
        self.bond_order = 1
        self._active = False
        self._start_atom: int | None = None
        self._start_position = Point2D()
        self._current_position = Point2D()

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start_atom = self._find_atom(position)
        self._start_position = (
            self.molecule.atom(self._start_atom).position
            if self._start_atom is not None
            else position
        )
        self._current_position = position
        self._active = True
        return True

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        hover = super().mouse_move(position, event)
        if not self._active:
            return hover
        self._current_position = position
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if not self._active:
            return False
        self._active = False
        self._current_position = position
        if (position - self._start_position).length < self._style.bond_length * 0.35:
            # Kurzer Klick ohne Ziehen: auf einer Bindung wird die
            # Bindungsordnung weitergeschaltet, sonst entsteht eine Bindung in
            # der günstigsten Richtung (ohne manuelle Ziehrichtung).
            if self._start_atom is not None:
                self._add_bond_in_best_direction(self._start_atom)
            elif not self.cycle_bond_at(position):
                self._add_bond_on_empty_space(self._start_position)
            return True

        target = self.target_position()
        target_atom = self.molecule.find_atom_near(target, self.hit_radius)
        if target_atom is not None and target_atom == self._start_atom:
            return True

        with self._document.edit("Bindung zeichnen"):
            start_atom = self._start_atom
            if start_atom is None:
                start_atom = self.molecule.add_atom("C", self._start_position)
            if target_atom is None:
                target_atom = self.molecule.add_atom("C", target)

            self._connect(start_atom, target_atom)
        return True

    # -- Anlegen / Ändern ------------------------------------------------
    def _connect(self, start_atom: int, end_atom: int) -> None:
        """Verbindet zwei Atome: bestehende Bindung ändern oder neue anlegen."""
        existing = self.molecule.bond_between(start_atom, end_atom)
        if existing is not None:
            self._update_existing_bond(existing, start_atom)
        else:
            self._new_bond(start_atom, end_atom)

    def _update_existing_bond(self, bond: Bond, start_atom: int) -> None:
        """Ziehen über eine bestehende Bindung erhöht die Ordnung."""
        if bond.order < 3:
            self.molecule.set_bond_order(bond, bond.order + 1)

    def _new_bond(self, start_atom: int, end_atom: int) -> None:
        """Legt die neue Bindung an (Unterklassen setzen hier ihre Darstellung)."""
        self.molecule.add_bond(start_atom, end_atom, self.bond_order)

    # -- Automatische Richtung -------------------------------------------
    def _add_bond_in_best_direction(self, atom_id: int) -> bool:
        """Hängt eine Bindung ohne Ziehrichtung ans Atom (ein Undo-Schritt)."""
        return self._append_bond(self.molecule.atom(atom_id).position, atom_id)

    def _add_bond_on_empty_space(self, position: Point2D) -> bool:
        """Setzt eine Bindung frei auf das Blatt (ein Undo-Schritt)."""
        return self._append_bond(position, None)

    def _append_bond(self, origin: Point2D, atom_id: int | None) -> bool:
        """Legt an ``origin`` eine neue Bindung in der günstigsten Richtung an."""
        direction = self.best_direction(origin, atom_id)
        if direction is None:
            return False
        target = self.clamp_to_page(origin + direction * self._style.bond_length)
        with self._document.edit("Bindung zeichnen"):
            start_atom = atom_id
            if start_atom is None:
                start_atom = self.molecule.add_atom("C", origin)
            end_atom = self.molecule.add_atom("C", target)
            self._new_bond(start_atom, end_atom)
        return True

    def auto_direction(self, atom_id: int) -> Point2D | None:
        """Günstigste Richtung für eine neue Bindung an ``atom_id``."""
        return self.best_direction(self.molecule.atom(atom_id).position, atom_id)

    def best_direction(self, origin: Point2D, atom_id: int | None = None) -> Point2D | None:
        """Günstigste Richtung für eine neue Bindung ab ``origin``.

        ``atom_id`` nennt das Atom, dessen vorhandene Bindungen den Winkel
        bestimmen. Auf freier Fläche bleibt es ``None``; ohne Hindernisse
        gewinnt dann die waagerechte Richtung. Bewertet werden alle
        15°-Richtungen; ausgeschlossen sind Richtungen, die eine vorhandene
        Bindung überdecken, ein anderes Atom treffen oder vom Blatt führen.
        Bevorzugt werden der ideale Bindungswinkel (~120°), viel Platz zu
        anderen Atomen und etwas Abstand zum Blattrand. Liefert ``None``,
        wenn keine Richtung passt.
        """
        best: Point2D | None = None
        best_score = float("-inf")
        for step in range(round(360.0 / SNAP_STEP_DEG)):
            direction = polar(Point2D(), step * SNAP_STEP_DEG, 1.0)
            score = self._score_direction(origin, atom_id, direction)
            if score is not None and score > best_score:
                best, best_score = direction, score
        return best

    def _score_direction(
        self,
        origin: Point2D,
        atom_id: int | None,
        direction: Point2D,
    ) -> float | None:
        """Bewertet eine Richtung für die neue Bindung (``None`` = unbrauchbar)."""
        molecule = self.molecule
        length = self._style.bond_length
        target = origin + direction * length
        if not self.is_on_page(target):
            return None

        score = 0.0
        if atom_id is not None:
            for neighbor in molecule.neighbors(atom_id):
                to_neighbor = (molecule.atom(neighbor).position - origin).normalized()
                angle = angle_between(direction, to_neighbor)
                if angle < self.AUTO_MIN_ANGLE:
                    return None
                # Ein Winkel nahe 120° ist chemisch und optisch am schönsten.
                score -= abs(angle - self.AUTO_IDEAL_ANGLE) * 10.0

        for other_id in molecule.atom_ids():
            if other_id == atom_id:
                continue
            distance = target.distance_to(molecule.atom(other_id).position)
            if distance < length * self.AUTO_ATOM_CLEARANCE:
                return None
            score -= max(0.0, length - distance) * 2.0

        # Weiter innen auf dem Blatt ist besser als hart am Rand.
        low, high = self.page_bounds
        border = min(
            target.x - low.x,
            high.x - target.x,
            target.y - low.y,
            high.y - target.y,
        )
        return score + min(border, length)

    # -- Vorschau --------------------------------------------------------
    def target_position(self) -> Point2D:
        """Eingerasteter Endpunkt der Vorschau (auf das Blatt begrenzt)."""
        snapped = snap_to_grid_angle(
            self._start_position,
            self._current_position,
            length=self._style.bond_length,
        )
        return self.clamp_to_page(snapped)

    def paint_overlay(self, painter: QPainter) -> None:
        if not self._active:
            return
        target = self.target_position()
        pen = QPen(
            qcolor(self._style.preview_color),
            self._style.preview_width,
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(to_qpoint(self._start_position), to_qpoint(target))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*self._style.preview_color))
        painter.drawEllipse(to_qpoint(target), 5.0, 5.0)


class StereoBondTool(BondTool):
    """Keil- oder Strichkeilbindungen zeichnen und Bindungen umwandeln.

    Die schmale Spitze sitzt am Startatom (bzw. an dem Atom, an dem gezogen
    wird). Ein Klick auf eine vorhandene Bindung setzt die Darstellung, ein
    weiterer Klick hebt sie wieder auf; Rechtsklick spiegelt die Richtung.
    """

    stereo: BondStereo = BondStereo.WEDGE
    name = "Keil"
    hint = (
        "Ziehen zeichnet eine Keilbindung: schmale Spitze am Startatom, breite "
        "Seite am Zielatom. Klick auf eine Bindung wandelt sie um, ein erneuter "
        "Klick hebt die Darstellung auf; Rechtsklick spiegelt die Richtung. "
        "Klick auf ein Atom hängt eine neue Keilbindung an."
    )
    set_text = "Keilbindung setzen"
    remove_text = "Keilbindung entfernen"

    def __init__(
        self,
        document: "Document",
        style: Style = DEFAULT_STYLE,
        parent: QObject | None = None,
        stereo: BondStereo | None = None,
    ) -> None:
        super().__init__(document, style, parent)
        if stereo is not None:
            self.stereo = stereo
        self.bond_order = 1

    # -- Anlegen / Umwandeln ---------------------------------------------
    def _new_bond(self, start_atom: int, end_atom: int) -> None:
        """Neue Bindung mit Keilspitze am Startatom."""
        self.molecule.add_bond(
            start_atom,
            end_atom,
            order=1,
            stereo=self.stereo,
            stereo_from=start_atom,
        )

    def _update_existing_bond(self, bond: Bond, start_atom: int) -> None:
        """Ziehen über eine Bindung setzt die Keildarstellung (Spitze am Start)."""
        self.molecule.set_bond_stereo(bond, self.stereo, start_atom)

    def cycle_bond_at(self, position: Point2D) -> bool:
        """Klick auf eine Bindung: Keildarstellung setzen bzw. aufheben."""
        bond = self.molecule.find_bond_near(position, self.hit_radius * 0.8)
        if bond is None:
            return False
        if bond.stereo is self.stereo:
            self._document.set_bond_stereo(bond, BondStereo.NONE, text=self.remove_text)
        else:
            self._document.set_bond_stereo(
                bond, self.stereo, bond.narrow_atom, text=self.set_text
            )
        return True

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            return self._mirror_at(position)
        return super().mouse_press(position, event)

    def _mirror_at(self, position: Point2D) -> bool:
        """Rechtsklick dreht die Spitze einer Keilbindung ans andere Atom."""
        bond = self.molecule.find_bond_near(position, self.hit_radius * 0.8)
        if bond is None or bond.stereo is BondStereo.NONE:
            return False
        self._document.flip_bond_stereo(bond)
        return True

    # -- Vorschau --------------------------------------------------------
    def paint_overlay(self, painter: QPainter) -> None:
        if not self._active:
            return
        target = self.target_position()
        painter.save()
        if self.stereo is BondStereo.WEDGE:
            painter.setPen(Qt.PenStyle.NoPen)
            color = QColor(*self._style.preview_color)
            color.setAlpha(120)
            painter.setBrush(QBrush(color))
            painter.drawPolygon(
                wedge_triangle(self._start_position, target, self._style.wedge_width)
            )
        else:
            painter.setPen(
                QPen(
                    qcolor(self._style.preview_color),
                    self._style.bond_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for start, end in hashed_wedge_lines(
                self._start_position,
                target,
                self._style.wedge_width,
                self._style.wedge_hatch_spacing,
            ):
                painter.drawLine(to_qpoint(start), to_qpoint(end))
        painter.restore()


class WedgeBondTool(StereoBondTool):
    """Keilbindung: die Bindung ragt aus der Zeichenebene heraus."""

    stereo = BondStereo.WEDGE
    name = "Keil"


class HashedBondTool(StereoBondTool):
    """Strichkeilbindung: die Bindung liegt hinter der Zeichenebene."""

    stereo = BondStereo.HASHED
    name = "Strichkeil"
    hint = (
        "Ziehen zeichnet eine Strichkeilbindung: schmale Spitze am Startatom, "
        "breite Seite am Zielatom. Klick auf eine Bindung wandelt sie um, ein "
        "erneuter Klick hebt die Darstellung auf; Rechtsklick spiegelt die "
        "Richtung. Klick auf ein Atom hängt eine neue Strichkeilbindung an."
    )
    set_text = "Strichkeil setzen"
    remove_text = "Strichkeil entfernen"


class AtomTool(Tool):
    """Atome setzen und Elemente ändern."""

    name = "Atom"
    hint = (
        "Klick auf ein Atom ändert das Element, Klick auf freie Fläche erzeugt "
        "ein Atom (Kohlenstoff wird als C beschriftet)."
    )
    cursor = Qt.CursorShape.CrossCursor
    highlights_snap_atom = True

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent)
        self.element = "C"

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        atom_id = self._find_atom(position)
        with self._document.edit("Atom setzen"):
            if atom_id is None:
                atom_id = self.molecule.add_atom(self.element, position)
                self._document.select_only(atom_id)
            self._set_explicit_element(atom_id)
        return True

    def _set_explicit_element(self, atom_id: int) -> None:
        """Setzt das gewählte Element und beschriftet es sichtbar.

        Kohlenstoff wird im Skelett normalerweise nicht gezeichnet; wer ihn mit
        dem Atom-Werkzeug ausdrücklich setzt, bekommt ein sichtbares ``C``.
        Eigene Gruppenlabels (z. B. ``NO2``) bleiben dabei erhalten.
        """
        molecule = self.molecule
        previous = molecule.atom(atom_id).element
        label = molecule.atom_label(atom_id)
        keep_custom_label = bool(label) and label.upper() != previous.upper()

        molecule.set_element(atom_id, self.element)
        if keep_custom_label:
            return
        molecule.set_label(atom_id, "C" if self.element == "C" else "")


class ChargeTool(_DirectionChooserTool):
    """Ladungen setzen – Klick zählt, Gedrückthalten wählt die Position."""

    name = "Ladung"
    hint = (
        "Klick auf ein Atom zählt die positive Ladung hoch (+ → 2+ … → 7+ → 0), "
        "Rechtsklick (oder Shift+Klick) die negative. Maustaste auf einem Atom "
        "gedrückt halten: Position der Ladung wählen (danach Ladung eintippen); "
        "Doppelklick oder Strg+Klick öffnet das Eingabefeld."
    )
    cursor = Qt.CursorShape.PointingHandCursor
    highlights_snap_atom = True

    _pending: tuple[int, int, Point2D] | None = None

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent, initial_direction=Point2D(1.0, -1.0))
        self._last_cycle: tuple[int, int] | None = None
        self._chooser_sign = 1

    # -- Auswahl der Position ---------------------------------------------
    def _chooser_selection(self) -> tuple[int, Point2D] | None:
        """Atom und Klickposition der gehaltenen Auswahl."""
        if self._pending is None:
            return None
        atom_id, sign, position = self._pending
        if atom_id not in self.molecule:
            return None
        self._chooser_sign = sign
        return atom_id, position

    # -- Ereignisse -------------------------------------------------------
    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        button = event.button()
        if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        atom_id = self._find_atom(position)
        if atom_id is None:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._ask_charge(atom_id)
            return True
        negative = button == Qt.MouseButton.RightButton or bool(
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        self._pending = (atom_id, -1 if negative else 1, position)
        self._timer.start()
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        chooser_atom = self._chooser_atom
        direction = self._chooser_direction
        sign = self._chooser_sign
        pending = self._pending
        self._timer.stop()
        self._pending = None
        self._chooser_atom = None
        if chooser_atom is not None:
            # Position gemerkt – jetzt die Ladung eintippen.
            self._ask_charge(chooser_atom, direction, sign)
            return True
        if pending is None:
            return False
        atom_id, pending_sign, _position = pending
        if atom_id not in self.molecule:
            return False
        self._last_cycle = (atom_id, self.molecule.atom(atom_id).charge)
        self._document.cycle_atom_charge(atom_id, pending_sign)
        return True

    def mouse_double_click(self, position: Point2D, event: "QMouseEvent") -> bool:
        """Doppelklick öffnet den Eingabedialog.

        Der erste Klick des Doppelklicks hat den Zyklus schon weitergeschaltet;
        das wird zurückgenommen, damit der Dialog mit der Ausgangsladung startet.
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        atom_id = self._find_atom(position)
        if atom_id is None:
            return False
        if self._last_cycle is not None and self._last_cycle[0] == atom_id:
            self._document.undo_stack.undo()
            self._last_cycle = None
        self._ask_charge(atom_id)
        return True

    def _ask_charge(
        self,
        atom_id: int,
        direction: Point2D | None = None,
        sign: int = 1,
    ) -> bool:
        """Öffnet den Ladungsdialog; liefert ``True``, wenn etwas geändert wurde.

        ``direction`` ist gesetzt, wenn vorher eine Position gewählt wurde –
        dann wird die Ladung genau dort platziert.
        """
        atom = self.molecule.atom(atom_id)
        symbol = atom_label(self.molecule, atom_id)
        parent = self.parent()
        initial = atom.charge
        if direction is not None and initial == 0:
            initial = sign  # sinnvoller Startwert für eine neue Ladung
        charge = ChargeDialog.ask(parent, initial, symbol)
        self._last_cycle = None
        if charge is None:
            return False
        if direction is not None:
            self._document.set_atom_charge_position(
                atom_id, charge, direction, "Ladung setzen"
            )
            return True
        if charge == atom.charge:
            return False
        self._document.set_atom_charge(atom_id, charge, "Ladung eingeben")
        return True

    # -- Darstellung ------------------------------------------------------
    def paint_overlay(self, painter: QPainter) -> None:
        self.paint_chooser_options(painter)


class PartialChargeTool(_DirectionChooserTool):
    """Teilladungen δ⁺/δ⁻ setzen – Klick schaltet, Halten wählt die Position."""

    name = "Teilladung"
    hint = (
        "Klick auf ein Atom setzt δ⁺ (erneuter Klick entfernt es), Rechtsklick "
        "oder Shift+Klick setzt δ⁻. Maustaste auf einem Atom gedrückt halten: "
        "Position der Teilladung wählen. Formalladungen bleiben daneben stehen."
    )
    cursor = Qt.CursorShape.PointingHandCursor
    highlights_snap_atom = True

    _pending: tuple[int, int, Point2D] | None = None

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent, initial_direction=Point2D(1.0, -1.0))
        self._chooser_sign = 1

    # -- Auswahl der Position ---------------------------------------------
    def _chooser_selection(self) -> tuple[int, Point2D] | None:
        """Atom und Klickposition der gehaltenen Auswahl."""
        if self._pending is None:
            return None
        atom_id, sign, position = self._pending
        if atom_id not in self.molecule:
            return None
        self._chooser_sign = sign
        return atom_id, position

    # -- Ereignisse -------------------------------------------------------
    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        button = event.button()
        if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        atom_id = self._find_atom(position)
        if atom_id is None:
            return False
        negative = button == Qt.MouseButton.RightButton or bool(
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        self._pending = (atom_id, -1 if negative else 1, position)
        self._timer.start()
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        chooser_atom = self._chooser_atom
        direction = self._chooser_direction
        sign = self._chooser_sign
        pending = self._pending
        self._timer.stop()
        self._pending = None
        self._chooser_atom = None
        if chooser_atom is not None:
            # Position gewählt: Teilladung mit diesem Vorzeichen dorthin setzen.
            self._document.set_atom_partial_charge(
                chooser_atom, sign, direction, "Teilladung setzen"
            )
            return True
        if pending is None:
            return False
        atom_id, pending_sign, _position = pending
        if atom_id not in self.molecule:
            return False
        self._document.cycle_atom_partial_charge(atom_id, pending_sign)
        return True

    # -- Darstellung ------------------------------------------------------
    def paint_overlay(self, painter: QPainter) -> None:
        self.paint_chooser_options(painter)


class ElectronTool(_DirectionChooserTool):
    """Elektronenpaare (zwei Punkte) und Radikale (ein Punkt) setzen.

    Kurzer Klick setzt das Elektron in Klickrichtung. Wer die Maustaste auf
    einem Atom **gedrückt hält**, bekommt nach kurzer Zeit eine Auswahl von
    Positionen rund um das Atom und kann die Richtung per Ziehen wählen.
    """

    name = "Elektronen"
    hint = (
        "Klick neben ein Atom setzt ein Elektronenpaar in Klickrichtung "
        "(zweiter Klick auf denselben Punkt entfernt es); Rechtsklick oder "
        "Shift+Klick setzt ein einzelnes Elektron (Radikal). Maustaste auf einem "
        "Atom gedrückt halten: Position auswählen."
    )
    cursor = Qt.CursorShape.PointingHandCursor
    highlights_snap_atom = True

    _pending: tuple[int, bool, Point2D] | None = None

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent)
        self._chooser_radical = False

    def _target_atom(self, position: Point2D) -> int | None:
        """Atom in der Nähe des Klicks – der Radius ist größer als beim Zeichnen.

        Gemessen wird zum Atom **und** zum Label-Mittelpunkt: bei endständigen
        Atomen sitzt das Label seitlich versetzt, ein Klick darauf gehört aber
        trotzdem zu diesem Atom.
        """
        molecule = self.molecule
        best: int | None = None
        best_distance = self._style.bond_length * 0.6
        for atom_id in molecule.atom_ids():
            distance = min(
                molecule.atom(atom_id).position.distance_to(position),
                electron_anchor(molecule, atom_id, self._style).distance_to(position),
            )
            if distance <= best_distance:
                best, best_distance = atom_id, distance
        if best is not None:
            return best
        return self._find_atom(position)

    def _update_snap_hover(self, position: Point2D) -> bool:
        atom_id = self._target_atom(position)
        if atom_id == self._snap_atom:
            return False
        self._snap_atom = atom_id
        return True

    # -- Auswahl der Position --------------------------------------------
    def _chooser_selection(self) -> tuple[int, Point2D] | None:
        """Atom und Vergleichspunkt der gehaltenen Auswahl.

        Der Klick wird als Richtung gemerkt; für die Winkelberechnung zählt
        der Punkt in ebendieser Richtung neben dem Atom.
        """
        if self._pending is None:
            return None
        atom_id, radical, direction = self._pending
        if atom_id not in self.molecule:
            return None
        self._chooser_radical = radical
        return atom_id, self.molecule.atom(atom_id).position + direction

    # -- Ereignisse -------------------------------------------------------
    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        button = event.button()
        if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        atom_id = self._target_atom(position)
        if atom_id is None:
            return False
        atom = self.molecule.atom(atom_id)
        direction = position - atom.position
        if direction.length < 1e-6:
            direction = Point2D(1.0, 0.0)
        radical = button == Qt.MouseButton.RightButton or bool(
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        self._pending = (atom_id, radical, direction)
        self._timer.start()
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False
        pending = self._pending
        chooser_atom = self._chooser_atom
        direction = self._chooser_direction
        self._timer.stop()
        self._pending = None
        self._chooser_atom = None
        if chooser_atom is not None:
            radical = self._chooser_radical
            self._document.toggle_electron(chooser_atom, direction, radical)
            return True
        if pending is None:
            return False
        atom_id, radical, direction = pending
        if atom_id not in self.molecule:
            return False
        self._document.toggle_electron(atom_id, direction, radical)
        return True

    def paint_overlay(self, painter: QPainter) -> None:
        if self._chooser_atom is None or self._chooser_atom not in self.molecule:
            return
        atom_id = self._chooser_atom
        painter.save()
        for direction in self.chooser_directions():
            selected = direction == self._chooser_direction
            dots = electron_preview(
                self.molecule, atom_id, direction, self._chooser_radical, self._style
            )
            painter.setPen(Qt.PenStyle.NoPen)
            if selected:
                painter.setBrush(QBrush(qcolor(self._style.selection_color, 210)))
            else:
                painter.setBrush(QBrush(qcolor(self._style.bond_color, 70)))
            radius = self._style.electron_dot_radius * (1.35 if selected else 1.0)
            for dot in dots:
                painter.drawEllipse(to_qpoint(dot), radius, radius)
        painter.restore()


class EraseTool(Tool):
    """Atome, Bindungen, Texte und Pfeile löschen."""

    name = "Radierer"
    hint = (
        "Klick entfernt Text, Pfeil, Bindung oder Elektronenpaar; auf einem Atom "
        "zuerst die Beschriftung (wird Kohlenstoff), beim zweiten Klick das Atom "
        "samt Bindungen."
    )
    cursor = Qt.CursorShape.PointingHandCursor

    def __init__(self, document: "Document", style: Style = DEFAULT_STYLE, parent: QObject | None = None) -> None:
        super().__init__(document, style, parent)
        self._hover_atom: int | None = None
        self._hover_bond: Bond | None = None
        self._hover_text: TextObject | None = None
        self._hover_arrow: ArrowObject | None = None
        self._hover_electron: tuple[int, str, int] | None = None

    def _update_hover(self, position: Point2D) -> None:
        self._hover_electron = electron_hit(self.molecule, position, self._style)
        self._hover_atom = None
        self._hover_bond = None
        self._hover_text = None
        self._hover_arrow = None
        if self._hover_electron is not None:
            return
        self._hover_atom = self._find_atom(position)
        if self._hover_atom is not None:
            return
        self._hover_bond = self.molecule.find_bond_near(position, self.hit_radius * 0.8)
        if self._hover_bond is not None:
            return
        self._hover_text = self.find_text(position)
        if self._hover_text is not None:
            return
        self._hover_arrow = self.find_arrow(position)

    def _erase_atom(self, atom_id: int) -> None:
        """Erst die Beschriftung entfernen, erst dann das Atom samt Bindungen.

        Ein sichtbares Atom – Element wie ``O``, Ladung oder Gruppenlabel wie
        ``OTs`` – wird beim ersten Klick zu einem einfachen Skelett-Kohlenstoff;
        die Bindungen bleiben erhalten. Nur ein unbeschriftetes Kohlenstoffatom
        wird mitsamt seinen Bindungen gelöscht.
        """
        atom = self.molecule.atom(atom_id)
        is_plain_carbon = (
            atom.element == DEFAULT_ELEMENT
            and atom.charge == 0
            and not atom.label.strip()
            and not atom.lone_pairs
            and not atom.radicals
        )
        if not is_plain_carbon:
            with self._document.edit("Atombeschriftung entfernen"):
                self.molecule.reset_atom(atom_id)
            return
        with self._document.edit("Atom löschen"):
            self.molecule.remove_atom(atom_id)

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        self._update_hover(position)
        return True

    def clear_hover(self) -> bool:
        """Entfernt die rote Hover-Markierung (z. B. beim Verlassen der Fläche)."""
        changed = (
            self._hover_atom is not None
            or self._hover_bond is not None
            or self._hover_text is not None
            or self._hover_arrow is not None
            or self._hover_electron is not None
        )
        self._hover_atom = None
        self._hover_bond = None
        self._hover_text = None
        self._hover_arrow = None
        self._hover_electron = None
        return changed

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._update_hover(position)
        if self._hover_electron is not None:
            atom_id, kind, index = self._hover_electron
            self._document.remove_electron(atom_id, kind, index)
        elif self._hover_atom is not None:
            self._erase_atom(self._hover_atom)
        elif self._hover_bond is not None:
            with self._document.edit("Bindung löschen"):
                self.molecule.remove_bond(self._hover_bond)
        elif self._hover_text is not None:
            self._document.remove_text(self._hover_text)
        elif self._hover_arrow is not None:
            self._document.remove_arrow(self._hover_arrow)
        self._hover_atom = None
        self._hover_bond = None
        self._hover_text = None
        self._hover_arrow = None
        self._hover_electron = None
        return True

    def paint_overlay(self, painter: QPainter) -> None:
        color = QColor(220, 60, 60, 90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        if self._hover_electron is not None:
            atom_id, kind, index = self._hover_electron
            if atom_id in self.molecule:
                atom = self.molecule.atom(atom_id)
                vectors = atom.lone_pairs if kind == "pair" else atom.radicals
                if 0 <= index < len(vectors):
                    for dot in electron_preview(
                        self.molecule, atom_id, vectors[index], kind == "radical", self._style
                    ):
                        radius = self._style.electron_dot_radius * 2.4
                        painter.drawEllipse(to_qpoint(dot), radius, radius)
            return
        if self._hover_atom is not None and self._hover_atom in self.molecule:
            radius = self._style.bond_length * SELECTION_RADIUS_FACTOR
            painter.drawEllipse(
                to_qpoint(label_center(self.molecule, self._hover_atom, self._style)),
                radius,
                radius,
            )
        elif self._hover_bond is not None:
            bond = self._hover_bond
            if bond.a in self.molecule and bond.b in self.molecule:
                pen = QPen(color, self._style.selection_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(
                    to_qpoint(self.molecule.atom(bond.a).position),
                    to_qpoint(self.molecule.atom(bond.b).position),
                )
        elif self._hover_text is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(text_bounds(self._hover_text, self._style), 4.0, 4.0)
        elif self._hover_arrow is not None:
            arrow = self._hover_arrow
            pen = QPen(color, self._style.selection_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawPath(arrow_path(arrow))


class RingTool(Tool):
    """Ring-Templates platzieren – auf einem Atom wird der Ring dort angeknüpft."""

    name = "Ring"
    hint = "Klick setzt einen Ring; auf einem Atom wird er dort angeknüpft."
    cursor = Qt.CursorShape.CrossCursor
    highlights_snap_atom = True

    def __init__(
        self,
        document: "Document",
        style: Style = DEFAULT_STYLE,
        parent: QObject | None = None,
        template: RingTemplate = BENZENE,
    ) -> None:
        super().__init__(document, style, parent)
        self.template = template
        self._preview: list[Point2D] = []

    def deactivate(self) -> None:
        super().deactivate()
        self._preview = []

    # -- Geometrie -------------------------------------------------------
    def placement(self, position: Point2D) -> list[Point2D]:
        """Eckpunkte des Rings für einen Klick an ``position``."""
        bond_length = self._style.bond_length
        atom_id = self._find_atom(position)
        if atom_id is None:
            return self.template.vertices(position, bond_length=bond_length)

        anchor = self.molecule.atom(atom_id).position
        neighbors = [self.molecule.atom(n).position for n in self.molecule.neighbors(atom_id)]
        direction = Point2D(1.0, 0.0)
        if neighbors:
            total = Point2D()
            for neighbor in neighbors:
                total = total + (neighbor - anchor).normalized()
            if total.length > 1e-6:
                # Ring in den freien Raum zeigen lassen (weg von den Nachbarn).
                direction = (-total).normalized()
            else:
                # Nachbarn liegen gegenüber: senkrecht zur ersten Bindung ansetzen.
                direction = (neighbors[0] - anchor).normalized().rotated(90.0)

        center = anchor + direction * self.template.circumradius_for(bond_length)
        return self.template.vertices(
            center,
            start_angle_deg=direction.angle_deg + 180.0,
            bond_length=bond_length,
        )

    # -- Ereignisse ------------------------------------------------------
    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        self._update_snap_hover(position)
        self._preview = self.placement(position)
        return True

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        vertices = self.placement(position)
        if not self.all_on_page(vertices):
            return True
        with self._document.edit(f"{self.template.name} einfügen"):
            atom_ids: list[int] = []
            for vertex in vertices:
                existing = self.molecule.find_atom_near(vertex, self.hit_radius * 0.5)
                if existing is None:
                    atom_ids.append(self.molecule.add_atom("C", vertex))
                else:
                    atom_ids.append(existing)

            for (start_index, end_index), order in zip(
                self.template.bond_pairs(), self.template.bond_orders, strict=True
            ):
                start_atom = atom_ids[start_index]
                end_atom = atom_ids[end_index]
                if start_atom == end_atom:
                    continue
                bond = self.molecule.bond_between(start_atom, end_atom)
                if bond is None:
                    self.molecule.add_bond(start_atom, end_atom, order)
                elif bond.order < order:
                    self.molecule.set_bond_order(bond, order)
        self._preview = []
        return True

    # -- Vorschau --------------------------------------------------------
    def paint_overlay(self, painter: QPainter) -> None:
        if not self._preview:
            return
        pen = QPen(
            qcolor(self._style.preview_color),
            self._style.preview_width,
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF([to_qpoint(vertex) for vertex in self._preview]))


class TextTool(Tool):
    """Textbeschriftungen setzen und bearbeiten.

    Ein Klick auf ein Atom setzt ein Label direkt am Atom (z. B. ``NO2`` für
    eine funktionelle Gruppe), ein Klick auf freie Fläche einen freien Text.
    Die Bearbeitung selbst (Dialog) macht das Hauptfenster.
    """

    name = "Text"
    hint = "Klick auf ein Atom = Gruppenlabel (z. B. NO2), Klick auf Fläche = freier Text."
    cursor = Qt.CursorShape.IBeamCursor
    highlights_snap_atom = True

    text_requested = Signal(object, object)
    atom_label_requested = Signal(object)

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        atom_id = self._find_atom(position)
        if atom_id is not None:
            self.atom_label_requested.emit(atom_id)
            return True
        self.text_requested.emit(position, self.find_text(position))
        return True


class ArrowTool(Tool):
    """Reaktionspfeile ziehen."""

    name = "Pfeil"
    hint = "Ziehen zeichnet einen Pfeil in Ziehrichtung (Winkel rastet in 15°-Schritten ein)."
    cursor = Qt.CursorShape.CrossCursor

    MIN_LENGTH_FACTOR = 0.6

    def __init__(
        self,
        document: "Document",
        style: Style = DEFAULT_STYLE,
        parent: QObject | None = None,
        kind: ArrowKind = ArrowKind.FORWARD,
    ) -> None:
        super().__init__(document, style, parent)
        self.kind = kind
        self._start: Point2D | None = None
        self._current: Point2D | None = None

    def deactivate(self) -> None:
        super().deactivate()
        self._start = None
        self._current = None

    def mouse_press(self, position: Point2D, event: "QMouseEvent") -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start = position
        self._current = position
        return True

    def mouse_move(self, position: Point2D, event: "QMouseEvent") -> bool:
        if self._start is None:
            return False
        self._current = position
        return True

    def mouse_release(self, position: Point2D, event: "QMouseEvent") -> bool:
        if self._start is None:
            return False
        start = self._start
        self._start = None
        self._current = None
        distance = (position - start).length
        if distance < self._style.bond_length * self.MIN_LENGTH_FACTOR:
            return True
        end = self.clamp_to_page(snap_to_grid_angle(start, position, length=distance))
        self._document.add_arrow(start, end, self.kind)
        return True

    def preview_end(self) -> Point2D | None:
        if self._start is None or self._current is None:
            return None
        distance = (self._current - self._start).length
        snapped = snap_to_grid_angle(self._start, self._current, length=distance)
        return self.clamp_to_page(snapped)

    def paint_overlay(self, painter: QPainter) -> None:
        end = self.preview_end()
        if self._start is None or end is None:
            return
        pen = QPen(
            qcolor(self._style.preview_color),
            self._style.preview_width,
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind in FLOW_KINDS:
            # Vorschau der gebogenen Elektronenfluss-Pfeile
            painter.drawPath(arrow_path(ArrowObject(self._start, end, self.kind, DEFAULT_FLOW_BOW)))
        elif self.kind is ArrowKind.EQUILIBRIUM:
            # Vorschau als Doppellinie, damit sie dem fertigen ⇌ entspricht.
            preview = ArrowObject(self._start, end, self.kind)
            for shaft_start, shaft_end in arrow_shafts(preview, self._style):
                painter.drawLine(to_qpoint(shaft_start), to_qpoint(shaft_end))
        else:
            painter.drawLine(to_qpoint(self._start), to_qpoint(end))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*self._style.preview_color))
        painter.drawEllipse(to_qpoint(self._start), 4.0, 4.0)
