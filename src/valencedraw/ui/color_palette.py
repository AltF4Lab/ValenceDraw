"""Farbpalette für die Werkzeugleiste.

Die Palette färbt **die aktuelle Auswahl** nachträglich ein: Erst zeichnen
(standardmäßig schwarz), dann Objekte auswählen und auf einen Farbknopf
klicken. Der Knopf „Standard“ entfernt eine gesetzte Farbe wieder.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from ..core.colors import PALETTE, RGB

SWATCH_SIZE = 18
BUTTON_SIZE = 26


def swatch_icon(color: RGB | None, size: int = SWATCH_SIZE) -> QIcon:
    """Quadratisches Farbfeld als Icon; ``None`` zeichnet den Standardknopf."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(110, 110, 110), 1.0))
        painter.setBrush(QColor(255, 255, 255) if color is None else QColor(*color))
        painter.drawRoundedRect(0.5, 0.5, size - 1.0, size - 1.0, 3.0, 3.0)
        if color is None:
            # Standard = automatisch schwarz: roter Schrägstrich als „keine Farbe“.
            painter.setPen(QPen(QColor(200, 60, 60), 1.6))
            painter.drawLine(3, size - 3, size - 3, 3)
    finally:
        painter.end()
    return QIcon(pixmap)


class ColorPalette(QWidget):
    """Reihe von Farbknöpfen; sendet die gewählte Farbe (``None`` = Standard)."""

    color_selected = Signal(object)
    """Gewählte Farbe als ``(r, g, b)`` oder ``None``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QToolButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self._add_button(layout, "Standard", None, "Standardfarbe (schwarz)")
        for name, color in PALETTE:
            self._add_button(layout, name, color, name)

    @property
    def buttons(self) -> dict[str, QToolButton]:
        """Knöpfe nach Name (für Tests und Tastaturbedienung)."""
        return dict(self._buttons)

    def _add_button(
        self,
        layout: QHBoxLayout,
        key: str,
        color: RGB | None,
        tooltip: str,
    ) -> None:
        button = QToolButton(self)
        button.setAutoRaise(True)
        button.setIcon(swatch_icon(color))
        button.setIconSize(QSize(SWATCH_SIZE, SWATCH_SIZE))
        button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        button.setToolTip(
            f"{tooltip} – färbt die ausgewählten Objekte"
            if color is not None
            else f"{tooltip} – entfernt die gesetzte Farbe"
        )
        button.clicked.connect(lambda _checked=False, value=color: self.color_selected.emit(value))
        layout.addWidget(button)
        self._buttons[key] = button
