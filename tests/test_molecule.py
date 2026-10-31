from __future__ import annotations

import pytest

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import MAX_ATOM_CHARGE, Molecule, next_atom_charge


def test_add_atom_assigns_increasing_ids() -> None:
    molecule = Molecule()
    first = molecule.add_atom("C", Point2D(0.0, 0.0))
    second = molecule.add_atom("O", Point2D(10.0, 0.0))

    assert (first, second) == (0, 1)
    assert len(molecule) == 2
    assert molecule.atom(second).element == "O"


def test_reset_atom_makes_a_plain_carbon_and_keeps_bonds() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(BOND_LENGTH, 0.0), charge=1)
    bond = molecule.add_bond(left, nitrogen)
    molecule.set_label(nitrogen, "NO2")

    molecule.reset_atom(nitrogen)

    atom = molecule.atom(nitrogen)
    assert (atom.element, atom.charge, atom.label) == ("C", 0, "")
    assert molecule.bonds == (bond,)


def test_add_atom_accepts_tuple_positions() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", (5, 7))
    assert molecule.atom(atom_id).position == Point2D(5.0, 7.0)


def test_add_bond_orders_endpoints() -> None:
    molecule = Molecule()
    a = molecule.add_atom()
    b = molecule.add_atom()
    bond = molecule.add_bond(b, a, order=2)

    assert (bond.a, bond.b, bond.order) == (min(a, b), max(a, b), 2)
    assert molecule.bonds == (bond,)


def test_add_bond_rejects_invalid_input() -> None:
    molecule = Molecule()
    a = molecule.add_atom()
    b = molecule.add_atom()

    with pytest.raises(ValueError):
        molecule.add_bond(a, a)
    with pytest.raises(ValueError):
        molecule.add_bond(a, 99)
    with pytest.raises(ValueError):
        molecule.add_bond(a, b, order=4)

    molecule.add_bond(a, b)
    with pytest.raises(ValueError):
        molecule.add_bond(a, b)


def test_remove_atom_removes_its_bonds() -> None:
    molecule = Molecule()
    a = molecule.add_atom()
    b = molecule.add_atom()
    c = molecule.add_atom()
    molecule.add_bond(a, b)
    molecule.add_bond(b, c)

    molecule.remove_atom(b)

    assert molecule.bonds == ()
    assert len(molecule) == 2
    molecule.remove_atom(999)  # unbekannte ID bleibt ein No-Op


def test_neighbors_and_valence() -> None:
    molecule = Molecule()
    center = molecule.add_atom()
    left = molecule.add_atom()
    right = molecule.add_atom()
    molecule.add_bond(center, left, order=2)
    molecule.add_bond(center, right)

    assert set(molecule.neighbors(center)) == {left, right}
    assert molecule.degree(center) == 2
    assert molecule.bonded_valence(center) == 3


def test_find_atom_and_bond_near() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(a, b)

    assert molecule.find_atom_near(Point2D(2.0, 1.0), radius=10.0) == a
    assert molecule.find_atom_near(Point2D(200.0, 200.0), radius=10.0) is None

    bond = molecule.find_bond_near(Point2D(BOND_LENGTH / 2, 3.0), tolerance=5.0)
    assert bond is not None
    assert {bond.a, bond.b} == {a, b}


def test_clone_is_independent() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(a, b)

    copy = molecule.clone()
    assert copy == molecule

    copy.set_element(a, "N")
    copy.set_position(b, Point2D(0.0, 100.0))

    assert molecule.atom(a).element == "C"
    assert molecule.atom(b).position == Point2D(BOND_LENGTH, 0.0)


def test_clone_keeps_ids_after_removal() -> None:
    molecule = Molecule()
    molecule.add_atom()
    second = molecule.add_atom()
    molecule.remove_atom(second)

    copy = molecule.clone()
    new_id = copy.add_atom()
    assert new_id == 2


