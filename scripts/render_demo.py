"""Rendert die Demo-Strukturen nach ``out/`` – nützlich als schneller Sichtcheck."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from valencedraw.demo import benzene, ethane, ethanol  # noqa: E402
from valencedraw.render.export import save_png, save_svg  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)

    for name, molecule in (
        ("ethane", ethane()),
        ("benzene", benzene()),
        ("ethanol", ethanol()),
    ):
        save_png(molecule, out_dir / f"{name}.png", width=600, height=400)
        save_svg(molecule, out_dir / f"{name}.svg", width=600, height=400)
        print(f"{name}: {len(molecule)} Atome, {len(molecule.bonds)} Bindungen")

    del app
    print(f"Exporte liegen in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
