from __future__ import annotations

import pytest

from valencedraw.core.geometry import BOND_LENGTH
from valencedraw.core.molecule import Molecule
from valencedraw.document.io import (
    RDKIT_AVAILABLE,
    ChemistryError,
    load_molecule,
    molecule_from_smiles,
    molecule_to_smiles,
    save_molecule,
)

pytestmark = pytest.mark.skipif(not RDKIT_AVAILABLE, reason="RDKit ist nicht installiert")


def test_smiles_import_builds_atoms_and_bonds() -> None:
    molecule = molecule_from_smiles("CCO")

    assert len(molecule) == 3
    assert len(molecule.bonds) == 2
    oxygen = next(
        atom_id for atom_id in molecule.atom_ids() if molecule.atom(atom_id).element == "O"
    )
    assert molecule.degree(oxygen) == 1


def test_smiles_import_scales_to_bond_length() -> None:
    molecule = molecule_from_smiles("CC")
    a, b = molecule.atom_ids()
    distance = molecule.atom(a).position.distance_to(molecule.atom(b).position)
    assert distance == pytest.approx(BOND_LENGTH, rel=0.15)


def test_smiles_roundtrip_benzene() -> None:
    molecule = molecule_from_smiles("c1ccccc1")
    assert molecule_to_smiles(molecule) == "c1ccccc1"


def test_molfile_roundtrip(tmp_path) -> None:  # noqa: ANN001
    molecule = molecule_from_smiles("CCO")
    path = save_molecule(molecule, tmp_path / "ethanol.mol")
    assert path.exists()

    reloaded = load_molecule(path)
    assert len(reloaded) == 3
    assert len(reloaded.bonds) == 2


def test_smiles_file_roundtrip(tmp_path) -> None:  # noqa: ANN001
    molecule = molecule_from_smiles("c1ccccc1")
    path = save_molecule(molecule, tmp_path / "benzene.smi")
    assert molecule_to_smiles(load_molecule(path)) == molecule_to_smiles(molecule)


def test_empty_molecule_cannot_be_exported() -> None:
    with pytest.raises(ChemistryError):
        molecule_to_smiles(Molecule())


def test_invalid_smiles_raises() -> None:
    with pytest.raises(ChemistryError):
        molecule_from_smiles("C1CC")


def test_unsupported_suffix_raises(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "struktur.xyz"
    path.write_text("irrelevant", encoding="utf-8")
    with pytest.raises(ChemistryError):
        load_molecule(path)