def test_atom_label_defaults_to_empty_and_is_stripped() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))

    assert molecule.atom_label(atom_id) == ""
    molecule.set_label(atom_id, "  NO2  ")
    assert molecule.atom_label(atom_id) == "NO2"

    molecule.set_label(atom_id, "")
    assert molecule.atom_label(atom_id) == ""


def test_clone_keeps_atom_labels() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    molecule.set_label(atom_id, "NO2")

    copy = molecule.clone()
    assert copy.atom_label(atom_id) == "NO2"

    copy.set_label(atom_id, "OH")
    assert molecule.atom_label(atom_id) == "NO2"


def test_custom_label_survives_reset_only_by_erase() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=2)
    molecule.set_label(atom_id, "NO2")

    molecule.reset_atom(atom_id)

    atom = molecule.atom(atom_id)
    assert atom.element == "C"
    assert atom.charge == 0
    assert atom.label == ""


def test_next_atom_charge_cycles_positive() -> None:
    charges = [0]
    for _ in range(MAX_ATOM_CHARGE):
        charges.append(next_atom_charge(charges[-1], 1))

    assert charges == list(range(MAX_ATOM_CHARGE + 1))
    assert next_atom_charge(MAX_ATOM_CHARGE, 1) == 0


def test_next_atom_charge_cycles_negative() -> None:
    charges = [0]
    for _ in range(MAX_ATOM_CHARGE):
        charges.append(next_atom_charge(charges[-1], -1))

    assert charges == [-value for value in range(MAX_ATOM_CHARGE + 1)]
    assert next_atom_charge(-MAX_ATOM_CHARGE, -1) == 0


def test_next_atom_charge_reaches_permanganate() -> None:
    """Mn in MnO₄⁻ trägt +7 – der Zyklus muss dorthin kommen."""
    charge = 0
    for _ in range(7):
        charge = next_atom_charge(charge, 1)

    assert charge == MAX_ATOM_CHARGE >= 7


def test_next_atom_charge_switches_the_sign_first() -> None:
    assert next_atom_charge(-2, 1) == 1
    assert next_atom_charge(2, -1) == -1
    assert next_atom_charge(-MAX_ATOM_CHARGE, 1) == 1


def test_next_atom_charge_needs_a_direction() -> None:
    with pytest.raises(ValueError):
        next_atom_charge(0, 0)


def test_charge_direction_is_normalized_and_cleared() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)

    molecule.set_charge_direction(atom_id, Point2D(0.0, 30.0))

    direction = molecule.atom(atom_id).charge_direction
    assert direction is not None
    assert direction.y == pytest.approx(1.0)

    molecule.set_charge_direction(atom_id, None)
    assert molecule.atom(atom_id).charge_direction is None

    molecule.set_charge_direction(atom_id, Point2D(-1.0, 0.0))
    molecule.reset_atom(atom_id)
    assert molecule.atom(atom_id).charge_direction is None


def test_equality_ignores_bond_order_in_list() -> None:
    first = Molecule()
    a = first.add_atom()
    b = first.add_atom()
    c = first.add_atom()
    first.add_bond(a, b)
    first.add_bond(b, c)

    second = Molecule()
    a2 = second.add_atom()
    b2 = second.add_atom()
    c2 = second.add_atom()
    second.add_bond(b2, c2)
    second.add_bond(a2, b2)

    assert first == second
    second.set_element(a2, "O")
    assert first != second


def test_bounds_and_center() -> None:
    molecule = Molecule()
    assert molecule.bounds() is None
    assert molecule.center() == Point2D(0.0, 0.0)

    molecule.add_atom("C", Point2D(0.0, 0.0))
    molecule.add_atom("C", Point2D(100.0, 50.0))
    low, high = molecule.bounds()
    assert low == Point2D(0.0, 0.0)
    assert high == Point2D(100.0, 50.0)
    assert molecule.center() == Point2D(50.0, 25.0)

