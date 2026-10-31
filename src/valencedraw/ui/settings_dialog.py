"""Einstellungsdialog mit Tab-Reitern.

Aktuell gibt es einen Reiter „Bindungen“ mit Bindungslänge und Bindungsdicke.
Weitere Reiter (z. B. Farben, Schrift) lassen sich hier ergänzen.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.molecule import Molecule
from ..core.page import MM_PER_SCENE_UNIT, SCENE_UNITS_PER_MM
from ..core.templates import BENZENE, build_ring
from ..render.painter import paint_molecule
from ..render.style import DEFAULT_STYLE, Style

MIN_BOND_LENGTH_MM = 1.0
MAX_BOND_LENGTH_MM = 20.0
MIN_BOND_WIDTH_MM = 0.05
MAX_BOND_WIDTH_MM = 2.0

PAGE_MARGIN = 12.0
MAX_PREVIEW_SCALE = 2.0


class StylePreview(QWidget):
    """Kleine Vorschau eines Benzolrings im aktuellen Stil."""

    def __init__(self, style: Style = DEFAULT_STYLE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._style = style
        self.setMinimumSize(240, 170)

    @property
    def style(self) -> Style:
        return self._style

    def set_style(self, style: Style) -> None:
        if style == self._style:
            return
        self._style = style
        self.update()

    def preview_molecule(self) -> Molecule:
        """Benzolring mit der konfigurierten Bindungslänge (für die Vorschau)."""
        return build_ring(BENZENE, bond_length=self._style.bond_length)

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        extent = 2.0 * self._style.bond_length
        available = min(self.width(), self.height()) - 2 * PAGE_MARGIN
        if extent <= 0.0 or available <= 0.0:
            return
        scale = min(MAX_PREVIEW_SCALE, available / extent)

        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.scale(scale, scale)
        paint_molecule(painter, self.preview_molecule(), self._style)


class SettingsDialog(QDialog):
    """Dialog mit Einstellungen; liefert über :meth:`ask` den neuen Stil."""

    def __init__(self, style: Style = DEFAULT_STYLE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self._base_style = style

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._create_bond_tab(), "Bindungen")

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Übernehmen")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(self._buttons)
        self.resize(460, 400)

    # -- Aufbau ----------------------------------------------------------
    def _create_bond_tab(self) -> QWidget:
        tab = QWidget(self)

        self.length_spin = QDoubleSpinBox(tab)
        self.length_spin.setDecimals(1)
        self.length_spin.setSingleStep(0.1)
        self.length_spin.setRange(MIN_BOND_LENGTH_MM, MAX_BOND_LENGTH_MM)
        self.length_spin.setSuffix(" mm")
        self.length_spin.setValue(self._base_style.bond_length * MM_PER_SCENE_UNIT)
        self.length_spin.setToolTip(
            "Länge neuer Bindungen; gilt auch für neu platzierte Ringe"
        )

        self.width_spin = QDoubleSpinBox(tab)
        self.width_spin.setDecimals(2)
        self.width_spin.setSingleStep(0.05)
        self.width_spin.setRange(MIN_BOND_WIDTH_MM, MAX_BOND_WIDTH_MM)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(self._base_style.bond_width * MM_PER_SCENE_UNIT)
        self.width_spin.setToolTip("Strichdicke aller Bindungen und Pfeile")

        hint = QLabel(
            "Die Bindungslänge gilt für neu gezeichnete Bindungen und Ringe, "
            "die Bindungsdicke wirkt sofort auf die gesamte Zeichnung.",
            tab,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")

        self._preview = StylePreview(self._base_style, tab)

        form = QFormLayout()
        form.addRow("Bindungslänge:", self.length_spin)
        form.addRow("Bindungsdicke:", self.width_spin)

        self.length_spin.valueChanged.connect(self._on_values_changed)
        self.width_spin.valueChanged.connect(self._on_values_changed)

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self._preview, 1)
        return tab

    # -- Werte -----------------------------------------------------------
    @property
    def style(self) -> Style:
        """Der Stil mit den aktuell eingestellten Werten."""
        return replace(
            self._base_style,
            bond_length=self.length_spin.value() * SCENE_UNITS_PER_MM,
            bond_width=self.width_spin.value() * SCENE_UNITS_PER_MM,
        )

    def _on_values_changed(self, _value: float) -> None:
        self._preview.set_style(self.style)

    @staticmethod
    def ask(parent: QWidget | None, style: Style = DEFAULT_STYLE) -> Style | None:
        """Zeigt den Dialog modal; liefert den neuen Stil oder ``None``."""
        dialog = SettingsDialog(style, parent)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.style
        finally:
            dialog.deleteLater()


__all__ = [
    "MAX_BOND_LENGTH_MM",
    "MAX_BOND_WIDTH_MM",
    "MIN_BOND_LENGTH_MM",
    "MIN_BOND_WIDTH_MM",
    "SettingsDialog",
    "StylePreview",
]
