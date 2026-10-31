"""Automatische Wasserstoffatome an Heteroatomen.

Die H-Atome stehen nicht im Modell: Sie ergeben sich beim Zeichnen aus der
Bindungssumme und der Formalladung. Dadurch wird ein ``O`` am Bindungsende
automatisch zu ``OH`` und wieder zu ``O``, sobald eine zweite Bindung oder
eine Doppelbindung dazukommt.
"""

from __future__ import annotations

import pytest

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import Molecule
from valencedraw.core.valence import implicit_hydrogens
from valencedraw.render.painter import atom_label, atom_label_full, atom_label_markup


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _chain(first: str, second: str) -> tuple[Molecule, int]:
    """Zwei Atome mit einer Einfachbindung; liefert Molekül und zweites Atom."""
    molecule = Molecule()
    left = molecule.add_atom(first, Point2D(0.0, 0.0))
    right = molecule.add_atom(second, Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(left, right)
    return molecule, right


# -- Valenzregel ---------------------------------------------------------
@pytest.mark.parametrize(
    ("element", "charge", "bonded", "expected"),
    [
        ("O", 0, 1, 1),  # OH
        ("O", 0, 2, 0),  # Ether / Keton
        ("O", 0, 3, 0),  # keine negativen H-Zahlen
        ("O", 1, 1, 2),  # H2O+
        ("O", -1, 1, 0),  # O−
        ("N", 0, 1, 2),  # NH2
        ("N", 0, 2, 1),  # NH im Ring
        ("N", 0, 3, 0),  # tertiäres Amin
        ("N", 1, 4, 0),  # Ammonium
        ("S", 0, 1, 1),  # SH
        ("S", 0, 6, 0),  # Sulfon: keine H-Auffüllung
        ("Cl", 0, 1, 0),
        ("Mn", 0, 4, 0),  # unbekanntes Element ohne H
    ],
)
def test_implicit_hydrogens(
    element: str, charge: int, bonded: int, expected: int
) -> None:
    assert implicit_hydrogens(element, charge, bonded) == expected


# -- Anzeige -------------------------------------------------------------
def test_attached_oxygen_becomes_oh() -> None:
    molecule, oxygen = _chain("C", "O")

    assert atom_label_markup(molecule, oxygen) == "OH"
    assert atom_label(molecule, oxygen) == "OH"


def test_free_atom_stays_without_hydrogens() -> None:
    """Ein einzelnes Atom auf dem Blatt zeigt kein ``OH_2``."""
    molecule = Molecule()
    oxygen = molecule.add_atom("O", Point2D(0.0, 0.0))

    assert atom_label(molecule, oxygen) == "O"


def test_second_bond_turns_oh_into_o() -> None:
    molecule, oxygen = _chain("C", "O")
    other = molecule.add_atom("C", Point2D(2 * BOND_LENGTH, 0.0))

    molecule.add_bond(oxygen, other)

    assert atom_label(molecule, oxygen) == "O"


def test_double_bond_turns_oh_into_o() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_bond_order(molecule.bonds[0], 2)

    assert atom_label(molecule, oxygen) == "O"


def test_amine_shows_two_hydrogens() -> None:
    molecule, nitrogen = _chain("C", "N")

    assert atom_label_markup(molecule, nitrogen) == "NH_2"
    assert atom_label(molecule, nitrogen) == "NH2"


def test_ring_nitrogen_shows_one_hydrogen() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(BOND_LENGTH, 0.0))
    right = molecule.add_atom("C", Point2D(2 * BOND_LENGTH, 0.0))
    molecule.add_bond(left, nitrogen)
    molecule.add_bond(nitrogen, right)

    assert atom_label(molecule, nitrogen) == "NH"


def test_negative_charge_removes_the_hydrogen() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_charge(oxygen, -1)

    assert atom_label(molecule, oxygen) == "O"
    assert atom_label_full(molecule, oxygen) == "O\u2212"


def test_positive_charge_adds_a_hydrogen() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_charge(oxygen, 1)

    assert atom_label(molecule, oxygen) == "OH2"
    assert atom_label_full(molecule, oxygen) == "OH2+"


def test_electrons_do_not_change_the_hydrogen_count() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_electrons(
        oxygen,
        lone_pairs=(Point2D(0.0, 1.0),),
        radicals=(Point2D(0.0, -1.0),),
    )

    assert atom_label(molecule, oxygen) == "OH"


def test_partial_charge_does_not_change_the_hydrogen_count() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_partial_charge(oxygen, -1)

    assert atom_label(molecule, oxygen) == "OH"


def test_explicit_hydrogen_satisfies_the_valence() -> None:
    """Ein gezeichnetes H zählt als Bindung – das O zeigt dann kein zweites H."""
    molecule, oxygen = _chain("C", "O")
    hydrogen = molecule.add_atom("H", Point2D(2 * BOND_LENGTH, 0.0))

    molecule.add_bond(oxygen, hydrogen)

    assert atom_label(molecule, oxygen) == "O"
    assert atom_label(molecule, hydrogen) == "H"


def test_carbon_and_hydrogen_stay_unlabelled() -> None:
    molecule, _oxygen = _chain("C", "O")

    assert atom_label_markup(molecule, 0) == ""

    charged = molecule.add_atom("C", Point2D(0.0, BOND_LENGTH), charge=1)
    assert atom_label(molecule, charged) == "C"


def test_custom_label_keeps_precedence() -> None:
    molecule, oxygen = _chain("C", "O")

    molecule.set_label(oxygen, "OMe")

    assert atom_label(molecule, oxygen) == "OMe"
