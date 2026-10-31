"""Dokument: Molekül, freie Objekte, Auswahl und Undo-Stack.

Das Dokument ist die einzige Stelle, die Änderungen kennt. Werkzeuge rufen
``begin_edit``/``commit_edit`` (oder den ``edit``-Kontextmanager) auf, damit jede
Änderung genau einen Undo-Schritt erzeugt.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from typing import Iterable, Iterator

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from ..core.annotations import (
    DEFAULT_FLOW_BOW,
    FLOW_KINDS,
    ArrowKind,
    ArrowObject,
    TextObject,
)
from ..core.colors import RGB
from ..core.geometry import Point2D
from ..core.molecule import (
    MAX_LONE_PAIRS,
    MAX_RADICALS,
    Atom,
    Bond,
    BondStereo,
    Molecule,
    default_double_bond_side,
    next_atom_charge,
    next_partial_charge,
)
from ..core.page import Orientation, Page, PageFormat
from .clipboard import Fragment
from .commands import SnapshotCommand
from .state import DocumentState

UNDO_LIMIT = 200


def _copy_atom(target: Molecule, atom: Atom, position: Point2D) -> int:
    """Kopiert ein Atom inkl. Label, Elektronen, Ladungen, Richtungen und Farbe."""
    new_id = target.add_atom(atom.element, position, atom.charge, atom.color)
    if atom.label:
        target.set_label(new_id, atom.label)
    target.set_electrons(new_id, atom.lone_pairs, atom.radicals)
    target.set_charge_direction(new_id, atom.charge_direction)
    target.set_partial_charge(new_id, atom.partial_charge)
    target.set_partial_charge_direction(new_id, atom.partial_charge_direction)
    return new_id


def _copy_bonds(source: Molecule, target: Molecule, ids: dict[int, int]) -> None:
    """Kopiert alle Bindungen, deren beide Atome in ``ids`` abgebildet sind."""
    for bond in source.bonds:
        if bond.a in ids and bond.b in ids:
            target.add_bond(
                ids[bond.a],
                ids[bond.b],
                bond.order,
                bond.side,
                bond.centered,
                bond.stereo,
                ids[bond.narrow_atom],
                bond.color,
            )


class Document(QObject):
    """Hält den bearbeiteten Molekülzustand inklusive Undo-Historie."""

    changed = Signal()
    """Das Molekül wurde geändert (Zeichnung neu aufbauen)."""

    selection_changed = Signal()
    """Die Atomauswahl hat sich geändert."""

    page_changed = Signal(object)
    """Seitenformat oder Ausrichtung wurde geändert (Sendet das neue ``Page``)."""

    def __init__(
        self,
        molecule: Molecule | None = None,
        parent: QObject | None = None,
        *,
        page: Page | None = None,
    ) -> None:
        super().__init__(parent)
        self._molecule = molecule.clone() if molecule is not None else Molecule()
        self._texts: list[TextObject] = []
        self._arrows: list[ArrowObject] = []
        self._selection: set[int] = set()
        self._selected_texts: set[int] = set()
        self._selected_arrows: set[int] = set()
        self._page = page if page is not None else Page()
        self._pending: DocumentState | None = None
        self._undo_stack = QUndoStack(self)
        self._undo_stack.setUndoLimit(UNDO_LIMIT)

    # -- Zustand ---------------------------------------------------------
    @property
    def molecule(self) -> Molecule:
        """Das lebende Molekül. Änderungen daran müssen über ``edit`` laufen."""
        return self._molecule

    @property
    def texts(self) -> tuple[TextObject, ...]:
        return tuple(self._texts)

    @property
    def arrows(self) -> tuple[ArrowObject, ...]:
        return tuple(self._arrows)

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    @property
    def selection(self) -> frozenset[int]:
        return frozenset(self._selection)

    @property
    def text_selection(self) -> frozenset[int]:
        """Indizes der ausgewählten Texte (in :attr:`texts`)."""
        return frozenset(self._selected_texts)

    @property
    def arrow_selection(self) -> frozenset[int]:
        """Indizes der ausgewählten Pfeile (in :attr:`arrows`)."""
        return frozenset(self._selected_arrows)

    @property
    def selected_texts(self) -> tuple[TextObject, ...]:
        return tuple(self._texts[index] for index in sorted(self._selected_texts))

    @property
    def selected_arrows(self) -> tuple[ArrowObject, ...]:
        return tuple(self._arrows[index] for index in sorted(self._selected_arrows))

    # -- Seite -----------------------------------------------------------
    @property
    def page(self) -> Page:
        """Aktuelles Seitenformat inklusive Ausrichtung."""
        return self._page

    def set_page(self, page: Page) -> None:
        """Setzt Format/Ausrichtung; kein Undo-Schritt (reine Blatteinstellung)."""
        if page == self._page:
            return
        self._page = page
        self.page_changed.emit(page)

    def set_page_format(self, page_format: PageFormat) -> None:
        self.set_page(self._page.with_format(page_format))

    def set_orientation(self, orientation: Orientation) -> None:
        self.set_page(self._page.with_orientation(orientation))

    def state(self) -> DocumentState:
        """Aktueller Zustand als Snapshot (Molekül wird kopiert)."""
        return DocumentState(
            molecule=self._molecule.clone(),
            texts=tuple(self._texts),
            arrows=tuple(self._arrows),
        )

    def is_empty(self) -> bool:
        return self._molecule.is_empty() and not self._texts and not self._arrows

    # -- Undo/Redo -------------------------------------------------------
    def begin_edit(self) -> None:
        """Merkt sich den Zustand vor der kommenden Änderung."""
        if self._pending is None:
            self._pending = self.state()

    def cancel_edit(self) -> None:
        """Verwirft die begonnene Änderung (z. B. abgebrochener Drag)."""
        self._pending = None

    def commit_edit(self, text: str) -> bool:
        """Schließt die Änderung ab und legt einen Undo-Schritt an.

        Liefert ``True``, wenn sich tatsächlich etwas geändert hat.
        """
        before = self._pending
        self._pending = None
        if before is None:
            return False
        after = self.state()
        if before == after:
            return False
        self._undo_stack.push(SnapshotCommand(self, text, before, after))
        return True

    @contextmanager
    def edit(self, text: str) -> Iterator[Molecule]:
        """Kontextmanager für genau einen Undo-Schritt."""
        self.begin_edit()
        try:
            yield self._molecule
        except Exception:
            self.cancel_edit()
            raise
        else:
            self.commit_edit(text)

    def restore_snapshot(self, state: DocumentState) -> None:
        """Wird von ``SnapshotCommand`` aufgerufen."""
        self._molecule = state.molecule.clone()
        self._texts = list(state.texts)
        self._arrows = list(state.arrows)
        self._prune_selection()
        self.changed.emit()

    def touch(self) -> None:
        """Änderung ohne Undo-Schritt signalisieren (z. B. während eines Drags)."""
        self.changed.emit()

    def replace_molecule(
        self,
        molecule: Molecule,
        text: str = "Struktur ersetzen",
        keep_annotations: bool = False,
    ) -> None:
        """Ersetzt das komplette Molekül (undo-fähig)."""
        if keep_annotations:
            self.replace_content(molecule, self.texts, self.arrows, text=text)
        else:
            self.replace_content(molecule, text=text)

    def replace_content(
        self,
        molecule: Molecule | None = None,
        texts: tuple[TextObject, ...] = (),
        arrows: tuple[ArrowObject, ...] = (),
        page: Page | None = None,
        text: str = "Dokument laden",
    ) -> None:
        """Ersetzt Molekül, freie Objekte und optional die Seite (undo-fähig).

        Wird beim Öffnen einer Projektdatei genutzt, damit Texte und Pfeile
        erhalten bleiben.
        """
        with self.edit(text):
            if molecule is not None:
                self._molecule = molecule.clone()
            self._texts = list(texts)
            self._arrows = list(arrows)
        self.clear_selection()
        if page is not None:
            self.set_page(page)

    def mark_saved(self) -> None:
        """Aktuellen Zustand als „gespeichert" markieren."""
        self._undo_stack.setClean()

    def is_modified(self) -> bool:
        return not self._undo_stack.isClean()

    def _index_of_text(self, obj: TextObject) -> int | None:
        try:
            return self._texts.index(obj)
        except ValueError:
            return None

    def add_text(self, position: Point2D, markup: str, text: str = "Text einfügen") -> TextObject:
        """Fügt eine Textbeschriftung hinzu."""
        obj = TextObject(position, markup)
        with self.edit(text):
            self._texts.append(obj)
        return obj

    def replace_text(self, old: TextObject, markup: str, text: str = "Text ändern") -> TextObject:
        """Ersetzt den Inhalt einer Beschriftung (Position bleibt)."""
        new = old.with_markup(markup)
        with self.edit(text):
            index = self._index_of_text(old)
            if index is None:
                self._texts.append(new)
            else:
                self._texts[index] = new
        return new

    def remove_text(self, obj: TextObject, text: str = "Text löschen") -> None:
        with self.edit(text):
            index = self._index_of_text(obj)
            if index is not None:
                del self._texts[index]

    def add_arrow(
        self,
        start: Point2D,
        end: Point2D,
        kind: ArrowKind = ArrowKind.FORWARD,
        text: str = "Pfeil zeichnen",
    ) -> ArrowObject:
        """Fügt einen Reaktions- oder Elektronenfluss-Pfeil hinzu."""
        bow = DEFAULT_FLOW_BOW if kind in FLOW_KINDS else 0.0
        arrow = ArrowObject(start, end, kind, bow)
        with self.edit(text):
            self._arrows.append(arrow)
        return arrow

    def remove_arrow(self, arrow: ArrowObject, text: str = "Pfeil löschen") -> None:
        with self.edit(text):
            if arrow in self._arrows:
                self._arrows.remove(arrow)

    # -- Auswahl ---------------------------------------------------------
    def has_selection(self) -> bool:
        """Ist irgendein Objekt (Atom, Text oder Pfeil) ausgewählt?"""
        return bool(self._selection or self._selected_texts or self._selected_arrows)

    def is_text_selected(self, index: int) -> bool:
        return index in self._selected_texts

    def is_arrow_selected(self, index: int) -> bool:
        return index in self._selected_arrows

    def select_only(self, atom_id: int) -> None:
        """Wählt genau ein Atom aus (Texte/Pfeile werden abgewählt)."""
        self._set_selection_state({atom_id}, set(), set())

    def toggle_atom(self, atom_id: int) -> None:
        selection = set(self._selection)
        if atom_id in selection:
            selection.discard(atom_id)
        else:
            selection.add(atom_id)
        self._set_selection_state(selection, self._selected_texts, self._selected_arrows)

    def select_text(self, index: int, *, additive: bool = False) -> None:
        """Wählt eine Beschriftung aus (``additive`` = umschalten)."""
        texts = set(self._selected_texts)
        if additive:
            if index in texts:
                texts.discard(index)
            else:
                texts.add(index)
            self._set_selection_state(self._selection, texts, self._selected_arrows)
        else:
            self._set_selection_state(set(), {index}, set())

    def select_arrow(self, index: int, *, additive: bool = False) -> None:
        """Wählt einen Pfeil aus (``additive`` = umschalten)."""
        arrows = set(self._selected_arrows)
        if additive:
            if index in arrows:
                arrows.discard(index)
            else:
                arrows.add(index)
            self._set_selection_state(self._selection, self._selected_texts, arrows)
        else:
            self._set_selection_state(set(), set(), {index})

    def select_all(self) -> None:
        """Wählt alle Atome, Texte und Pfeile aus."""
        self._set_selection_state(
            set(self._molecule.atom_ids()),
            set(range(len(self._texts))),
            set(range(len(self._arrows))),
        )

    def select_objects(
        self,
        atom_ids: Iterable[int] = (),
        text_indices: Iterable[int] = (),
        arrow_indices: Iterable[int] = (),
        *,
        additive: bool = False,
    ) -> None:
        """Wählt mehrere Objekte auf einmal aus (z. B. per Rechteck).

        Mit ``additive`` bleibt die bisherige Auswahl erhalten.
        """
        if additive:
            self._set_selection_state(
                set(self._selection) | set(atom_ids),
                set(self._selected_texts) | set(text_indices),
                set(self._selected_arrows) | set(arrow_indices),
            )
            return
        self._set_selection_state(atom_ids, text_indices, arrow_indices)

    def clear_selection(self) -> None:
        self._set_selection_state(set(), set(), set())

    def _set_selection_state(
        self,
        atom_ids: Iterable[int],
        text_indices: Iterable[int],
        arrow_indices: Iterable[int],
    ) -> None:
        atoms = {atom_id for atom_id in atom_ids if atom_id in self._molecule}
        texts = {index for index in text_indices if 0 <= index < len(self._texts)}
        arrows = {index for index in arrow_indices if 0 <= index < len(self._arrows)}
        if (atoms, texts, arrows) == (
            self._selection,
            self._selected_texts,
            self._selected_arrows,
        ):
            return
        self._selection = atoms
        self._selected_texts = texts
        self._selected_arrows = arrows
        self.selection_changed.emit()

    def _prune_selection(self) -> None:
        self._set_selection_state(
            self._selection, self._selected_texts, self._selected_arrows
        )

    # -- Farben -----------------------------------------------------------
    def set_selection_color(
        self,
        color: RGB | None,
        text: str = "Farbe ändern",
    ) -> int:
        """Färbt alle ausgewählten Objekte (ein Undo-Schritt).

        Atome, Texte und Pfeile bekommen die Farbe direkt. Bindungen werden
        mitgefärbt, wenn **beide** Endatome ausgewählt sind – so lässt sich ein
        ganzer Ausschnitt oder über „Alles auswählen“ ein komplettes Molekül
        in einem Zug einfärben. ``None`` setzt die Standardfarbe zurück.

        Liefert die Anzahl der bearbeiteten Objekte (Atome, Bindungen, Texte
        und Pfeile).
        """
        if not self.has_selection():
            return 0
        selected = set(self._selection)
        bonds = [
            bond
            for bond in self._molecule.bonds
            if bond.a in selected and bond.b in selected
        ]
        count = len(selected) + len(bonds) + len(self._selected_texts) + len(
            self._selected_arrows
        )
        self.begin_edit()
        try:
            for atom_id in selected:
                self._molecule.set_atom_color(atom_id, color)
            for bond in bonds:
                self._molecule.set_bond_color(bond, color)
            for index in self._selected_texts:
                self._texts[index] = replace(self._texts[index], color=color)
            for index in self._selected_arrows:
                self._arrows[index] = replace(self._arrows[index], color=color)
        except Exception:
            self.cancel_edit()
            raise
        self.commit_edit(text)
        return count

    # -- Operationen -----------------------------------------------------
    def delete_selection(self) -> None:
        """Löscht ausgewählte Atome (inkl. Bindungen), Texte und Pfeile."""
        if not self.has_selection():
            return
        with self.edit("Löschen"):
            for atom_id in sorted(self._selection):
                self._molecule.remove_atom(atom_id)
            for index in sorted(self._selected_texts, reverse=True):
                if 0 <= index < len(self._texts):
                    del self._texts[index]
            for index in sorted(self._selected_arrows, reverse=True):
                if 0 <= index < len(self._arrows):
                    del self._arrows[index]
        self.clear_selection()

    def move_selection(self, delta: Point2D) -> None:
        """Verschiebt alle ausgewählten Objekte als eigenen Undo-Schritt."""
        if not self.has_selection() or delta.length == 0:
            return
        with self.edit("Objekte verschieben"):
            self._translate_selection(delta)

    def _translate_selection(self, delta: Point2D) -> None:
        if self._selection:
            self._molecule.translate(self._selection, delta)
        for index in self._selected_texts:
            obj = self._texts[index]
            self._texts[index] = obj.moved_to(obj.position + delta)
        for index in self._selected_arrows:
            arrow = self._arrows[index]
            self._arrows[index] = arrow.translated(delta)

    def set_text_object(self, index: int, obj: TextObject) -> None:
        """Ersetzt eine Beschriftung ohne Undo-Schritt (für Drag-Vorschauen)."""
        if 0 <= index < len(self._texts):
            self._texts[index] = obj

    def set_arrow_object(self, index: int, arrow: ArrowObject) -> None:
        """Ersetzt einen Pfeil ohne Undo-Schritt (für Drag-Vorschauen)."""
        if 0 <= index < len(self._arrows):
            self._arrows[index] = arrow

    # -- Kopieren / Einfügen ---------------------------------------------
    def copy_selection(self) -> Fragment:
        """Kopiert die Auswahl als Fragment.

        Übernommen werden die ausgewählten Atome (mit den Bindungen zwischen
        ihnen), die ausgewählten Texte und Pfeile.
        """
        molecule = Molecule()
        ids: dict[int, int] = {}
        for atom_id in sorted(self._selection):
            atom = self._molecule.atom(atom_id)
            ids[atom_id] = _copy_atom(molecule, atom, atom.position)
        _copy_bonds(self._molecule, molecule, ids)
        return Fragment(
            molecule=molecule,
            texts=tuple(self._texts[index] for index in sorted(self._selected_texts)),
            arrows=tuple(self._arrows[index] for index in sorted(self._selected_arrows)),
        )

    def paste_fragment(
        self,
        fragment: Fragment,
        delta: Point2D = Point2D(),
        text: str = "Einfügen",
    ) -> bool:
        """Fügt ein Fragment versetzt ein und wählt die neuen Objekte aus."""
        if fragment.is_empty():
            return False
        new_atom_ids: list[int] = []
        text_start = len(self._texts)
        arrow_start = len(self._arrows)
        with self.edit(text):
            ids: dict[int, int] = {}
            for old_id in fragment.molecule.atom_ids():
                atom = fragment.molecule.atom(old_id)
                new_id = _copy_atom(self._molecule, atom, atom.position + delta)
                ids[old_id] = new_id
                new_atom_ids.append(new_id)
            _copy_bonds(fragment.molecule, self._molecule, ids)
            self._texts.extend(
                obj.moved_to(obj.position + delta) for obj in fragment.texts
            )
            for arrow in fragment.arrows:
                self._arrows.append(arrow.translated(delta))
        self._set_selection_state(
            new_atom_ids,
            range(text_start, len(self._texts)),
            range(arrow_start, len(self._arrows)),
        )
        return True

    def cycle_bond_order(self, bond: Bond, text: str = "Bindungsordnung ändern") -> int:
        """Schaltet die Bindung weiter: 1 → 2 (zentriert) → 2 (Seite A) →
        2 (Seite B) → 3 → 1.

        Die erste Doppelbindung wird symmetrisch zur Bindungsachse gezeichnet.
        Danach liegt die zweite Linie im Ring innen (in der Kette auf der
        positiven Normalenseite), der nächste Klick klappt sie auf die andere
        Seite, danach folgt die Dreifachbindung.
        """
        current = self._molecule.bond_between(bond.a, bond.b) or bond
        if current.order == 1:
            new_order, new_side, new_centered = 2, 0, True
        elif current.centered:
            default_side = default_double_bond_side(self._molecule, current)
            new_order, new_side, new_centered = 2, default_side, False
        elif current.order == 2:
            default_side = default_double_bond_side(self._molecule, current)
            side = current.side if current.side != 0 else default_side
            if side == default_side:
                new_order, new_side, new_centered = 2, -default_side, False
            else:
                new_order, new_side, new_centered = 3, 0, False
        else:
            new_order, new_side, new_centered = 1, 0, False
        with self.edit(text):
            self._molecule.set_bond_order(current, new_order, new_side, new_centered)
        return new_order

    def set_bond_stereo(
        self,
        bond: Bond,
        stereo: BondStereo,
        from_atom: int | None = None,
        text: str = "Keilbindung setzen",
    ) -> None:
        """Setzt die Keilstrich-Darstellung einer Bindung (ein Undo-Schritt).

        ``from_atom`` legt die schmale Spitze fest; ohne Angabe bleibt die
        bisherige Richtung erhalten. ``BondStereo.NONE`` zeichnet wieder eine
        normale Linie.
        """
        with self.edit(text):
            self._molecule.set_bond_stereo(bond, stereo, from_atom)

    def flip_bond_stereo(self, bond: Bond, text: str = "Keilrichtung spiegeln") -> None:
        """Dreht die Spitze eines Keils an das andere Atom (ein Undo-Schritt)."""
        current = self._molecule.bond_between(bond.a, bond.b)
        if current is None or current.stereo is BondStereo.NONE:
            return
        with self.edit(text):
            self._molecule.set_bond_stereo(current, current.stereo, current.wide_atom)

    def set_atom_label(self, atom_id: int, label: str, text: str = "Atomlabel setzen") -> None:
        """Setzt oder entfernt das Anzeige-Label eines Atoms (undo-fähig)."""
        with self.edit(text):
            self._molecule.set_label(atom_id, label.strip())

    def set_atom_charge(self, atom_id: int, charge: int, text: str = "Ladung setzen") -> None:
        """Setzt die Formalladung eines Atoms (undo-fähig)."""
        with self.edit(text):
            self._molecule.set_charge(atom_id, int(charge))

    def set_atom_charge_position(
        self,
        atom_id: int,
        charge: int,
        direction: Point2D | None = None,
        text: str = "Ladung setzen",
    ) -> None:
        """Setzt Ladung und Position in einem Undo-Schritt."""
        with self.edit(text):
            self._molecule.set_charge(atom_id, int(charge))
            self._molecule.set_charge_direction(atom_id, direction)

    def cycle_atom_charge(
        self,
        atom_id: int,
        sign: int = 1,
        text: str = "Ladung ändern",
    ) -> int:
        """Schaltet die Ladung eine Stufe weiter und liefert die neue Ladung.

        ``sign=1`` zählt positiv (0 → + → 2+ → 3+ → 0), ``sign=-1`` negativ.
        Ist das Atom entgegengesetzt geladen, beginnt der Zyklus neu bei ±1.
        """
        new_charge = next_atom_charge(self._molecule.atom(atom_id).charge, sign)
        with self.edit(text):
            self._molecule.set_charge(atom_id, new_charge)
        return new_charge

    def set_atom_partial_charge(
        self,
        atom_id: int,
        partial_charge: int,
        direction: Point2D | None = None,
        text: str = "Teilladung setzen",
    ) -> None:
        """Setzt die Teilladung δ⁺/δ⁻ (und optional ihre Position) undo-fähig."""
        with self.edit(text):
            self._molecule.set_partial_charge(atom_id, partial_charge)
            self._molecule.set_partial_charge_direction(atom_id, direction)

    def cycle_atom_partial_charge(
        self,
        atom_id: int,
        sign: int = 1,
        text: str = "Teilladung ändern",
    ) -> int:
        """Schaltet die Teilladung weiter und liefert den neuen Wert.

        ``sign=1`` setzt δ⁺, ``sign=-1`` δ⁻; ein Klick auf die bereits
        gesetzte Teilladung entfernt sie wieder.
        """
        new_value = next_partial_charge(
            self._molecule.atom(atom_id).partial_charge, sign
        )
        with self.edit(text):
            self._molecule.set_partial_charge(atom_id, new_value)
        return new_value

    def remove_electron(
        self,
        atom_id: int,
        kind: str,
        index: int,
        text: str = "Elektronen entfernen",
    ) -> None:
        """Entfernt ein Elektronenpaar (``kind="pair"``) oder Radikal (undo-fähig)."""
        with self.edit(text):
            self._remove_electron_now(atom_id, kind, index)

    def _remove_electron_now(self, atom_id: int, kind: str, index: int) -> None:
        """Entfernt ein Elektron ohne eigenen Undo-Schritt."""
        if kind == "pair":
            self._molecule.remove_lone_pair(atom_id, index)
        else:
            self._molecule.remove_radical(atom_id, index)

    def toggle_electron(
        self,
        atom_id: int,
        direction: Point2D,
        radical: bool = False,
    ) -> bool:
        """Setzt oder entfernt ein Elektronenpaar bzw. Radikal (undo-fähig).

        Zeigt der Klick in die Richtung eines vorhandenen Elektrons, wird es
        entfernt – sonst neu gesetzt (``radical=True``: einzelnes Elektron).
        Liefert ``True``, wenn sich etwas geändert hat.
        """
        existing = self._molecule.electron_at(atom_id, direction)
        if existing is not None:
            kind, index = existing
            with self.edit("Elektronen entfernen"):
                self._remove_electron_now(atom_id, kind, index)
            return True

        atom = self._molecule.atom(atom_id)
        if radical:
            if len(atom.radicals) >= MAX_RADICALS:
                return False
            with self.edit("Radikal setzen"):
                self._molecule.add_radical(atom_id, direction)
            return True
        if len(atom.lone_pairs) >= MAX_LONE_PAIRS:
            return False
        with self.edit("Elektronenpaar setzen"):
            self._molecule.add_lone_pair(atom_id, direction)
        return True
