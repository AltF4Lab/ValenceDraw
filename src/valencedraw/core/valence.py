"""Valenzregeln für die Anzeige impliziter Wasserstoffatome.

Das Molekülmodell speichert keine Wasserstoffatome – sie ergeben sich beim
Zeichnen aus der Summe der Bindungsordnungen und der typischen Valenz des
Elements. Eine zusätzliche Bindung (oder eine Doppelbindung) verbraucht dabei
ein Bindungsvermögen, sodass z. B. aus ``OH`` ein ``O`` wird.

Formalladungen verschieben die Valenz um genau eine Stufe: ``O⁺`` hat drei,
``O⁻`` nur eine Bindung (daher ``OH_2⁺`` bzw. ``O⁻``). Elektronenpaare und
Radikale bleiben bewusst ohne Einfluss.
"""

from __future__ import annotations

from .elements import get_element


def implicit_hydrogens(element: str, charge: int, bonded_valence: int) -> int:
    """Zahl der impliziten Wasserstoffatome an einem Atom.

    Maßgeblich ist die **niedrigste** Valenz des Elements plus Formalladung.
    Höhere Valenzen (Schwefel, Phosphor) werden nicht aufgefüllt – ein Sulfon
    mit sechs Bindungen zeigt also kein ``H``.

    >>> implicit_hydrogens("O", 0, 1)  # OH
    1
    >>> implicit_hydrogens("O", 0, 2), implicit_hydrogens("O", 0, 3)
    (0, 0)
    >>> implicit_hydrogens("O", 1, 1), implicit_hydrogens("O", -1, 1)
    (2, 0)
    >>> implicit_hydrogens("N", 0, 1), implicit_hydrogens("N", 0, 3)
    (2, 0)
    >>> implicit_hydrogens("N", 0, 4), implicit_hydrogens("Mn", 0, 4)
    (0, 0)
    """
    data = get_element(element)
    if data is None:
        return 0
    target = data.valences[0] + int(charge)
    return max(0, target - int(bonded_valence))


__all__ = ["implicit_hydrogens"]
