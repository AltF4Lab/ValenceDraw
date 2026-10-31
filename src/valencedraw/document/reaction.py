"""Reaktionsanalyse für die Ansatztabelle.

Die Zeichnung enthält ein einziges Molekülobjekt (alle Atome und Bindungen).
Für die Tabelle werden daraus die **zusammenhängenden Komponenten** gebildet
und relativ zum Reaktionspfeil einsortiert:

* links vom Pfeil → Edukt
* rechts vom Pfeil → Produkt
* über dem Pfeil → Reagenz (Text oder gezeichnete Struktur)
* unter dem Pfeil → Lösemittel (wird nicht aufgeführt)
* Text mit ``-R``/``−R`` → abgehendes Nebenprodukt (wird nicht aufgeführt)

Molare Massen und Summenformeln kommen aus RDKit (inkl. impliziter
Wasserstoffe). Die Äquivalente werden – wenn möglich – aus der Atom- und
Ladungsbilanz bestimmt; andernfalls starten alle Strukturen mit 1 eq.
"""

from __future__ import annotations

import math
import re
from collections import deque
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction

from ..core.annotations import ArrowObject, TextObject
from ..core.geometry import Point2D
from ..core.markup import to_plain_text
from ..core.molecule import Molecule
from ..core.stoichiometry import RowRole, StoichiometryRow, StoichiometryTable
from ..render.painter import text_bounds
from .io import RDKIT_AVAILABLE, molecule_to_rdkit

try:  # RDKit ist optional – ohne RDKit bleibt die molare Masse leer.
    from rdkit.Chem import Descriptors, rdMolDescriptors
except Exception:  # pragma: no cover - abhängig von der Installation
    Descriptors = None  # type: ignore[assignment]
    rdMolDescriptors = None  # type: ignore[assignment]

_LEAVING_GROUP = re.compile(r"[-−–]\s*R\b", re.IGNORECASE)
"""Erkennt abgehende Gruppen wie ``-R``, ``−R`` oder ``OMe-R``."""


class ReactionAnalysisError(ValueError):
    """Die Auswahl enthält keine auswertbare Reaktionsgleichung."""


@dataclass
class ReactionSpecies:
    """Eine aus der Zeichnung erkannte Substanz."""

    name: str
    role: RowRole
    formula: str = ""
    molar_mass: float | None = None
    equivalents: float | None = None
    atom_ids: tuple[int, ...] = ()
    element_counts: tuple[tuple[str, int], ...] = ()
    charge: int = 0


@dataclass(frozen=True)
class ReactionAnalysis:
    """Ergebnis der Reaktionsanalyse."""

    arrow: ArrowObject
    educts: tuple[ReactionSpecies, ...]
    reagents: tuple[ReactionSpecies, ...]
    products: tuple[ReactionSpecies, ...]
    solvents: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()

    @property
    def species(self) -> tuple[ReactionSpecies, ...]:
        """Alle aufzuführenden Substanzen in Tabellenreihenfolge."""
        return self.educts + self.reagents + self.products


