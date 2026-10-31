"""Zwischenablage: Ausschnitte des Dokuments kopieren und einfügen.

Ein :class:`Fragment` enthält die kopierten Atome (mit den Bindungen zwischen
ihnen), Texte und Pfeile. Für die Systemzwischenablage wird derselbe
JSON-Aufbau wie in der Projektdatei verwendet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..core.annotations import ArrowObject, TextObject
from ..core.geometry import Point2D
from ..core.molecule import Molecule
from .project import Project, ProjectError, project_from_data, project_to_data
CLIPBOARD_MIME = "application/x-valencedraw-fragment"
"""MIME-Typ der ValenceDraw-Zwischenablage."""


@dataclass(frozen=True)
class Fragment:
    """Kopierter Dokumentausschnitt."""

    molecule: Molecule = field(default_factory=Molecule)
    texts: tuple[TextObject, ...] = ()
    arrows: tuple[ArrowObject, ...] = ()

    def is_empty(self) -> bool:
        return self.molecule.is_empty() and not self.texts and not self.arrows

    def translated(self, delta: Point2D) -> "Fragment":
        """Kopie, deren Objekte um ``delta`` verschoben sind."""
        molecule = self.molecule.clone()
        molecule.translate(molecule.atom_ids(), delta)
        return Fragment(
            molecule=molecule,
            texts=tuple(obj.moved_to(obj.position + delta) for obj in self.texts),
            arrows=tuple(arrow.translated(delta) for arrow in self.arrows),
        )


def fragment_to_json(fragment: Fragment) -> str:
    """Serialisiert ein Fragment als JSON (Schema der Projektdatei)."""
    project = Project(fragment.molecule, fragment.texts, fragment.arrows)
    return json.dumps(project_to_data(project), ensure_ascii=False)


def fragment_from_json(text: str) -> Fragment:
    """Liest ein Fragment aus JSON; wirft ``ProjectError`` bei ungültigen Daten."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(f"Zwischenablage ist kein gültiges JSON: {exc}") from exc
    project = project_from_data(data)
    return Fragment(project.molecule, project.texts, project.arrows)


__all__ = [
    "CLIPBOARD_MIME",
    "Fragment",
    "fragment_from_json",
    "fragment_to_json",
]
