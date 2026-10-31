"""Erzeugt einen Screenshot des Hauptfensters – nützlich als visuelle Kontrolle.

Aufruf (Windows/macOS/Linux mit Desktop):

    .\\.venv\\Scripts\\python.exe scripts\\window_screenshot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from valencedraw.app import create_application  # noqa: E402
from valencedraw.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = create_application([])
    window = MainWindow()
    window.resize(1100, 780)
    window.show()
    app.processEvents()

    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / "window.png"
    window.grab().save(str(target))
    print(f"Screenshot: {target}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
