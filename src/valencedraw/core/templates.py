"""Ring-Templates für das Ring-Werkzeug.

Ein Template beschreibt einen Ring über die Anzahl der Ringatome und die
Bindungsordnungen der Ringbindungen. Die Geometrie wird als regelmäßiges
Vieleck mit der Kantenlänge ``BOND_LENGTH`` berechnet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import BOND_LENGTH, Point2D, polar
from .molecule import Molecule


@dataclass(frozen=True)
class RingTemplate:
    """Regelmäßiger Ring mit definierten Bindungsordnungen."""

    name: str
    size: int
    bond_orders: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.size < 3:
            raise ValueError("Ein Ring braucht mindestens drei Atome.")
        if len(self.bond_orders) != self.size:
            raise ValueError("Es muss genau eine Bindungsordnung pro Ringbindung geben.")

    def circumradius_for(self, bond_length: float = BOND_LENGTH) -> float:
        """Umkreisradius, sodass alle Kanten ``bond_length`` lang sind."""
        return bond_length / (2.0 * math.sin(math.pi / self.size))

    @property
    def circumradius(self) -> float:
        """Umkreisradius bei Standard-Bindungslänge (``BOND_LENGTH``)."""
        return self.circumradius_for(BOND_LENGTH)

    def vertices(
        self,
        center: Point2D,
        start_angle_deg: float = 90.0,
        bond_length: float = BOND_LENGTH,
    ) -> list[Point2D]:
        """Eckpunkte des Rings um ``center``.

        ``start_angle_deg`` gibt die Richtung vom Zentrum zum ersten Eckpunkt an;
        ein Winkel von 90° setzt die erste Ecke nach unten (y zeigt nach unten).
        ``bond_length`` legt die Kantenlänge fest (Einstellungen → Bindungslänge).
        """
        radius = self.circumradius_for(bond_length)
        return [
            polar(center, start_angle_deg - 360.0 * index / self.size, radius)
            for index in range(self.size)
        ]

    def bond_pairs(self) -> list[tuple[int, int]]:
        """Indexpaare der Ringbindungen (in Gegenrichtung der ``bond_orders``)."""
        return [(index, (index + 1) % self.size) for index in range(self.size)]


BENZENE = RingTemplate("Benzol", 6, (2, 1, 2, 1, 2, 1))
CYCLOHEXANE = RingTemplate("Cyclohexan", 6, (1, 1, 1, 1, 1, 1))
CYCLOPENTANE = RingTemplate("Cyclopentan", 5, (1, 1, 1, 1, 1))
CYCLOHEPTANE = RingTemplate("Cycloheptan", 7, (1, 1, 1, 1, 1, 1, 1))

RING_TEMPLATES: tuple[RingTemplate, ...] = (
    BENZENE,
    CYCLOHEXANE,
    CYCLOPENTANE,
    CYCLOHEPTANE,
)


def build_ring(
    template: RingTemplate,
    center: Point2D | None = None,
    bond_length: float = BOND_LENGTH,
) -> Molecule:
    """Baut das Ring-Template als Molekül (für Demo, Vorschau und Tests)."""
    molecule = Molecule()
    vertices = template.vertices(center or Point2D(), bond_length=bond_length)
    atom_ids = [molecule.add_atom("C", vertex) for vertex in vertices]
    for (start, end), order in zip(
        template.bond_pairs(), template.bond_orders, strict=True
    ):
        molecule.add_bond(atom_ids[start], atom_ids[end], order)
    return molecule


__all__ = [
    "BENZENE",
    "CYCLOHEPTANE",
    "CYCLOHEXANE",
    "CYCLOPENTANE",
    "RING_TEMPLATES",
    "RingTemplate",
    "build_ring",
]
