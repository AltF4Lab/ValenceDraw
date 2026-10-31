"""Seitenformat und Ausrichtung der Zeichenfläche.

Die Zeichenfläche ist wie in ChemDraw ein Blatt Papier (A4, Letter, …), das auf
einer grauen Arbeitsfläche liegt. Alle Maße sind Qt-frei und in Szeneneinheiten;
dabei gilt:

    1 Szeneneinheit = 0,1 mm   →   1 Bindungslänge (40) = 4 mm

Das Blatt ist um den Ursprung zentriert, damit Demo-Strukturen und neue
Moleküle direkt in der Blattmitte landen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry import Point2D

SCENE_UNITS_PER_MM = 10.0
"""Szeneneinheiten pro Millimeter (1 Einheit = 0,1 mm)."""

MM_PER_SCENE_UNIT = 1.0 / SCENE_UNITS_PER_MM


class PageFormat(Enum):
    """Unterstützte Papierformate mit ihren Maßen in Millimetern."""

    A4 = ("A4", 210.0, 297.0)
    A3 = ("A3", 297.0, 420.0)
    A5 = ("A5", 148.0, 210.0)
    LETTER = ("Letter", 215.9, 279.4)
    LEGAL = ("Legal", 215.9, 355.6)

    def __init__(self, label: str, width_mm: float, height_mm: float) -> None:
        self.label = label
        self.width_mm = width_mm
        self.height_mm = height_mm

    def __str__(self) -> str:  # pragma: no cover - nur für Diagnose/UI
        return self.label


class Orientation(Enum):
    """Blattausrichtung."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"

    @property
    def label(self) -> str:
        return "Hochformat" if self is Orientation.PORTRAIT else "Querformat"


@dataclass(frozen=True)
class Page:
    """Ein Blatt Papier: Format plus Ausrichtung."""

    format: PageFormat = PageFormat.A4
    orientation: Orientation = Orientation.PORTRAIT

    @property
    def width_mm(self) -> float:
        """Breite in Millimetern (abhängig von der Ausrichtung)."""
        short, long = self.format.width_mm, self.format.height_mm
        return short if self.orientation is Orientation.PORTRAIT else long

    @property
    def height_mm(self) -> float:
        """Höhe in Millimetern (abhängig von der Ausrichtung)."""
        short, long = self.format.width_mm, self.format.height_mm
        return long if self.orientation is Orientation.PORTRAIT else short

    @property
    def width(self) -> float:
        """Breite in Szeneneinheiten."""
        return self.width_mm * SCENE_UNITS_PER_MM

    @property
    def height(self) -> float:
        """Höhe in Szeneneinheiten."""
        return self.height_mm * SCENE_UNITS_PER_MM

    @property
    def bounds(self) -> tuple[Point2D, Point2D]:
        """Linke obere und rechte untere Ecke (Blatt mittig um den Ursprung)."""
        half_width = self.width / 2.0
        half_height = self.height / 2.0
        return Point2D(-half_width, -half_height), Point2D(half_width, half_height)

    def with_format(self, page_format: PageFormat) -> "Page":
        return Page(page_format, self.orientation)

    def with_orientation(self, orientation: Orientation) -> "Page":
        return Page(self.format, orientation)

    def toggled(self) -> "Page":
        """Dreht das Blatt um 90° (Hoch- ↔ Querformat)."""
        other = (
            Orientation.LANDSCAPE
            if self.orientation is Orientation.PORTRAIT
            else Orientation.PORTRAIT
        )
        return Page(self.format, other)
