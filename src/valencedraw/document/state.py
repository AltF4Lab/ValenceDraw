"""Momentaufnahme eines Dokuments für Undo/Redo."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.annotations import ArrowObject, TextObject
from ..core.molecule import Molecule


@dataclass(frozen=True)
class DocumentState:
    """Molekül plus freie Objekte (Texte, Pfeile)."""

    molecule: Molecule = field(default_factory=Molecule)
    texts: tuple[TextObject, ...] = ()
    arrows: tuple[ArrowObject, ...] = ()
