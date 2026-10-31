"""Demo-Strukturen für Start und Tests."""

from __future__ import annotations

from .core.geometry import BOND_LENGTH, Point2D, polar
from .core.molecule import Molecule
from .core.templates import BENZENE, build_ring


def ethane() -> Molecule:
    """Ethan (CH3–CH3), zentriert um den Ursprung."""
    molecule = Molecule()
    half = BOND_LENGTH / 2
    left = molecule.add_atom("C", Point2D(-half, 0.0))
    right = molecule.add_atom("C", Point2D(half, 0.0))
    molecule.add_bond(left, right)
    return molecule


def benzene() -> Molecule:
    """Benzol mit alternierenden Doppelbindungen (Teststruktur für den Renderer)."""
    return build_ring(BENZENE)


def ethanol() -> Molecule:
    """Ethanol mit Heteroatom-Label (Teststruktur für Labels)."""
    molecule = Molecule()
    c1 = molecule.add_atom("C", Point2D(0.0, 0.0))
    c2 = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", polar(Point2D(BOND_LENGTH, 0.0), 60, BOND_LENGTH))
    molecule.add_bond(c1, c2)
    molecule.add_bond(c2, oxygen)
    return molecule
