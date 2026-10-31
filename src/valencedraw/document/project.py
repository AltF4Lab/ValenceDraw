"""Projektdatei (``.valencedraw``): Molekül, Texte, Pfeile und Seite.

Die Chemie-Formate (MOL/SDF/SMILES) kennen nur Atome und Bindungen. Für ein
vollständiges Dokument – inklusive Beschriftungen, Reaktionspfeilen,
Atomlabels und Seitenformat – gibt es deshalb dieses JSON-Format.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.annotations import ArrowKind, ArrowObject, TextObject
from ..core.colors import RGB
from ..core.geometry import Point2D
from ..core.molecule import MAX_BOND_ORDER, BondStereo, Molecule
from ..core.page import Orientation, Page, PageFormat

PROJECT_SUFFIX = ".valencedraw"
"""Dateiendung der ValenceDraw-Projektdatei."""

FORMAT_NAME = "valencedraw"
FORMAT_VERSION = 1


class ProjectError(ValueError):
    """Die Projektdatei ist unlesbar oder beschädigt."""


@dataclass(frozen=True)
class Project:
    """Kompletter Dokumentinhalt einer Projektdatei."""

    molecule: Molecule = field(default_factory=Molecule)
    texts: tuple[TextObject, ...] = ()
    arrows: tuple[ArrowObject, ...] = ()
    page: Page = field(default_factory=Page)


# -- Abbildung Modell -> JSON -------------------------------------------
def _color_to_data(color: RGB | None) -> list[int] | None:
    """Farbe als ``[r, g, b]`` (``None`` = Standardfarbe)."""
    return None if color is None else [color[0], color[1], color[2]]


def _arrow_to_data(arrow: ArrowObject) -> dict[str, Any]:
    """JSON-Eintrag eines Pfeils (Scheiteltangente nur wenn nötig)."""
    entry: dict[str, Any] = {
        "x1": arrow.start.x,
        "y1": arrow.start.y,
        "x2": arrow.end.x,
        "y2": arrow.end.y,
        "kind": arrow.kind.value,
        "bow": arrow.bow,
        "bow_along": arrow.bow_along,
    }
    if arrow.apex_tangent is not None:
        entry["apex_tangent"] = [arrow.apex_tangent.x, arrow.apex_tangent.y]
    if arrow.color is not None:
        entry["color"] = _color_to_data(arrow.color)
    return entry


def project_to_data(project: Project) -> dict[str, Any]:
    """Wandelt ein Projekt in ein JSON-fähiges Dict um."""
    molecule = project.molecule
    atoms: list[dict[str, Any]] = []
    for atom_id in molecule.atom_ids():
        atom = molecule.atom(atom_id)
        entry: dict[str, Any] = {
            "id": atom_id,
            "element": atom.element,
            "x": atom.position.x,
            "y": atom.position.y,
            "charge": atom.charge,
            "label": atom.label,
            "pairs": [[vector.x, vector.y] for vector in atom.lone_pairs],
            "radicals": [[vector.x, vector.y] for vector in atom.radicals],
            "charge_at": (
                [atom.charge_direction.x, atom.charge_direction.y]
                if atom.charge_direction is not None
                else None
            ),
            "partial": atom.partial_charge,
            "partial_at": (
                [
                    atom.partial_charge_direction.x,
                    atom.partial_charge_direction.y,
                ]
                if atom.partial_charge_direction is not None
                else None
            ),
        }
        if atom.color is not None:
            entry["color"] = _color_to_data(atom.color)
        atoms.append(entry)
    bonds = []
    for bond in molecule.bonds:
        bond_entry: dict[str, Any] = {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "side": bond.side,
            "centered": bond.centered,
            "stereo": bond.stereo.value,
            "stereo_from": bond.stereo_from,
        }
        if bond.color is not None:
            bond_entry["color"] = _color_to_data(bond.color)
        bonds.append(bond_entry)

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "page": {
            "format": project.page.format.name,
            "orientation": project.page.orientation.name,
        },
        "molecule": {"atoms": atoms, "bonds": bonds},
        "texts": [
            {
                "x": obj.position.x,
                "y": obj.position.y,
                "markup": obj.markup,
                **(
                    {"color": _color_to_data(obj.color)}
                    if obj.color is not None
                    else {}
                ),
            }
            for obj in project.texts
        ],
        "arrows": [_arrow_to_data(arrow) for arrow in project.arrows],
    }


# -- Abbildung JSON -> Modell -------------------------------------------
def _vector_from_data(entry: Any) -> Point2D | None:
    """Liest einen Richtungsvektor ``[x, y]`` (``None`` bei fehlendem Eintrag)."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        return None
    vector = Point2D(float(entry[0]), float(entry[1]))
    return vector if vector.length > 1e-9 else None


def _vectors_from_data(entries: Any) -> tuple[Point2D, ...]:
    """Liest Richtungsvektoren aus ``[[x, y], …]``-Einträgen."""
    if not isinstance(entries, list):
        return ()
    return tuple(
        Point2D(float(entry[0]), float(entry[1]))
        for entry in entries
        if isinstance(entry, (list, tuple)) and len(entry) >= 2
    )


