"""Dialog zum Erfassen von Beschriftungen inklusive Hoch-/Tiefstellung."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.latex import MATH_DELIMITER
from ..core.markup import BOLD_MARKER, ITALIC_MARKER, markup_to_html


class TextDialog(QDialog):
    """Kleiner Editor mit Live-Vorschau für Markup-Text."""

    def __init__(self, markup: str = "", parent=None, title: str = "Text") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)

        self._edit = QLineEdit(markup, self)
        self._edit.setPlaceholderText(
            "z. B. NO2, OH, Fe^{3+} oder $\\Delta G^\\circ = -RT \\ln K$"
        )
        self._edit.textChanged.connect(self._update_preview)
        self._edit.returnPressed.connect(self.accept)

        self._preview = QLabel(self)
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setMinimumHeight(44)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            "background: white; color: #1a1a1a; border: 1px solid #bbb; padding: 6px;"
        )

        subscript_button = QPushButton("Tiefgestellt _{…}", self)
        subscript_button.clicked.connect(lambda: self.wrap_selection("_"))
        superscript_button = QPushButton("Hochgestellt ^{…}", self)
        superscript_button.clicked.connect(lambda: self.wrap_selection("^"))

        bold_button = QPushButton("Fett **…**", self)
        bold_button.setToolTip("Auswahl fett setzen (nochmal klicken hebt es auf)")
        bold_button.clicked.connect(lambda: self.toggle_style(BOLD_MARKER))
        italic_button = QPushButton("Kursiv *…*", self)
        italic_button.setToolTip("Auswahl kursiv setzen (nochmal klicken hebt es auf)")
        italic_button.clicked.connect(lambda: self.toggle_style(ITALIC_MARKER))
        math_button = QPushButton("Mathe $…$", self)
        math_button.setToolTip(
            "Auswahl als LaTeX-Formel setzen, z. B. $\\Delta G^\\circ$, "
            "$\\frac{a}{b}$, $\\sqrt{x}$ (nochmal klicken hebt es auf)"
        )
        math_button.clicked.connect(self.toggle_math)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        markers = QGridLayout()
        markers.addWidget(subscript_button, 0, 0)
        markers.addWidget(superscript_button, 0, 1)
        markers.addWidget(math_button, 0, 2)
        markers.addWidget(bold_button, 1, 0)
        markers.addWidget(italic_button, 1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Text (Auswahl formatieren):", self))
        layout.addWidget(self._edit)
        layout.addLayout(markers)
        layout.addWidget(
            QLabel(
                "Automatisch: Ziffern nach Buchstaben tiefgestellt (NO2 → NO₂), \n"
                "abschließende Ladung hochgestellt (NO3- → NO₃⁻).\n"
                "Fett: **…**, kursiv: *…*, LaTeX: $…$ (z. B. $\\Delta G^\\circ$).",
                self,
            )
        )
        layout.addWidget(QLabel("Vorschau:", self))
        layout.addWidget(self._preview)
        layout.addWidget(buttons)

        self._update_preview(markup)
        self._edit.setFocus()

    # -- Markup ----------------------------------------------------------
    def markup(self) -> str:
        return self._edit.text().strip()

    def set_markup(self, markup: str) -> None:
        self._edit.setText(markup)

    def wrap_selection(self, marker: str) -> None:
        """Setzt ``_{…}`` bzw. ``^{…}`` um die aktuelle Auswahl."""
        text, start, end = self._selection()
        selected = text[start:end]
        self._edit.setText(f"{text[:start]}{marker}{{{selected}}}{text[end:]}")
        self._edit.setCursorPosition(start + 2 + len(selected))
        self._edit.setFocus()

    def toggle_style(self, marker: str) -> None:
        """Setzt ``**…**`` (fett) bzw. ``*…*`` (kursiv) um die Auswahl.

        Ist die Auswahl bereits mit demselben Marker umschlossen, wird die
        Auszeichnung wieder entfernt.
        """
        text, start, end = self._selection()
        selected = text[start:end]
        size = len(marker)
        wrapped = (
            start >= size
            and text[start - size : start] == marker
            and text[end : end + size] == marker
        )
        if wrapped:
            self._edit.setText(text[: start - size] + selected + text[end + size :])
            self._edit.setSelection(start - size, len(selected))
        else:
            self._edit.setText(f"{text[:start]}{marker}{selected}{marker}{text[end:]}")
            self._edit.setSelection(start + size, len(selected))
        self._edit.setFocus()

    def toggle_math(self) -> None:
        """Setzt ``$…$`` um die Auswahl und macht sie damit zur LaTeX-Formel.

        Ist die Auswahl bereits als Formel markiert, wird ``$…$`` wieder
        entfernt.
        """
        text, start, end = self._selection()
        selected = text[start:end]
        wrapped = (
            start >= 1
            and text[start - 1] == MATH_DELIMITER
            and text[end : end + 1] == MATH_DELIMITER
        )
        if wrapped:
            self._edit.setText(text[: start - 1] + selected + text[end + 1 :])
            self._edit.setSelection(start - 1, len(selected))
        else:
            self._edit.setText(
                f"{text[:start]}{MATH_DELIMITER}{selected}{MATH_DELIMITER}{text[end:]}"
            )
            self._edit.setSelection(start + 1, len(selected))
        self._edit.setFocus()

    def _selection(self) -> tuple[str, int, int]:
        """Aktueller Text sowie Anfang und Ende der Auswahl."""
        text = self._edit.text()
        start = self._edit.selectionStart()
        if start < 0:
            start = self._edit.cursorPosition()
        return text, start, start + len(self._edit.selectedText())

    def _update_preview(self, markup: str) -> None:
        self._preview.setText(markup_to_html(markup) if markup else "&nbsp;")

    # -- Komfort ---------------------------------------------------------
    @classmethod
    def ask(cls, parent, markup: str = "", title: str = "Text") -> str | None:
        """Zeigt den Dialog und liefert das Ergebnis (oder ``None``)."""
        dialog = cls(markup, parent, title)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.markup()
            return result or None
        return None
