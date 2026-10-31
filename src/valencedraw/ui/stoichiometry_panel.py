"""Dock-Fenster der Ansatztabelle.

Die Tabelle zeigt die aus der Reaktionsgleichung erkannten Substanzen und
berechnet Äquivalente, Stoffmenge, Masse und Volumen. Änderungen in einer
Zelle werden sofort auf alle abhängigen Werte übertragen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.stoichiometry import (
    ROLE_LABELS,
    StoichiometryTable,
    format_value,
    latex_table,
)

#: Spaltenschlüssel, Überschrift, bearbeitbar, Nachkommastellen.
COLUMNS: tuple[tuple[str, str, bool, int], ...] = (
    ("name", "Substanz", False, 0),
    ("role", "Rolle", False, 0),
    ("eq", "eq", True, 4),
    ("M", "M / (g/mol)", True, 4),
    ("n", "n / mmol", True, 4),
    ("m", "m / g", True, 5),
    ("rho", "ρ / (g/mL)", True, 4),
    ("V", "V / mL", True, 4),
)


class StoichiometryPanel(QDockWidget):
    """Andockbares Fenster mit der interaktiven Ansatztabelle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Ansatztabelle", parent)
        self.setObjectName("stoichiometry_panel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self._table: StoichiometryTable | None = None
        self._updating = False

        container = QWidget(self)
        self._table_widget = QTableWidget(0, len(COLUMNS), container)
        self._table_widget.setHorizontalHeaderLabels(
            [heading for _key, heading, _editable, _decimals in COLUMNS]
        )
        self._table_widget.setAlternatingRowColors(True)
        self._table_widget.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self._table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self._table_widget.itemChanged.connect(self._on_item_changed)
        # Qt zeichnet Rasterlinien nur 1 px breit und hell. Für die
        # Ansatztabelle werden sie über Zellrahmen kräftig schwarz gesetzt.
        self._table_widget.setStyleSheet(
            """
            QTableWidget {
                gridline-color: #000000;
                border: 2px solid #000000;
            }
            QTableWidget::item {
                border-right: 2px solid #000000;
                border-bottom: 2px solid #000000;
                padding: 2px;
            }
            QHeaderView::section {
                border-right: 2px solid #000000;
                border-bottom: 2px solid #000000;
                padding: 4px;
                font-weight: bold;
                color: #000000;
            }
            QTableCornerButton::section {
                border-right: 2px solid #000000;
                border-bottom: 2px solid #000000;
            }
            """
        )

        header = self._table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        self._copy_button = QPushButton("LaTeX-Code kopieren", container)
        self._copy_button.setToolTip(
            "Kopiert die Ansatztabelle als LaTeX-tabular in die Zwischenablage"
        )
        self._copy_button.clicked.connect(self._copy_latex)

        self._hint = QLabel(
            "Zahlenwerte direkt anklicken und ändern – abhängige Werte werden "
            "neu berechnet. Reagenzien über dem Pfeil werden übernommen; "
            "Lösemittel unter dem Pfeil und −R-Gruppen nicht.",
            container,
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: palette(mid);")
        self._message = QLabel("", container)
        self._show_message("")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self._table_widget, 1)
        layout.addWidget(self._copy_button)
        layout.addWidget(self._message)
        layout.addWidget(self._hint)
        self.setWidget(container)
        self.setMinimumHeight(220)

    @property
    def table(self) -> StoichiometryTable | None:
        """Aktuell angezeigtes Rechenmodell."""
        return self._table

    @property
    def table_widget(self) -> QTableWidget:
        """Die eigentliche Tabelle (für Tests)."""
        return self._table_widget

    @property
    def copy_button(self) -> QPushButton:
        """Knopf für den LaTeX-Export (für Tests)."""
        return self._copy_button

    def set_table(self, table: StoichiometryTable) -> None:
        """Zeigt ein neues Rechenmodell an."""
        self._table = table
        self._show_message("")
        self._refresh()

    def _show_message(self, text: str, *, error: bool = False) -> None:
        """Status- oder Fehlermeldung unter der Tabelle anzeigen."""
        self._message.setText(text)
        self._message.setStyleSheet(
            "color: #a03030;" if error else "color: #207020;"
        )

    def _copy_latex(self) -> None:
        """Kopiert den LaTeX-Code der aktuellen Tabelle in die Zwischenablage."""
        table = self._table
        if table is None or not table.rows:
            self._show_message("Keine Tabelle zum Exportieren vorhanden.", error=True)
            return
        QApplication.clipboard().setText(latex_table(table))
        self._show_message("LaTeX-Code in die Zwischenablage kopiert.")

    # -- Aufbau und Aktualisierung ---------------------------------------
    def _refresh(self) -> None:
        table = self._table
        if table is None:
            return
        self._updating = True
        try:
            self._table_widget.setRowCount(len(table.rows))
            for row_index, row in enumerate(table.rows):
                values = {
                    "name": row.name,
                    "role": ROLE_LABELS[row.role],
                    "eq": format_value(row.equivalents, 4),
                    "M": format_value(row.molar_mass, 4),
                    "n": format_value(table.amount_mmol(row), 4),
                    "m": format_value(table.mass_g(row), 5),
                    "rho": format_value(row.density, 4),
                    "V": format_value(table.volume_ml(row), 4),
                }
                for column, (key, _heading, numeric, _decimals) in enumerate(COLUMNS):
                    item = self._table_widget.item(row_index, column)
                    if item is None:
                        item = QTableWidgetItem()
                        self._table_widget.setItem(row_index, column, item)
                    item.setText(values[key])
                    editable = key == "name" or numeric
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        if numeric
                        else Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                    flags = item.flags()
                    if editable:
                        item.setFlags(flags | Qt.ItemFlag.ItemIsEditable)
                    else:
                        item.setFlags(flags & ~Qt.ItemFlag.ItemIsEditable)
        finally:
            self._updating = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        table = self._table
        if self._updating or table is None:
            return
        column = item.column()
        if not 0 <= column < len(COLUMNS):
            return
        key, _heading, numeric, _decimals = COLUMNS[column]
        if key == "name":
            error = table.rename(item.row(), item.text())
            self._show_message(error or "", error=bool(error))
            self._refresh()
            return
        if not numeric:
            return
        try:
            value = self._parse_value(item.text())
        except ValueError:
            self._show_message(f"„{item.text()}“ ist keine Zahl.", error=True)
            self._refresh()
            return
        error = table.set_value(item.row(), key, value)
        self._show_message(error or "", error=bool(error))
        self._refresh()

    @staticmethod
    def _parse_value(text: str) -> float | None:
        """Zahl aus der Zelle lesen (Komma oder Punkt als Dezimaltrennzeichen)."""
        cleaned = text.strip().replace(",", ".")
        if not cleaned:
            return None
        return float(cleaned)
