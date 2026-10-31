"""Einstiegspunkt für den PyInstaller-Build.

Das Paket benutzt relative Importe, deshalb kann ``valencedraw/app.py`` nicht
direkt als PyInstaller-Skript dienen. Dieses Modul importiert stattdessen die
öffentliche ``main()``-Funktion.
"""

from __future__ import annotations

import multiprocessing
import sys

from valencedraw.app import main

if __name__ == "__main__":
    # Nötig, falls eine Abhängigkeit (RDKit/NumPy) Prozesse startet.
    multiprocessing.freeze_support()
    sys.exit(main())
