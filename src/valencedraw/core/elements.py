"""Elementdaten (Farbe, Kovalenzradius, typische Valenzen).

Die Werte sind bewusst klein gehalten: nur Elemente, die im MVP sinnvoll
gezeichnet werden können. Unbekannte Symbole sind erlaubt – sie werden schwarz
und mit einem Standardradius dargestellt.
"""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]

DEFAULT_ELEMENT: str = "C"

# Reihenfolge für die Element-Auswahl in der Oberfläche.
ELEMENT_ORDER: tuple[str, ...] = (
    "C",
    "H",
    "N",
    "O",
    "S",
    "P",
    "F",
    "Cl",
    "Br",
    "I",
    "B",
    "Si",
)


@dataclass(frozen=True)
class Element:
    symbol: str
    name: str
    atomic_number: int
    covalent_radius: float
    color: RGB
    valences: tuple[int, ...] = (0,)


ELEMENTS: dict[str, Element] = {
    element.symbol: element
    for element in (
        Element("H", "Wasserstoff", 1, 0.31, (60, 60, 60), (1,)),
        Element("B", "Bor", 5, 0.84, (255, 113, 113), (3,)),
        Element("C", "Kohlenstoff", 6, 0.76, (25, 25, 25), (4,)),
        Element("N", "Stickstoff", 7, 0.71, (0, 0, 255), (3,)),
        Element("O", "Sauerstoff", 8, 0.66, (255, 0, 0), (2,)),
        Element("F", "Fluor", 9, 0.57, (144, 200, 80), (1,)),
        Element("Si", "Silicium", 14, 1.11, (200, 160, 90), (4,)),
        Element("P", "Phosphor", 15, 1.07, (255, 128, 0), (3, 5)),
        Element("S", "Schwefel", 16, 1.05, (200, 160, 20), (2, 4, 6)),
        Element("Cl", "Chlor", 17, 1.02, (31, 190, 31), (1,)),
        Element("Br", "Brom", 35, 1.20, (166, 41, 41), (1,)),
        Element("I", "Iod", 53, 1.39, (148, 0, 148), (1,)),
    )
}

DEFAULT_COLOR: RGB = (25, 25, 25)


def get_element(symbol: str) -> Element | None:
    """Elementdaten oder ``None``, wenn das Symbol unbekannt ist."""
    return ELEMENTS.get(symbol)


def display_color(symbol: str) -> RGB:
    """Farbe für Atomlabels; unbekannte Elemente werden dunkelgrau."""
    element = ELEMENTS.get(symbol)
    return element.color if element else DEFAULT_COLOR
