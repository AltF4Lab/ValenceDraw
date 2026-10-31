"""Undo/Redo-Bausteine.

Für den MVP nutzen wir Snapshot-basiertes Undo: jede Änderung speichert eine
Kopie des Dokumentzustands (Molekül, Texte, Pfeile) vor und nach der Aktion.
Bei den hier erwarteten Strukturgrößen ist das schnell, und es ist unmöglich,
einen inkonsistenten Zustand wiederherzustellen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from .state import DocumentState

if TYPE_CHECKING:  # pragma: no cover
    from .document import Document


class SnapshotCommand(QUndoCommand):
    """Setzt beim Undo/Redo einen kompletten Dokumentzustand zurück."""

    def __init__(
        self,
        document: "Document",
        text: str,
        before: DocumentState,
        after: DocumentState,
    ) -> None:
        super().__init__(text)
        self._document = document
        self._before = before
        self._after = after

    def undo(self) -> None:  # noqa: D102
        self._document.restore_snapshot(self._before)

    def redo(self) -> None:  # noqa: D102
        self._document.restore_snapshot(self._after)