def _color_from_data(entry: Any) -> RGB | None:
    """Liest eine optionale RGB-Farbe (ungültige Werte = Standardfarbe)."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 3:
        return None
    try:
        values = tuple(int(value) for value in entry[:3])
    except (TypeError, ValueError):
        return None
    if any(value < 0 or value > 255 for value in values):
        return None
    return values  # type: ignore[return-value]


def _stereo_from_data(entry: Any) -> BondStereo:
    """Liest die Keilstrich-Darstellung (unbekannte Werte werden zur Linie)."""
    try:
        return BondStereo(str(entry))
    except ValueError:
        return BondStereo.NONE


def _int_or_none(entry: Any) -> int | None:
    """Liest eine optionale Atom-ID."""
    if entry is None:
        return None
    try:
        return int(entry)
    except (TypeError, ValueError):
        return None


def _molecule_from_data(data: dict[str, Any]) -> Molecule:
    molecule = Molecule()
    ids: dict[int, int] = {}
    try:
        for entry in data.get("atoms", []):
            atom_id = molecule.add_atom(
                str(entry.get("element", "C")),
                Point2D(float(entry["x"]), float(entry["y"])),
                int(entry.get("charge", 0)),
                _color_from_data(entry.get("color")),
            )
            ids[int(entry["id"])] = atom_id
            label = str(entry.get("label", "")).strip()
            if label:
                molecule.set_label(atom_id, label)
            molecule.set_electrons(
                atom_id,
                _vectors_from_data(entry.get("pairs", [])),
                _vectors_from_data(entry.get("radicals", [])),
            )
            charge_at = _vector_from_data(entry.get("charge_at"))
            if charge_at is not None:
                molecule.set_charge_direction(atom_id, charge_at)
            molecule.set_partial_charge(atom_id, int(entry.get("partial", 0)))
            partial_at = _vector_from_data(entry.get("partial_at"))
            if partial_at is not None:
                molecule.set_partial_charge_direction(atom_id, partial_at)

        for entry in data.get("bonds", []):
            a = ids[int(entry["a"])]
            b = ids[int(entry["b"])]
            order = max(1, min(int(entry.get("order", 1)), MAX_BOND_ORDER))
            side = max(-1, min(1, int(entry.get("side") or 0)))
            molecule.add_bond(
                a,
                b,
                order,
                side,
                bool(entry.get("centered", False)),
                _stereo_from_data(entry.get("stereo")),
                _int_or_none(entry.get("stereo_from")),
                _color_from_data(entry.get("color")),
            )
    except KeyError as exc:
        raise ProjectError(f"Unbekanntes Atom in der Projektdatei: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise ProjectError(f"Ungültige Moleküldaten: {exc}") from exc
    return molecule


def _page_from_data(data: dict[str, Any]) -> Page:
    try:
        page_format = PageFormat[str(data.get("format", PageFormat.A4.name))]
        orientation = Orientation[str(data.get("orientation", Orientation.PORTRAIT.name))]
    except KeyError as exc:
        raise ProjectError(f"Unbekanntes Seitenformat: {exc}") from exc
    return Page(page_format, orientation)


def project_from_data(data: Any) -> Project:
    """Baut ein Projekt aus geparsten JSON-Daten."""
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise ProjectError("Das ist keine ValenceDraw-Projektdatei.")

    try:
        version = int(data.get("version", FORMAT_VERSION))
    except (TypeError, ValueError) as exc:
        raise ProjectError(f"Ungültige Projektversion: {data.get('version')}") from exc
    if version > FORMAT_VERSION:
        raise ProjectError(
            f"Die Projektdatei wurde mit einer neueren Version erstellt (v{version})."
        )

    molecule_data = data.get("molecule") or {}
    if not isinstance(molecule_data, dict):
        raise ProjectError("Ungültige Moleküldaten.")

    try:
        texts = tuple(
            TextObject(
                Point2D(float(entry["x"]), float(entry["y"])),
                str(entry.get("markup", "")),
                _color_from_data(entry.get("color")),
            )
            for entry in data.get("texts", [])
        )
        arrows = tuple(
            ArrowObject(
                Point2D(float(entry["x1"]), float(entry["y1"])),
                Point2D(float(entry["x2"]), float(entry["y2"])),
                ArrowKind(str(entry.get("kind", ArrowKind.FORWARD.value))),
                float(entry.get("bow", 0.0)),
                float(entry.get("bow_along", 0.0)),
                _vector_from_data(entry.get("apex_tangent")),
                _color_from_data(entry.get("color")),
            )
            for entry in data.get("arrows", [])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectError(f"Ungültige Objektdaten: {exc}") from exc

    return Project(
        molecule=_molecule_from_data(molecule_data),
        texts=texts,
        arrows=arrows,
        page=_page_from_data(data.get("page") or {}),
    )


# -- Dateien -------------------------------------------------------------
def project_to_json(project: Project) -> str:
    """Serialisiert ein Projekt als JSON-Text."""
    return json.dumps(project_to_data(project), indent=2, ensure_ascii=False) + "\n"


def project_from_json(text: str) -> Project:
    """Liest ein Projekt aus JSON-Text."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(f"Projektdatei ist kein gültiges JSON: {exc}") from exc
    return project_from_data(data)


def save_project(project: Project, path: str | Path) -> Path:
    """Schreibt ein Projekt als ``.valencedraw``-Datei."""
    file_path = Path(path)
    file_path.write_text(project_to_json(project), encoding="utf-8")
    return file_path


def load_project(path: str | Path) -> Project:
    """Liest eine ``.valencedraw``-Datei."""
    file_path = Path(path)
    return project_from_json(file_path.read_text(encoding="utf-8"))


__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "PROJECT_SUFFIX",
    "Project",
    "ProjectError",
    "load_project",
    "project_from_data",
    "project_from_json",
    "project_to_data",
    "project_to_json",
    "save_project",
]
