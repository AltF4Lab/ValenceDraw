"""Zeichen-Styling (Farben, Linienbreiten, Schriftgrößen in Szeneneinheiten)."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.geometry import BOND_LENGTH

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Style:
    """Alle Maße in Szeneneinheiten (1 Bindungslänge = ``bond_length``)."""

    bond_length: float = BOND_LENGTH
    bond_width: float = 3.0
    double_bond_offset: float = 7.0
    """Abstand zwischen den beiden Linien einer Doppelbindung."""

    triple_bond_offset: float = 8.0
    """Abstand zwischen den beiden Außenlinien einer Dreifachbindung."""

    wedge_width: float = 7.0
    """Breite der dicken Seite eines Keils (0,7 mm)."""

    wedge_hatch_spacing: float = 5.5
    """Abstand der Querstriche eines Strichkeils (0,55 mm)."""

    label_font_family: str = "Segoe UI"
    label_pixel_size: int = 30
    label_padding: float = 2.0
    """Abstand zwischen Bindung und Atomlabel (Rand der weißen Maske)."""

    bond_label_gap: float = 3.0
    """Zusätzlicher Abstand zwischen Bindungsende und Label (0,3 mm)."""

    text_font_family: str = "Segoe UI"
    text_pixel_size: int = 28

    arrow_head_length: float = 18.0
    arrow_head_width: float = 10.0
    arrow_gap: float = 8.0
    """Abstand zwischen den beiden Linien des Gleichgewichtspfeils (0,8 mm)."""

    equilibrium_head_scale: float = 0.8
    """Größe der Spitzen am Gleichgewichtspfeil relativ zur normalen Spitze."""

    bond_color: RGB = (25, 25, 25)
    background: RGB = (255, 255, 255)
    """Blatt- und Export-Hintergrund."""

    workspace_background: RGB = (168, 168, 168)
    """Arbeitsfläche um das Blatt (nicht im Export)."""

    page_border: RGB = (130, 130, 130)
    page_shadow_alpha: int = 60
    page_shadow_offset: float = 10.0
    """Versatz des Blattschatten in Szeneneinheiten (1 mm)."""

    selection_color: RGB = (0, 122, 204)
    selection_alpha: int = 70
    selection_width: float = 16.0

    preview_color: RGB = (0, 122, 204)
    preview_width: float = 2.0

    hover_alpha: int = 170
    """Deckkraft des Hover-Rings, der das Einrast-Ziel anzeigt."""

    bond_hover_alpha: int = 90
    """Deckkraft der Hervorhebung einer Bindung unter dem Cursor."""

    hit_radius_factor: float = 0.32
    """Trefferradius (Anteil der Bindungslänge) für Klicks."""

    electron_dot_radius: float = 2.2
    """Radius eines Elektronenpunkts (0,22 mm)."""

    electron_pair_gap: float = 6.0
    """Mittiger Abstand der beiden Punkte eines Elektronenpaars."""

    electron_gap: float = 4.0
    """Abstand zwischen Atomlabel und Elektronenpunkten."""

    electron_min_distance: float = 10.0
    """Mindestabstand der Elektronen vom Atomzentrum (bei unbeschriftetem Atom)."""

    @property
    def hit_radius(self) -> float:
        return self.bond_length * self.hit_radius_factor


DEFAULT_STYLE = Style()
