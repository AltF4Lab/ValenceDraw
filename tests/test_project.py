"""Tests für das Projektformat (``.valencedraw``)."""

from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind, ArrowObject, TextObject
from valencedraw.core.geometry import Point2D
from valencedraw.core.molecule import Molecule
from valencedraw.core.page import Orientation, Page, PageFormat
from valencedraw.document.project import (
    PROJECT_SUFFIX,
    Project,
    ProjectError,
    load_project,
    project_from_json,
    project_to_json,
    save_project,
)


def _project() -> Project:
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(40.0, 0.0), charge=-1)
    molecule.add_bond(carbon, oxygen, order=2)
    molecule.set_label(oxygen, "O^{2-}")
    return Project(
        molecule=molecule,
        texts=(TextObject(Point2D(10.0, 20.0), "**Ph** und *H_2O*"),),
        arrows=(
            ArrowObject(
                Point2D(0.0, 100.0), Point2D(80.0, 100.0), ArrowKind.EQUILIBRIUM
            ),
        ),
        page=Page(PageFormat.A5, Orientation.LANDSCAPE),
    )


def test_project_roundtrip_via_file(tmp_path) -> None:  # noqa: ANN001
    project = _project()

    path = save_project(project, tmp_path / f"test{PROJECT_SUFFIX}")
    loaded = load_project(path)

    assert loaded.molecule == project.molecule
    assert loaded.texts == project.texts
    assert loaded.arrows == project.arrows
    assert loaded.page == project.page


def test_project_roundtrip_via_json() -> None:
    project = _project()

    assert project_from_json(project_to_json(project)) == project


def test_project_keeps_the_charge_position(tmp_path) -> None:  # noqa: ANN001
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)
    molecule.set_charge_direction(atom_id, Point2D(0.0, 1.0))

    loaded = project_from_json(project_to_json(Project(molecule=molecule)))

    direction = loaded.molecule.atom(atom_id).charge_direction
    assert direction is not None
    assert direction.y == pytest.approx(1.0)


def test_project_keeps_double_bond_side() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("C", Point2D(40.0, 0.0))
    molecule.add_bond(left, right, order=2, side=-1)

    loaded = project_from_json(project_to_json(Project(molecule=molecule)))

    assert loaded.molecule.bonds[0].side == -1


def test_project_keeps_centered_double_bond() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("C", Point2D(40.0, 0.0))
    molecule.add_bond(left, right, order=2, centered=True)

    loaded = project_from_json(project_to_json(Project(molecule=molecule)))

    assert loaded.molecule.bonds[0].centered


def test_project_keeps_the_curved_flow_arrow() -> None:
    molecule = Molecule()
    molecule.add_atom("C", Point2D(0.0, 0.0))
    arrow = ArrowObject(
        Point2D(0.0, 0.0),
        Point2D(80.0, 0.0),
        ArrowKind.PAIR_FLOW,
        0.3,
        0.2,
        Point2D(0.6, 0.8),
    )
    project = Project(molecule=molecule, arrows=(arrow,))

    loaded = project_from_json(project_to_json(project))

    assert loaded.arrows[0] == arrow
    assert loaded.arrows[0].kind is ArrowKind.PAIR_FLOW
    assert loaded.arrows[0].bow == pytest.approx(0.3)
    assert loaded.arrows[0].bow_along == pytest.approx(0.2)
    tangent = loaded.arrows[0].apex_tangent
    assert tangent is not None
    assert tangent.x == pytest.approx(0.6)
    assert tangent.y == pytest.approx(0.8)


def test_project_keeps_atom_labels_and_charges(tmp_path) -> None:  # noqa: ANN001
    project = _project()

    loaded = load_project(save_project(project, tmp_path / "x.valencedraw"))

    oxygen = next(
        atom_id
        for atom_id in loaded.molecule.atom_ids()
        if loaded.molecule.atom(atom_id).element == "O"
    )
    assert loaded.molecule.atom_label(oxygen) == "O^{2-}"
    assert loaded.molecule.atom(oxygen).charge == -1


def test_project_keeps_bonds_after_deleted_atoms(tmp_path) -> None:  # noqa: ANN001
    molecule = Molecule()
    first = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("O", Point2D(40.0, 0.0))
    last = molecule.add_atom("N", Point2D(80.0, 0.0))
    molecule.add_bond(first, middle)
    molecule.add_bond(middle, last)
    molecule.remove_atom(middle)
    molecule.add_bond(first, last)

    loaded = load_project(save_project(Project(molecule=molecule), tmp_path / "x.valencedraw"))

    assert len(loaded.molecule) == 2
    assert len(loaded.molecule.bonds) == 1
    bond = loaded.molecule.bonds[0]
    elements = {
        loaded.molecule.atom(bond.a).element,
        loaded.molecule.atom(bond.b).element,
    }
    assert elements == {"C", "N"}


def test_empty_project_is_valid(tmp_path) -> None:  # noqa: ANN001
    loaded = load_project(save_project(Project(), tmp_path / "leer.valencedraw"))

    assert loaded.molecule.is_empty()
    assert loaded.texts == ()
    assert loaded.arrows == ()


def test_foreign_json_is_rejected() -> None:
    with pytest.raises(ProjectError):
        project_from_json('{"format": "irgendwas"}')


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(ProjectError):
        project_from_json("kein json")


def test_newer_project_version_is_rejected() -> None:
    with pytest.raises(ProjectError):
        project_from_json('{"format": "valencedraw", "version": 99}')
