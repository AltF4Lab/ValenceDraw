"""Farbpalette und Farbhilfen (Qt-frei).

Objekte speichern ihre Farbe optional als RGB-Tripel. ``None`` bedeutet
„Standardfarbe“ – gezeichnet wird dann mit dem Bindungston aus dem ``Style``
(also schwarz). So bleibt die Zeichnung zunächst einfarbig und lässt sich
nachträglich über die Palette einfärben.
"""

from __future__ import annotations

from collections.abc import Sequence

RGB = tuple[int, int, int]

#: Standardfarbe aller Objekte (identisch mit ``Style.bond_color``).
DEFAULT_COLOR: RGB = (25, 25, 25)

#: Farben der Palette in der Oberfläche (Name, RGB).
PALETTE: tuple[tuple[str, RGB], ...] = (
    ("Schwarz", DEFAULT_COLOR),
    ("Grau", (110, 110, 110)),
    ("Rot", (210, 40, 40)),
    ("Orange", (230, 120, 0)),
    ("Gelb", (200, 160, 0)),
    ("Grün", (20, 140, 60)),
    ("Türkis", (0, 140, 145)),
    ("Blau", (40, 90, 200)),
    ("Violett", (135, 60, 190)),
    ("Braun", (130, 85, 45)),
)


def normalize_color(color: Sequence[int] | RGB | None) -> RGB | None:
    """Prüft und normalisiert eine Farbe auf ``(r, g, b)`` mit Werten 0–255.

    ``None`` bleibt ``None`` (Standardfarbe). Ungültige Eingaben lösen einen
    ``ValueError`` aus, damit ein fehlerhaftes Modell nicht stillschweigend
    falsche Farben zeichnet.
    """
    if color is None:
        return None
    try:
        values = tuple(int(value) for value in color)
    except TypeError as exc:  # nicht iterierbar
        raise ValueError(f"Ungültige Farbe: {color!r}") from exc
    if len(values) != 3:
        raise ValueError(f"Eine Farbe braucht drei Werte (RGB): {color!r}")
    if any(value < 0 or value > 255 for value in values):
        raise ValueError(f"Farbwerte müssen zwischen 0 und 255 liegen: {color!r}")
    return values  # type: ignore[return-value]


def color_to_hex(color: RGB) -> str:
    """Farbe als ``#rrggbb`` (für Tests, Anzeige und Export)."""
    return "#{:02x}{:02x}{:02x}".format(*color)
