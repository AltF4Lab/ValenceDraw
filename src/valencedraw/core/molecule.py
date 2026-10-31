"""Molekülmodell: Atome, Bindungen und Nachbarschaftsabfragen.

Das Modell ist bewusst Qt-frei und ohne Chemie-Semantik (Valenzprüfung etc.).
Chemische Validierung passiert dort, wo sie gebraucht wird – beim Import/Export
über RDKit.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType

from .colors import RGB, normalize_color
from .elements import DEFAULT_ELEMENT
from .geometry import Point2D, as_point, bounding_box, distance_to_segment

MAX_BOND_ORDER = 3

#: Höchste Ladungsstufe des Klick-Zyklus (±1 → … → ±7 → 0).
#: Mn in Permanganat (MnO₄⁻) ist +7; höhere Werte (z. B. IrO₄⁺ mit +9) gibt
#: man über den Eingabedialog ein.
MAX_ATOM_CHARGE = 7

#: Teilladungen gibt es nur als δ⁺/δ⁻ (Betrag 1).
MAX_PARTIAL_CHARGE = 1

#: Höchstzahl freier Elektronenpaare je Atom (Oktett).
MAX_LONE_PAIRS = 4
#: Höchstzahl einzelner Elektronen (Radikale) je Atom.
MAX_RADICALS = 2
#: Winkel, innerhalb dessen ein Klick auf ein vorhandenes Elektron zeigt.
ELECTRON_HIT_ANGLE = 28.0


def _unit_vector(vector: "Point2D | tuple[float, float]") -> Point2D:
    """Richtungsvektor der Länge 1 (Nullvektoren werden zu ``(1, 0)``)."""
    point = as_point(vector)
    length = point.length
    if length <= 1e-9:
        return Point2D(1.0, 0.0)
    return point / length


def _unit_vectors(vectors: Iterable["Point2D | tuple[float, float]"]) -> tuple[Point2D, ...]:
    """Normalisiert eine Folge von Richtungsvektoren."""
    return tuple(_unit_vector(vector) for vector in vectors)


@dataclass
class Atom:
    """Ein Atom mit Element, Position (Szeneneinheiten) und Formalladung.

    ``label`` überschreibt bei Bedarf die Anzeige (z. B. ``NO2`` für eine
    nicht standardisierte Gruppe). Der Text darf Markup enthalten und wird
    automatisch hoch-/tiefgestellt.

    ``lone_pairs`` und ``radicals`` sind **Richtungen** (Einheitsvektoren vom
    Atom aus), in denen Elektronenpaare bzw. einzelne Elektronen sitzen. So
    bestimmt der Anwender, an welcher Stelle die Punkte erscheinen.
    ``charge_direction`` ist die Richtung der Ladung; ``None`` bedeutet, dass
    die freie Ecke automatisch bestimmt wird.

    ``partial_charge`` ist die Teilladung (``+1`` = δ⁺, ``-1`` = δ⁻, ``0`` =
    keine); ``partial_charge_direction`` legt ihre Richtung fest (``None`` =
    automatisch, bei zusätzlicher Formalladung die gegenüberliegende Ecke).

    ``color`` ist die Anzeigefarbe von Label, Ladung und Elektronen; ``None``
    bedeutet die Standardfarbe (schwarz).
    """

    element: str = DEFAULT_ELEMENT
    position: Point2D = Point2D()
    charge: int = 0
    label: str = ""
    lone_pairs: tuple[Point2D, ...] = ()
    radicals: tuple[Point2D, ...] = ()
    charge_direction: Point2D | None = None
    partial_charge: int = 0
    partial_charge_direction: Point2D | None = None
    color: RGB | None = None

    def __post_init__(self) -> None:
        self.position = as_point(self.position)
        self.element = self.element.strip() or DEFAULT_ELEMENT
        self.lone_pairs = _unit_vectors(self.lone_pairs)
        self.radicals = _unit_vectors(self.radicals)
        self.color = normalize_color(self.color)
        if self.charge_direction is not None:
            self.charge_direction = _unit_vector(self.charge_direction)
        if self.partial_charge_direction is not None:
            self.partial_charge_direction = _unit_vector(
                self.partial_charge_direction
            )


def charge_text(charge: int) -> str:
    """Formalladung als Text ohne Markup: ``+``, ``2+``, ``−``, ``7−``.

    Die Ladung wird hochgestellt hinter das Atomsymbol gesetzt; die leere
    Zeichenkette bedeutet „neutral“.

    >>> [charge_text(value) for value in (0, 1, 2, -1, -7)]
    ['', '+', '2+', '−', '7−']
    """
    if charge == 0:
        return ""
    sign = "+" if charge > 0 else "\u2212"
    magnitude = abs(charge)
    return f"{magnitude if magnitude > 1 else ''}{sign}"


def next_atom_charge(charge: int, sign: int) -> int:
    """Nächste Ladungsstufe beim Klicken auf ein Atom.

    ``sign`` ist ``+1`` (positiv) oder ``-1`` (negativ):

    * neutral oder entgegengesetzt geladen → ``±1``
    * gleiche Richtung → eine Stufe weiter (bis ``±MAX_ATOM_CHARGE``)
    * darüber hinaus → wieder neutral (``0``), damit der Klick zyklisch bleibt

    >>> [next_atom_charge(charge, 1) for charge in (0, 1, 6)]
    [1, 2, 7]
    >>> next_atom_charge(7, 1), next_atom_charge(-7, -1)
    (0, 0)
    >>> next_atom_charge(-2, 1), next_atom_charge(2, -1)
    (1, -1)
    """
    if sign == 0:
        raise ValueError("sign muss +1 oder -1 sein.")
    direction = 1 if sign > 0 else -1
    if charge * direction <= 0:
        return direction
    if abs(charge) >= MAX_ATOM_CHARGE:
        return 0
    return charge + direction


def partial_charge_text(partial_charge: int) -> str:
    """Teilladung als Text: ``δ⁺``, ``δ⁻`` oder leer (keine Teilladung).

    >>> [partial_charge_text(value) for value in (0, 1, -1)]
    ['', 'δ⁺', 'δ⁻']
    """
    if partial_charge == 0:
        return ""
    return "\u03b4\u207a" if partial_charge > 0 else "\u03b4\u207b"


def next_partial_charge(partial_charge: int, sign: int) -> int:
    """Nächste Teilladung beim Klicken.

    ``sign`` ist ``+1`` (δ⁺) oder ``-1`` (δ⁻): Eine andere Teilladung wird
    gesetzt, die gleiche wieder entfernt (δ⁺ → keine → δ⁺ …).

    >>> [next_partial_charge(0, 1), next_partial_charge(1, 1)]
    [1, 0]
    >>> next_partial_charge(0, -1), next_partial_charge(1, -1)
    (-1, -1)
    """
    if sign == 0:
        raise ValueError("sign muss +1 oder -1 sein.")
    direction = 1 if sign > 0 else -1
    return 0 if partial_charge == direction else direction


class BondStereo(str, Enum):
    """Keilstrich-Darstellung einer Einfachbindung."""

    NONE = "none"
    """Normale Linie."""

    WEDGE = "wedge"
    """Keil: die Bindung ragt aus der Zeichenebene heraus (dick)."""

    HASHED = "hashed"
    """Strichkeil: die Bindung verläuft hinter die Zeichenebene."""


@dataclass(frozen=True, order=True)
class Bond:
    """Eine Bindung zwischen zwei Atomen (Atom-IDs).

    ``side`` bestimmt bei einer Doppelbindung, auf welcher Seite der
    Bindungsachse die zweite Linie liegt (``+1``/``-1`` relativ zur Normalen).
    ``0`` bedeutet automatisch: im Ring nach innen, in der Kette auf die
    positive Seite. ``centered`` zeichnet beide Linien stattdessen symmetrisch
    zur Bindungsachse; ``side`` ist dann bedeutungslos.

    ``stereo`` legt die Keilstrich-Darstellung fest (nur bei Einfachbindungen).
    Die schmale Spitze sitzt an :attr:`narrow_atom`, die breite Seite am
    anderen Atom. ``color`` überschreibt die Standardfarbe der Linie.
    """

    a: int
    b: int
    order: int = 1
    side: int = 0
    centered: bool = False
    stereo: BondStereo = BondStereo.NONE
    stereo_from: int | None = None
    """Atom an der schmalen Spitze des Keils (``None`` = Atom ``a``)."""
    color: RGB | None = None

    @property
    def narrow_atom(self) -> int:
        """Atom an der schmalen Spitze des Keils."""
        return self.a if self.stereo_from is None else self.stereo_from

    @property
    def wide_atom(self) -> int:
        """Atom an der breiten Seite des Keils."""
        return self.b if self.narrow_atom == self.a else self.a

    def other(self, atom_id: int) -> int:
        """Die jeweils andere Atom-ID."""
        if atom_id == self.a:
            return self.b
        if atom_id == self.b:
            return self.a
        raise ValueError(f"Atom {atom_id} ist nicht Teil der Bindung {self}")

    def involves(self, atom_id: int) -> bool:
        return atom_id in (self.a, self.b)


class Molecule:
    """Sammlung von Atomen und Bindungen mit stabilen Atom-IDs."""

    def __init__(self) -> None:
        self._atoms: dict[int, Atom] = {}
        self._bonds: list[Bond] = []
        self._next_id: int = 0

    # -- Container -------------------------------------------------------
    @property
    def atoms(self) -> Mapping[int, Atom]:
        """Schreibgeschützte Sicht auf ``id -> Atom``."""
        return MappingProxyType(self._atoms)

    @property
    def bonds(self) -> tuple[Bond, ...]:
        return tuple(self._bonds)

    def __len__(self) -> int:
        return len(self._atoms)

    def __contains__(self, atom_id: object) -> bool:
        return atom_id in self._atoms

    def __iter__(self) -> Iterator[int]:
        return iter(self._atoms)

    def __repr__(self) -> str:  # pragma: no cover - nur Diagnose
        return f"Molecule(atoms={len(self._atoms)}, bonds={len(self._bonds)})"

    def is_empty(self) -> bool:
        return not self._atoms

    def atom(self, atom_id: int) -> Atom:
        """Atom per ID; wirft ``KeyError`` bei unbekannter ID."""
        return self._atoms[atom_id]

    def atom_ids(self) -> tuple[int, ...]:
        return tuple(self._atoms)

    # -- Aufbau ----------------------------------------------------------
    def add_atom(
        self,
        element: str = DEFAULT_ELEMENT,
        position: "Point2D | tuple[float, float]" = Point2D(),
        charge: int = 0,
        color: RGB | None = None,
    ) -> int:
        """Fügt ein Atom hinzu und liefert seine neue ID."""
        atom_id = self._next_id
        self._next_id += 1
        self._atoms[atom_id] = Atom(
            element=element,
            position=as_point(position),
            charge=charge,
            color=color,
        )
        return atom_id

    def add_bond(
        self,
        a: int,
        b: int,
        order: int = 1,
        side: int = 0,
        centered: bool = False,
        stereo: BondStereo = BondStereo.NONE,
        stereo_from: int | None = None,
        color: RGB | None = None,
    ) -> Bond:
        """Fügt eine Bindung hinzu.

        Wirft ``ValueError``, wenn ein Atom fehlt, beide IDs gleich sind oder
        die Bindung bereits existiert. ``side`` ist die manuelle Seite der
        zweiten Linie einer Doppelbindung (0 = automatisch); ``centered``
        zeichnet sie stattdessen symmetrisch zur Bindungsachse. ``stereo``
        verlangt eine Einfachbindung; ``stereo_from`` nennt das Atom an der
        schmalen Spitze (Vorgabe: Atom ``a``).
        """
        if a == b:
            raise ValueError("Eine Bindung benötigt zwei unterschiedliche Atome.")
        for atom_id in (a, b):
            if atom_id not in self._atoms:
                raise ValueError(f"Unbekanntes Atom: {atom_id}")
        if self.bond_between(a, b) is not None:
            raise ValueError(f"Zwischen {a} und {b} existiert bereits eine Bindung.")
        if order < 1 or order > MAX_BOND_ORDER:
            raise ValueError(f"Ungültige Bindungsordnung: {order}")
        is_double = order == 2
        is_single = order == 1
        narrow = stereo_from if stereo_from in (a, b) else a
        bond = Bond(
            a=min(a, b),
            b=max(a, b),
            order=order,
            side=0 if not is_double or centered else max(-1, min(1, int(side))),
            centered=is_double and bool(centered),
            stereo=stereo if is_single else BondStereo.NONE,
            stereo_from=narrow if is_single and stereo is not BondStereo.NONE else None,
            color=normalize_color(color),
        )
        self._bonds.append(bond)
        return bond

    def remove_atom(self, atom_id: int) -> None:
        """Entfernt ein Atom samt aller daran hängenden Bindungen."""
        if atom_id not in self._atoms:
            return
        self._bonds = [bond for bond in self._bonds if not bond.involves(atom_id)]
        del self._atoms[atom_id]

    def remove_bond(self, bond: Bond) -> None:
        try:
            index = self._bond_index(bond)
        except ValueError:
            return
        del self._bonds[index]

    def set_element(self, atom_id: int, element: str) -> None:
        self.atom(atom_id).element = element.strip() or DEFAULT_ELEMENT

    def set_position(self, atom_id: int, position: "Point2D | tuple[float, float]") -> None:
        self.atom(atom_id).position = as_point(position)

    def set_charge(self, atom_id: int, charge: int) -> None:
        self.atom(atom_id).charge = charge

    def set_charge_direction(
        self,
        atom_id: int,
        direction: "Point2D | tuple[float, float] | None",
    ) -> None:
        """Setzt die Richtung der Ladung (``None`` = automatische freie Ecke)."""
        atom = self.atom(atom_id)
        atom.charge_direction = None if direction is None else _unit_vector(direction)

    def set_partial_charge(self, atom_id: int, partial_charge: int) -> None:
        """Setzt die Teilladung: ``+1`` = δ⁺, ``-1`` = δ⁻, ``0`` = keine."""
        value = int(partial_charge)
        self.atom(atom_id).partial_charge = max(
            -MAX_PARTIAL_CHARGE, min(MAX_PARTIAL_CHARGE, value)
        )

    def set_partial_charge_direction(
        self,
        atom_id: int,
        direction: "Point2D | tuple[float, float] | None",
    ) -> None:
        """Setzt die Richtung der Teilladung (``None`` = automatisch)."""
        atom = self.atom(atom_id)
        atom.partial_charge_direction = (
            None if direction is None else _unit_vector(direction)
        )

    def set_atom_color(self, atom_id: int, color: RGB | None) -> None:
        """Setzt die Anzeigefarbe eines Atoms (``None`` = Standardfarbe)."""
        self.atom(atom_id).color = normalize_color(color)

    def set_bond_color(self, bond: Bond, color: RGB | None) -> None:
        """Setzt die Farbe einer Bindung (``None`` = Standardfarbe)."""
        index = self._bond_index(bond)
        self._bonds[index] = replace(
            self._bonds[index], color=normalize_color(color)
        )

    # -- Elektronenpaare und Radikale ------------------------------------
    def set_electrons(
        self,
        atom_id: int,
        lone_pairs: Iterable["Point2D | tuple[float, float]"] = (),
        radicals: Iterable["Point2D | tuple[float, float]"] = (),
    ) -> None:
        """Setzt Elektronenpaare und Radikale eines Atoms (Richtungen)."""
        atom = self.atom(atom_id)
        atom.lone_pairs = _unit_vectors(lone_pairs)
        atom.radicals = _unit_vectors(radicals)

    def add_lone_pair(
        self,
        atom_id: int,
        direction: "Point2D | tuple[float, float]",
    ) -> int:
        """Hängt ein Elektronenpaar in Richtung ``direction`` an; liefert den Index."""
        atom = self.atom(atom_id)
        if len(atom.lone_pairs) >= MAX_LONE_PAIRS:
            raise ValueError(f"Höchstens {MAX_LONE_PAIRS} Elektronenpaare je Atom.")
        atom.lone_pairs = (*atom.lone_pairs, _unit_vector(direction))
        return len(atom.lone_pairs) - 1

    def add_radical(
        self,
        atom_id: int,
        direction: "Point2D | tuple[float, float]",
    ) -> int:
        """Setzt ein einzelnes Elektron (Radikal); liefert den Index."""
        atom = self.atom(atom_id)
        if len(atom.radicals) >= MAX_RADICALS:
            raise ValueError(f"Höchstens {MAX_RADICALS} Radikale je Atom.")
        atom.radicals = (*atom.radicals, _unit_vector(direction))
        return len(atom.radicals) - 1

    def remove_lone_pair(self, atom_id: int, index: int) -> None:
        """Entfernt das Elektronenpaar mit dem Index ``index``."""
        atom = self.atom(atom_id)
        if 0 <= index < len(atom.lone_pairs):
            atom.lone_pairs = atom.lone_pairs[:index] + atom.lone_pairs[index + 1 :]

    def remove_radical(self, atom_id: int, index: int) -> None:
        """Entfernt das Radikal mit dem Index ``index``."""
        atom = self.atom(atom_id)
        if 0 <= index < len(atom.radicals):
            atom.radicals = atom.radicals[:index] + atom.radicals[index + 1 :]

    def electron_at(
        self,
        atom_id: int,
        direction: "Point2D | tuple[float, float]",
        max_angle_deg: float = ELECTRON_HIT_ANGLE,
    ) -> tuple[str, int] | None:
        """Elektron in Richtung ``direction``: ``("pair", i)``/``("radical", i)``."""
        atom = self.atom(atom_id)
        target = as_point(direction)
        if target.length <= 1e-9:
            return None
        target = _unit_vector(target)
        limit = math.cos(math.radians(max_angle_deg))
        best: tuple[str, int] | None = None
        best_dot = limit
        for kind, vectors in (("pair", atom.lone_pairs), ("radical", atom.radicals)):
            for index, vector in enumerate(vectors):
                dot = target.x * vector.x + target.y * vector.y
                if dot >= best_dot:
                    best, best_dot = (kind, index), dot
        return best

    def set_label(self, atom_id: int, label: str) -> None:
        """Setzt das Anzeige-Label eines Atoms (leer = Standardanzeige)."""
        self.atom(atom_id).label = label.strip()

    def atom_label(self, atom_id: int) -> str:
        """Hinterlegtes Label eines Atoms (leer, wenn keines gesetzt ist)."""
        return self.atom(atom_id).label

    def reset_atom(self, atom_id: int) -> None:
        """Macht aus einem Atom wieder einen unbeschrifteten Kohlenstoff.

        Element, Ladung und Label werden zurückgesetzt; Bindungen bleiben
        erhalten. Wird z. B. vom Radierer genutzt, um ein ``O``- oder
        Gruppenlabel zu entfernen, ohne die Struktur zu zerstören.
        """
        atom = self.atom(atom_id)
        atom.element = DEFAULT_ELEMENT
        atom.charge = 0
        atom.label = ""
        atom.lone_pairs = ()
        atom.radicals = ()
        atom.charge_direction = None
        atom.partial_charge = 0
        atom.partial_charge_direction = None

    def set_bond_order(
        self,
        bond: Bond,
        order: int,
        side: int | None = None,
        centered: bool = False,
    ) -> None:
        """Setzt Ordnung, Seite und Ausrichtung einer Bindung.

        ``side=None`` behält die bisherige Seite bei. Bei Einfach-/Dreifach-
        bindungen wird die Seite auf 0 zurückgesetzt. ``centered`` zeichnet
        eine Doppelbindung symmetrisch zur Bindungsachse (``side`` entfällt).
        Keilstrich-Darstellungen gibt es nur an Einfachbindungen.
        """
        if order < 1 or order > MAX_BOND_ORDER:
            raise ValueError(f"Ungültige Bindungsordnung: {order}")
        index = self._bond_index(bond)
        current = self._bonds[index]
        new_centered = order == 2 and bool(centered)
        if order != 2 or new_centered:
            new_side = 0
        elif side is None:
            new_side = current.side
        else:
            new_side = max(-1, min(1, int(side)))
        keeps_stereo = order == 1 and current.stereo is not BondStereo.NONE
        self._bonds[index] = replace(
            current,
            order=order,
            side=new_side,
            centered=new_centered,
            stereo=current.stereo if keeps_stereo else BondStereo.NONE,
            stereo_from=current.stereo_from if keeps_stereo else None,
        )

    def set_bond_stereo(
        self,
        bond: Bond,
        stereo: BondStereo,
        from_atom: int | None = None,
    ) -> None:
        """Setzt die Keilstrich-Darstellung einer Bindung.

        Keile gibt es nur an Einfachbindungen – Ordnung, Seite und
        Ausrichtung werden dabei auf „einfach, mittig“ zurückgesetzt.
        ``from_atom`` bestimmt die schmale Spitze; ohne gültige Angabe bleibt
        die bisherige Richtung erhalten.
        """
        index = self._bond_index(bond)
        current = self._bonds[index]
        if stereo is BondStereo.NONE:
            self._bonds[index] = replace(
                current, stereo=BondStereo.NONE, stereo_from=None
            )
            return
        narrow = from_atom if from_atom in (current.a, current.b) else current.narrow_atom
        self._bonds[index] = replace(
            current,
            order=1,
            side=0,
            centered=False,
            stereo=stereo,
            stereo_from=narrow,
        )

    def _bond_index(self, bond: Bond) -> int:
        """Index anhand der Endpunkte (unabhängig von Ordnung/Seite)."""
        for index, current in enumerate(self._bonds):
            if {current.a, current.b} == {bond.a, bond.b}:
                return index
        raise ValueError(f"Unbekannte Bindung: {bond}")

    def translate(self, atom_ids: Iterable[int], delta: Point2D) -> None:
        for atom_id in atom_ids:
            atom = self._atoms.get(atom_id)
            if atom is not None:
                atom.position = atom.position + delta

    def clear(self) -> None:
        self._atoms.clear()
        self._bonds.clear()

    # -- Abfragen --------------------------------------------------------
    def neighbors(self, atom_id: int) -> tuple[int, ...]:
        return tuple(bond.other(atom_id) for bond in self._bonds if bond.involves(atom_id))

    def shortest_cycle(self, bond: Bond) -> tuple[int, ...] | None:
        """Kürzester Ringweg über ``bond`` (ohne die Bindung selbst).

        Liefert die Atom-IDs des Wegs von ``bond.a`` nach ``bond.b``; zusammen
        mit der Bindung selbst bildet er einen Ring. ``None``, wenn die Bindung
        nicht in einem Ring liegt.
        """
        start, goal = bond.a, bond.b
        parents: dict[int, int | None] = {start: None}
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in self.neighbors(current):
                if {current, neighbor} == {start, goal}:
                    continue
                if neighbor in parents:
                    continue
                parents[neighbor] = current
                if neighbor == goal:
                    path = [goal]
                    node = goal
                    while parents[node] is not None:
                        node = parents[node]  # type: ignore[assignment]
                        path.append(node)
                    path.reverse()
                    return tuple(path)
                queue.append(neighbor)
        return None

    def degree(self, atom_id: int) -> int:
        return sum(1 for bond in self._bonds if bond.involves(atom_id))

    def bonded_valence(self, atom_id: int) -> int:
        """Summe der Bindungsordnungen an einem Atom."""
        return sum(bond.order for bond in self._bonds if bond.involves(atom_id))

    def bond_between(self, a: int, b: int) -> Bond | None:
        """Bindung zwischen ``a`` und ``b`` (oder ``None``)."""
        for bond in self._bonds:
            if {bond.a, bond.b} == {a, b}:
                return bond
        return None

    def find_atom_near(self, position: Point2D, radius: float) -> int | None:
        """Nächstgelegenes Atom innerhalb von ``radius`` (oder ``None``)."""
        best_id: int | None = None
        best_distance = radius
        for atom_id, atom in self._atoms.items():
            distance = atom.position.distance_to(position)
            if distance <= best_distance:
                best_id = atom_id
                best_distance = distance
        return best_id

    def find_bond_near(self, position: Point2D, tolerance: float) -> Bond | None:
        """Nächstgelegene Bindung innerhalb von ``tolerance`` (oder ``None``)."""
        best_bond: Bond | None = None
        best_distance = tolerance
        for bond in self._bonds:
            start = self._atoms[bond.a].position
            end = self._atoms[bond.b].position
            distance = distance_to_segment(position, start, end)
            if distance <= best_distance:
                best_bond = bond
                best_distance = distance
        return best_bond

    def bounds(self) -> tuple[Point2D, Point2D] | None:
        """Bounding-Box der Atompositionen (ohne Labelgrößen)."""
        return bounding_box(atom.position for atom in self._atoms.values())

    def center(self) -> Point2D:
        bounds = self.bounds()
        if bounds is None:
            return Point2D()
        low, high = bounds
        return Point2D((low.x + high.x) / 2, (low.y + high.y) / 2)

    # -- Kopie / Vergleich ----------------------------------------------
    def clone(self) -> "Molecule":
        """Tiefe Kopie (Atome werden dupliziert, IDs bleiben stabil)."""
        copy = Molecule()
        copy._atoms = {atom_id: replace(atom) for atom_id, atom in self._atoms.items()}
        copy._bonds = list(self._bonds)
        copy._next_id = self._next_id
        return copy

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Molecule):
            return NotImplemented
        return self._atoms == other._atoms and sorted(self._bonds) == sorted(other._bonds)

    __hash__ = None  # type: ignore[assignment]


def default_double_bond_side(
    molecule: Molecule,
    bond: Bond,
    cycle: tuple[int, ...] | None = None,
) -> int:
    """Bevorzugte Seite der zweiten Doppelbindungslinie (+1/-1).

    In einem Ring zeigt sie zur Ringmitte; in einer Kette auf die positive
    Normalenseite. Dadurch liegen Benzol-Doppelbindungen unabhängig von der
    Reihenfolge der Bindungen immer innen.
    """
    if cycle is None:
        cycle = molecule.shortest_cycle(bond)
    if cycle is None:
        return 1
    start = molecule.atom(bond.a).position
    end = molecule.atom(bond.b).position
    delta = end - start
    if delta.length <= 1e-9:
        return 1
    direction = delta / delta.length
    normal = Point2D(-direction.y, direction.x)
    midpoint = Point2D((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
    count = len(cycle)
    if count == 0:
        return 1
    centroid = Point2D(
        sum(molecule.atom(atom_id).position.x for atom_id in cycle) / count,
        sum(molecule.atom(atom_id).position.y for atom_id in cycle) / count,
    )
    offset = centroid - midpoint
    projection = normal.x * offset.x + normal.y * offset.y
    if abs(projection) <= 1e-9:
        return 1
    return 1 if projection > 0 else -1