def analyze_reaction(
    molecule: Molecule,
    texts: Sequence[TextObject],
    arrows: Sequence[ArrowObject],
    *,
    selected_atoms: Collection[int] | None = None,
    selected_texts: Collection[int] | None = None,
    selected_arrows: Collection[int] | None = None,
) -> ReactionAnalysis:
    """Wertet die (ausgewählte) Reaktionsgleichung aus.

    Fehlt eine Teilauswahl, werden alle Objekte des Dokuments verwendet. So
    funktioniert der Befehl sowohl nach „Alles auswählen“ als auch bei einer
    gezielten Auswahl.
    """
    arrow = _choose_arrow(arrows, selected_arrows)
    atom_ids = _selected_or_all(molecule.atom_ids(), selected_atoms)
    text_indices = _selected_indices(len(texts), selected_texts)

    direction = arrow.direction
    up_normal = Point2D(-direction.y, direction.x)
    if up_normal.y > 0:
        up_normal = Point2D(-up_normal.x, -up_normal.y)
    length = max(arrow.length, 1e-9)

    educts: list[ReactionSpecies] = []
    reagent_entries: list[tuple[float, ReactionSpecies]] = []
    products: list[ReactionSpecies] = []
    solvents: list[str] = []
    ignored: list[str] = []

    for number, component in enumerate(_components(molecule, atom_ids), start=1):
        center = _component_center(molecule, component)
        offset = center - arrow.midpoint
        perpendicular = offset.x * up_normal.x + offset.y * up_normal.y
        along = (
            (center - arrow.start).x * direction.x
            + (center - arrow.start).y * direction.y
        ) / length

        if along <= 0.02:
            role = RowRole.EDUKT
        elif along >= 0.98:
            role = RowRole.PRODUKT
        elif perpendicular > 0:
            role = RowRole.REAGENZ
        else:
            # Struktur unter dem Pfeil = Lösemittel; nicht in die Tabelle.
            continue

        species = _species_for_component(molecule, component, role, number)
        if role is RowRole.EDUKT:
            educts.append(species)
        elif role is RowRole.PRODUKT:
            products.append(species)
        else:
            # Reagenzien werden nie als Summenformel ausgewertet. Die Nummer
            # wird erst nach dem Einsortieren aller Reagenzien vergeben.
            reagent_entries.append((center.x, species))

    for index in text_indices:
        obj = texts[index]
        plain = to_plain_text(obj.markup).strip()
        if not plain:
            continue
        if _LEAVING_GROUP.search(plain):
            ignored.append(plain)
            continue
        rect = text_bounds(obj)
        center = Point2D(rect.center().x(), rect.center().y())
        offset = center - arrow.midpoint
        perpendicular = offset.x * up_normal.x + offset.y * up_normal.y
        if perpendicular > 0:
            # Auch Reagenz-Texte werden generisch benannt („Reagenz 1“ …);
            # der Anwender kann den Namen in der Tabelle selbst setzen.
            reagent_entries.append(
                (center.x, ReactionSpecies("", RowRole.REAGENZ))
            )
        elif perpendicular < 0:
            solvents.append(plain)
        # Texte genau auf der Pfeilhöhe sind Beschriftungen, keine Reagenzien.

    reagent_entries.sort(key=lambda entry: entry[0])
    reagents = [species for _x, species in reagent_entries]
    for number, species in enumerate(reagents, start=1):
        species.name = f"Reagenz {number}"

    _assign_equivalents(educts, products)

    if not educts and not reagents and not products:
        raise ReactionAnalysisError(
            "In der Auswahl wurden keine Substanzen gefunden. Bitte die "
            "Reaktionsgleichung inklusive Pfeil auswählen."
        )
    return ReactionAnalysis(
        arrow,
        tuple(educts),
        tuple(reagents),
        tuple(products),
        tuple(solvents),
        tuple(ignored),
    )


def table_from_analysis(analysis: ReactionAnalysis) -> StoichiometryTable:
    """Baut das Rechenmodell der Ansatztabelle aus dem Analyseergebnis."""
    rows = [
        StoichiometryRow(
            species.name,
            species.role,
            molar_mass=species.molar_mass,
            equivalents=species.equivalents,
        )
        for species in analysis.species
    ]
    return StoichiometryTable(rows)


# -- Auswahl und Pfeil ---------------------------------------------------
def _choose_arrow(
    arrows: Sequence[ArrowObject],
    selection: Collection[int] | None,
) -> ArrowObject:
    """Erster ausgewählter Reaktionspfeil (Elektronenfluss-Pfeile zählen nicht)."""
    indices = _selected_indices(len(arrows), selection)
    for index in indices:
        if not arrows[index].is_flow:
            return arrows[index]
    raise ReactionAnalysisError(
        "Kein Reaktionspfeil in der Auswahl. Bitte den Pfeil mit auswählen."
    )


def _selected_or_all(
    all_ids: tuple[int, ...],
    selection: Collection[int] | None,
) -> set[int]:
    """Ausgewählte IDs – oder alle, wenn nichts ausgewählt ist."""
    if selection:
        return {atom_id for atom_id in selection if atom_id in all_ids}
    return set(all_ids)


