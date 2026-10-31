"""Anwendungsstart."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    """Erzeugt (oder liefert) die ``QApplication``-Instanz."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    app = QApplication(list(sys.argv) if argv is None else list(argv))
    app.setApplicationName("ValenceDraw")
    app.setApplicationDisplayName("ValenceDraw")
    app.setOrganizationName("ValenceDraw")
    return app


def main(argv: list[str] | None = None) -> int:
    """Startet die Anwendung und liefert den Exit-Code."""
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
