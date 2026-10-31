"""Dialog zum Eintippen einer Atomladung."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..core.markup import markup_to_html
from ..core.molecule import MAX_ATOM_CHARGE, charge_text


class ChargeDialog(QDialog):
    """Kleiner Editor für die Formalladung eines Atoms.

    Die Spinbox deckt den gesamten Bereich ``-MAX_ATOM_CHARGE … +MAX_ATOM_CHARGE``
    ab; darunter zeigt eine Vorschau, wie das Atom mit Ladung aussieht.
    """

    def __init__(self, charge: int = 0, symbol: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ladung")
        self.setModal(True)
        self.setMinimumWidth(300)

        self._symbol = symbol.strip()

        self._spin = QSpinBox(self)
        self._spin.setRange(-MAX_ATOM_CHARGE, MAX_ATOM_CHARGE)
        self._spin.setValue(int(charge))
        self._spin.setToolTip(
            f"Formalladung von -{MAX_ATOM_CHARGE} bis +{MAX_ATOM_CHARGE}; "
            "0 bedeutet neutral."
        )
        self._spin.valueChanged.connect(self._update_preview)

        self._preview = QLabel(self)
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(40)
        self._preview.setStyleSheet(
            "background: white; color: #1a1a1a; border: 1px solid #bbb; padding: 6px;"
        )

        form = QFormLayout()
        form.addRow("Ladung:", self._spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        target = self._symbol or "das Atom"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Formalladung für {target}:", self))
        layout.addLayout(form)
        layout.addWidget(QLabel("Vorschau:", self))
        layout.addWidget(self._preview)
        layout.addWidget(buttons)

        self._update_preview(self.charge())
        self._spin.setFocus()
        self._spin.selectAll()

    # -- Werte -----------------------------------------------------------
    def charge(self) -> int:
        return int(self._spin.value())

    def set_charge(self, charge: int) -> None:
        self._spin.setValue(int(charge))

    def _update_preview(self, charge: int) -> None:
        markup = self._symbol
        if charge:
            markup = f"{markup}^{{{charge_text(charge)}}}"
        self._preview.setText(markup_to_html(markup) if markup else "&nbsp;")

    # -- Komfort ---------------------------------------------------------
    @classmethod
    def ask(cls, parent, charge: int = 0, symbol: str = "") -> int | None:
        """Zeigt den Dialog und liefert die Ladung (oder ``None`` bei Abbruch)."""
        dialog = cls(charge, symbol, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.charge()
        return None