def _selected_indices(
    total: int,
    selection: Collection[int] | None,
) -> list[int]:
    """Ausgewählte Indizes – oder alle, wenn nichts ausgewählt ist."""
    if selection:
        return sorted(index for index in selection if 0 <= index < total)
    return list(range(total))


# -- Komponenten ---------------------------------------------------------
def _components(molecule: Molecule, atom_ids: Collection[int]) -> list[tuple[int, ...]]:
    """Zusammenhängende Molekülteile der Auswahl (per Bindungen verbunden)."""
    allowed = set(atom_ids)
    adjacency: dict[int, list[int]] = {atom_id: [] for atom_id in allowed}
    for bond in molecule.bonds:
        if bond.a in allowed and bond.b in allowed:
            adjacency[bond.a].append(bond.b)
            adjacency[bond.b].append(bond.a)

    seen: set[int] = set()
    result: list[tuple[int, ...]] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        queue: deque[int] = deque([start])
        seen.add(start)
        component: list[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        result.append(tuple(sorted(component)))

    result.sort(key=lambda ids: _component_center(molecule, ids).x)
    return result


def _component_center(molecule: Molecule, atom_ids: Sequence[int]) -> Point2D:
    """Mittelpunkt einer Komponente (Mittel der Atompositionen)."""
    count = len(atom_ids)
    if count == 0:
        return Point2D()
    return Point2D(
        sum(molecule.atom(atom_id).position.x for atom_id in atom_ids) / count,
        sum(molecule.atom(atom_id).position.y for atom_id in atom_ids) / count,
    )


def _sub_molecule(molecule: Molecule, atom_ids: Collection[int]) -> Molecule:
    """Kopie der Komponente mit eigenen Atom-IDs (für RDKit)."""
    result = Molecule()
    mapping: dict[int, int] = {}
    for atom_id in sorted(atom_ids):
        atom = molecule.atom(atom_id)
        new_id = result.add_atom(atom.element, atom.position, atom.charge, atom.color)
        if atom.label:
            result.set_label(new_id, atom.label)
        mapping[atom_id] = new_id
    for bond in molecule.bonds:
        if bond.a in mapping and bond.b in mapping:
            result.add_bond(
                mapping[bond.a],
                mapping[bond.b],
                bond.order,
                bond.side,
                bond.centered,
                bond.stereo,
                mapping[bond.narrow_atom],
                bond.color,
            )
    return result


def _species_for_component(
    molecule: Molecule,
    atom_ids: tuple[int, ...],
    role: RowRole,
    number: int,
) -> ReactionSpecies:
    """Baut eine Tabellenzeile aus einer gezeichneten Komponente.

    Reagenzien über dem Pfeil werden bewusst **nicht** über RDKit ausgewertet:
    Sie bekommen weder Summenformel noch molare Masse und heißen zunächst nur
    „Reagenz N“.
    """
    if role is RowRole.REAGENZ:
        return ReactionSpecies("", role, atom_ids=atom_ids)
    sub = _sub_molecule(molecule, atom_ids)
    formula, molar_mass, rd_mol = _formula_and_mass(sub)
    counts, charge = _rdkit_counts(rd_mol)
    name = formula or f"Molekül {number}"
    return ReactionSpecies(
        name,
        role,
        formula,
        molar_mass,
        None,
        atom_ids,
        counts,
        charge,
    )


def _formula_and_mass(molecule: Molecule):
    """Summenformel und molare Masse über RDKit (``None`` bei Fehlern)."""
    if not RDKIT_AVAILABLE or rdMolDescriptors is None or Descriptors is None:
        return "", None, None
    try:
        rd_mol = molecule_to_rdkit(molecule)
        return (
            rdMolDescriptors.CalcMolFormula(rd_mol),
            float(Descriptors.MolWt(rd_mol)),
            rd_mol,
        )
    except Exception:  # ungültige Valenzen, RDKit fehlt, …
        return "", None, None


def _rdkit_counts(rd_mol) -> tuple[tuple[tuple[str, int], ...], int]:  # noqa: ANN001
    """Atomanzahlen inkl. impliziter Wasserstoffe und Gesamtladung."""
    if rd_mol is None:
        return (), 0
    counts: dict[str, int] = {}
    charge = 0
    for atom in rd_mol.GetAtoms():
        symbol = atom.GetSymbol()
        counts[symbol] = counts.get(symbol, 0) + 1
        hydrogens = atom.GetTotalNumHs()
        if hydrogens:
            counts["H"] = counts.get("H", 0) + hydrogens
        charge += atom.GetFormalCharge()
    return tuple(sorted(counts.items())), charge


# -- Äquivalente / Bilanz ------------------------------------------------
def _assign_equivalents(
    educts: list[ReactionSpecies],
    products: list[ReactionSpecies],
) -> None:
    """Setzt die Äquivalente aus der Bilanz (sonst 1 für alle Strukturen).

    Reagenzien über dem Pfeil werden bewusst nicht in die Bilanz aufgenommen:
    Sie können reine Texte ohne Summenformel sein und werden vom Anwender
    ohnehin über die Tabelle ergänzt.
    """
    balanced = _balance(educts, products)

    if balanced is None:
        for species in (*educts, *products):
            species.equivalents = 1.0
        return
    educt_eqs, product_eqs = balanced
    for species, value in zip(educts, educt_eqs, strict=True):
        species.equivalents = value
    for species, value in zip(products, product_eqs, strict=True):
        species.equivalents = value


def _balance(
    educts: Sequence[ReactionSpecies],
    products: Sequence[ReactionSpecies],
) -> tuple[list[float], list[float]] | None:
    """Ganzzahlige Atom-/Ladungsbilanz als Äquivalente (oder ``None``)."""
    if not educts or not products:
        return None
    if any(not species.element_counts for species in (*educts, *products)):
        return None
    species = [*educts, *products]
    signs = [1] * len(educts) + [-1] * len(products)
    counts = [dict(item.element_counts) for item in species]
    charges = [item.charge for item in species]

    elements = sorted({element for entry in counts for element in entry})
    matrix: list[list[Fraction]] = []
    for element in elements:
        matrix.append(
            [
                Fraction(sign * entry.get(element, 0))
                for entry, sign in zip(counts, signs, strict=True)
            ]
        )
    if any(charges):
        matrix.append(
            [Fraction(sign * charge) for charge, sign in zip(charges, signs, strict=True)]
        )

    vector = _nullspace_vector(matrix)
    if vector is None:
        return None
    if any(value <= 0 for value in vector):
        return None
    reference = vector[0]
    if reference <= 0:
        return None
    values = [float(value / reference) for value in vector]
    if not math.isfinite(sum(values)):
        return None
    return values[: len(educts)], values[len(educts) :]


def _nullspace_vector(matrix: list[list[Fraction]]) -> list[Fraction] | None:
    """Eindimensionaler Nullraum eines Gleichungssystems.

    Nur wenn die Lösung bis auf einen Faktor eindeutig ist, lässt sich daraus
    eine sinnvolle Reaktionsgleichung ableiten.
    """
    if not matrix or not matrix[0]:
        return None
    rows = [row[:] for row in matrix]
    columns = len(rows[0])
    pivot_columns: list[int] = []
    row = 0
    for column in range(columns):
        pivot = next(
            (index for index in range(row, len(rows)) if rows[index][column] != 0),
            None,
        )
        if pivot is None:
            continue
        rows[row], rows[pivot] = rows[pivot], rows[row]
        divisor = rows[row][column]
        rows[row] = [value / divisor for value in rows[row]]
        for index in range(len(rows)):
            if index == row:
                continue
            factor = rows[index][column]
            if factor != 0:
                rows[index] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(rows[index], rows[row], strict=True)
                ]
        pivot_columns.append(column)
        row += 1
        if row == len(rows):
            break

    free_columns = [column for column in range(columns) if column not in pivot_columns]
    if len(free_columns) != 1:
        return None
    free = free_columns[0]
    vector = [Fraction(0) for _ in range(columns)]
    vector[free] = Fraction(1)
    for pivot_row, column in enumerate(pivot_columns):
        vector[column] = -rows[pivot_row][free]
    if all(value <= 0 for value in vector):
        return [-value for value in vector]
    return vector
