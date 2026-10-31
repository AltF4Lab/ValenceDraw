"""Datei-I/O und Chemie-Backend (RDKit).

Unterstützte Formate im MVP: SMILES (``.smi``/``.smiles``), MDL-Molfile (``.mol``)
und SDF (``.sdf``). 2D-Koordinaten kommen von RDKit (CoordGen), damit importierte
Strukturen sofort sinnvoll aussehen.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from ..core.elements import DEFAULT_ELEMENT
from ..core.geometry import ANGSTROM, Point2D
from ..core.molecule import MAX_BOND_ORDER, BondStereo, Molecule

try:  # RDKit ist optional – die GUI läuft auch ohne.
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    from rdkit.Geometry import Point3D

    RDLogger.DisableLog("rdApp.*")
    RDKIT_AVAILABLE = True
except Exception:  # pragma: no cover - abhängig von der Installation
    Chem = None  # type: ignore[assignment]
    AllChem = None  # type: ignore[assignment]
    Point3D = None  # type: ignore[assignment]
    RDKIT_AVAILABLE = False


class ChemistryError(RuntimeError):
    """Fehler beim Umwandeln zwischen Modell und Chemie-Backend."""


def require_rdkit() -> None:
    if not RDKIT_AVAILABLE:
        raise ChemistryError(
            "RDKit ist nicht installiert. Bitte 'pip install rdkit' ausführen, "
            "um SMILES/MOL-Dateien lesen und schreiben zu können."
        )


# -- RDKit <-> Modell ----------------------------------------------------
def molecule_from_rdkit(mol: "Chem.Mol", scale: float = ANGSTROM) -> Molecule:
    """Wandelt ein RDKit-Molekül (mit 2D-Konformer) in unser Modell um."""
    require_rdkit()
    source = Chem.Mol(mol)
    with suppress(Exception):
        Chem.SanitizeMol(source)
    if source.GetNumConformers() == 0:
        AllChem.Compute2DCoords(source)
    # Aromatische Bindungen (Ordnung 1.5) in Einzel-/Doppelbindungen auflösen –
    # unser Modell kennt nur ganzzahlige Bindungsordnungen.
    with suppress(Exception):
        Chem.Kekulize(source, clearAromaticFlags=True)
    conformer = source.GetConformer()

    molecule = Molecule()
    index_to_id: dict[int, int] = {}
    for rd_atom in source.GetAtoms():
        position = conformer.GetAtomPosition(rd_atom.GetIdx())
        index_to_id[rd_atom.GetIdx()] = molecule.add_atom(
            element=rd_atom.GetSymbol(),
            # RDKit hat y nach oben, wir zeichnen mit y nach unten.
            position=Point2D(position.x * scale, -position.y * scale),
            charge=rd_atom.GetFormalCharge(),
        )
    for rd_bond in source.GetBonds():
        order = round(rd_bond.GetBondTypeAsDouble())
        order = max(1, min(order, MAX_BOND_ORDER))
        stereo, stereo_from = _stereo_from_rdkit(rd_bond, order, index_to_id)
        molecule.add_bond(
            index_to_id[rd_bond.GetBeginAtomIdx()],
            index_to_id[rd_bond.GetEndAtomIdx()],
            order=order,
            stereo=stereo,
            stereo_from=stereo_from,
        )
    return molecule


def _stereo_from_rdkit(
    rd_bond: "Chem.Bond",
    order: int,
    index_to_id: dict[int, int],
) -> tuple[BondStereo, int | None]:
    """Keil-/Strichkeil aus der molfile-Richtung (``BEGINWEDGE``/``BEGINDASH``).

    RDKit legt die Keilinformation beim Lesen eines Molblocks nicht in
    ``GetBondDir()`` ab, sondern als Eigenschaft ``_MolFileBondStereo``
    (1 = Keil, 6 = Strichkeil). Beides wird ausgewertet.
    """
    if order != 1:
        return BondStereo.NONE, None
    direction = rd_bond.GetBondDir()
    if direction == Chem.BondDir.BEGINWEDGE:
        stereo = BondStereo.WEDGE
    elif direction == Chem.BondDir.BEGINDASH:
        stereo = BondStereo.HASHED
    else:
        stereo = _molfile_stereo(rd_bond)
    if stereo is BondStereo.NONE:
        return BondStereo.NONE, None
    return stereo, index_to_id[rd_bond.GetBeginAtomIdx()]


def _molfile_stereo(rd_bond: "Chem.Bond") -> BondStereo:
    """Keil-Flag aus dem Molblock (``_MolFileBondStereo``: 1 = hoch, 6 = runter)."""
    value = rd_bond.GetPropsAsDict().get("_MolFileBondStereo")
    try:
        code = int(value)
    except (TypeError, ValueError):
        return BondStereo.NONE
    if code == 1:
        return BondStereo.WEDGE
    if code == 6:
        return BondStereo.HASHED
    return BondStereo.NONE


def molecule_to_rdkit(molecule: Molecule, scale: float = ANGSTROM) -> "Chem.Mol":
    """Wandelt unser Modell in ein sanitiziertes RDKit-Molekül um."""
    require_rdkit()
    if molecule.is_empty():
        raise ChemistryError("Das Molekül ist leer.")

    rw_mol = Chem.RWMol()
    index: dict[int, int] = {}
    for atom_id in molecule.atom_ids():
        atom = molecule.atom(atom_id)
        try:
            rd_atom = Chem.Atom(atom.element)
        except Exception:
            rd_atom = Chem.Atom(DEFAULT_ELEMENT)
        rd_atom.SetFormalCharge(atom.charge)
        index[atom_id] = rw_mol.AddAtom(rd_atom)

    bond_types = {
        1: Chem.BondType.SINGLE,
        2: Chem.BondType.DOUBLE,
        3: Chem.BondType.TRIPLE,
    }
    for bond in molecule.bonds:
        begin, end = bond.a, bond.b
        if bond.stereo is not BondStereo.NONE:
            # RDKit verankert die Keilspitze am ersten Atom der Bindung.
            begin, end = bond.narrow_atom, bond.wide_atom
        rw_mol.AddBond(
            index[begin], index[end], bond_types.get(bond.order, Chem.BondType.SINGLE)
        )

    mol = rw_mol.GetMol()
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # z. B. unerlaubte Valenz
        raise ChemistryError(f"RDKit akzeptiert die Struktur nicht: {exc}") from exc

    _apply_stereo_directions(mol, molecule, index)

    conformer = Chem.Conformer(mol.GetNumAtoms())
    for atom_id, rd_index in index.items():
        position = molecule.atom(atom_id).position
        conformer.SetAtomPosition(
            rd_index, Point3D(position.x / scale, -position.y / scale, 0.0)
        )
    mol.AddConformer(conformer, assignId=True)
    return mol


def _apply_stereo_directions(
    mol: "Chem.Mol",
    molecule: Molecule,
    index: dict[int, int],
) -> None:
    """Überträgt Keil-/Strichkeile als Bindungsrichtung ins RDKit-Molekül.

    Die Keilspitze muss dabei am Beginn-Atom der Bindung sitzen – deshalb
    werden Stereo-Bindungen in :func:`molecule_to_rdkit` in Keilrichtung
    eingetragen.
    """
    for bond in molecule.bonds:
        if bond.stereo is BondStereo.NONE:
            continue
        rd_bond = mol.GetBondBetweenAtoms(
            index[bond.narrow_atom], index[bond.wide_atom]
        )
        if rd_bond is None:  # pragma: no cover - inkonsistentes Modell
            continue
        rd_bond.SetBondDir(
            Chem.BondDir.BEGINWEDGE
            if bond.stereo is BondStereo.WEDGE
            else Chem.BondDir.BEGINDASH
        )


# -- Einzelformate -------------------------------------------------------
def molecule_from_smiles(smiles: str, scale: float = ANGSTROM) -> Molecule:
    """Baut ein Molekül aus SMILES inklusive 2D-Layout."""
    require_rdkit()
    text = smiles.strip().split()[0] if smiles.strip() else ""
    if not text:
        raise ChemistryError("Leerer SMILES-String.")
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise ChemistryError(f"SMILES konnte nicht gelesen werden: {smiles!r}")
    AllChem.Compute2DCoords(mol)
    return molecule_from_rdkit(mol, scale=scale)


def molecule_to_smiles(molecule: Molecule) -> str:
    require_rdkit()
    return Chem.MolToSmiles(molecule_to_rdkit(molecule))


def molecule_from_molblock(block: str, scale: float = ANGSTROM) -> Molecule:
    require_rdkit()
    mol = Chem.MolFromMolBlock(block, removeHs=False, sanitize=True)
    if mol is None:
        raise ChemistryError("Molfile konnte nicht gelesen werden.")
    return molecule_from_rdkit(mol, scale=scale)


def molecule_to_molblock(molecule: Molecule) -> str:
    require_rdkit()
    return Chem.MolToMolBlock(molecule_to_rdkit(molecule))


# -- Dateien -------------------------------------------------------------
SMILES_SUFFIXES = frozenset({".smi", ".smiles"})
SDF_SUFFIXES = frozenset({".sdf", ".mol"})


def load_molecule(path: str | Path, scale: float = ANGSTROM) -> Molecule:
    """Lädt eine Struktur anhand der Dateiendung."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    text = file_path.read_text(encoding="utf-8")
    if suffix in SMILES_SUFFIXES:
        return molecule_from_smiles(text, scale=scale)
    if suffix in SDF_SUFFIXES:
        return molecule_from_molblock(text, scale=scale)
    raise ChemistryError(f"Nicht unterstütztes Dateiformat: {suffix or '(ohne Endung)'}")


def save_molecule(molecule: Molecule, path: str | Path) -> Path:
    """Speichert eine Struktur anhand der Dateiendung."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix in SMILES_SUFFIXES:
        content = molecule_to_smiles(molecule) + "\n"
    elif suffix in SDF_SUFFIXES:
        content = molecule_to_molblock(molecule)
    else:
        raise ChemistryError(f"Nicht unterstütztes Dateiformat: {suffix or '(ohne Endung)'}")
    file_path.write_text(content, encoding="utf-8")
    return file_path
