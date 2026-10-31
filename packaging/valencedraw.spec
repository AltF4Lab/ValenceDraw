# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation für ValenceDraw (Windows, Linux, macOS).

Aufruf aus dem Projektwurzelverzeichnis::

    pyinstaller --noconfirm --clean packaging/valencedraw.spec

Ergebnis:

* Windows/Linux – ``dist/ValenceDraw/`` (Ordner mit ``ValenceDraw.exe`` bzw.
  ``ValenceDraw``)
* macOS – zusätzlich ``dist/ValenceDraw.app`` (App-Bundle)

Die Version für das macOS-Bundle wird aus ``VALENCEDRAW_VERSION`` gelesen
(fällt auf ``0.0.0`` zurück).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH ist das Verzeichnis dieser Datei (``packaging/``).
ROOT = Path(SPECPATH).resolve().parent
VERSION = os.environ.get("VALENCEDRAW_VERSION", "0.0.0")

# --- Abhängigkeiten einsammeln ------------------------------------------------
# RDKit lädt sehr viele Untermodule dynamisch nach; collect_all ist hier der
# zuverlässigste Weg (Daten, Shared Libraries und Hidden Imports in einem).
datas: list = []
binaries: list = []
hiddenimports: list[str] = []

for package in ("rdkit",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("valencedraw")
# Wird erst in ``render/export.py`` innerhalb einer Funktion importiert.
hiddenimports += ["PySide6.QtSvg"]

# --- Unbenutzte Qt-Module ausschließen (spart mehrere hundert MB) -------------
excludes = [
    "tkinter",
    # Qt-Module, die ValenceDraw nicht verwendet
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
]

a = Analysis(  # noqa: F821 - von PyInstaller injiziert
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ValenceDraw",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ValenceDraw",
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="ValenceDraw.app",
        bundle_identifier="io.github.altf4lab.valencedraw",
        info_plist={
            "CFBundleName": "ValenceDraw",
            "CFBundleDisplayName": "ValenceDraw",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "NSRequiresAquaSystemAppearance": False,
        },
    )
