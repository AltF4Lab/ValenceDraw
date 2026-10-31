"""Ansatztabelle: Äquivalente, molare Masse, Stoffmenge, Masse und Volumen.

Das Modell rechnet mit einer gemeinsamen Bezugsstoffmenge (``base_amount``,
Stoffmenge zu 1 eq in mmol). Jede Zeile speichert ihre Äquivalente, molare
Masse und Dichte; Stoffmenge, Masse und Volumen werden daraus abgeleitet:

* ``n = eq · base_amount`` (mmol)
* ``m = n · M / 1000`` (g)
* ``V = m / ρ`` (mL)

Ändert der Anwender einen abgeleiteten Wert, wird daraus die Bezugsstoffmenge
neu bestimmt – dadurch passen sich alle anderen Zeilen automatisch an.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: Spalten, die der Anwender direkt bearbeiten kann.
NUMERIC_FIELDS: tuple[str, ...] = ("eq", "M", "n", "m", "rho", "V")


class StoichiometryError(ValueError):
    """Eine Eingabe in der Ansatztabelle ist nicht sinnvoll."""


class RowRole(str, Enum):
    """Rolle einer Zeile in der Reaktionsgleichung."""

    EDUKT = "educt"
    PRODUKT = "produkt"
    REAGENZ = "reagenz"


ROLE_LABELS: dict[RowRole, str] = {
    RowRole.EDUKT: "Edukt",
    RowRole.PRODUKT: "Produkt",
    RowRole.REAGENZ: "Reagenz",
}


@dataclass
class StoichiometryRow:
    """Eine Substanz der Ansatztabelle (Edukt, Produkt oder Reagenz)."""

    name: str
    role: RowRole
    molar_mass: float | None = None
    equivalents: float | None = None
    density: float | None = None


@dataclass
class StoichiometryTable:
    """Rechenmodell der Ansatztabelle."""

    rows: list[StoichiometryRow] = field(default_factory=list)
    base_amount_mmol: float | None = None

    # -- abgeleitete Werte ------------------------------------------------
    def amount_mmol(self, row: StoichiometryRow) -> float | None:
        """Stoffmenge in mmol, sobald Äquivalente und Bezugsmenge bekannt sind."""
        if row.equivalents is None or self.base_amount_mmol is None:
            return None
        return row.equivalents * self.base_amount_mmol

    def mass_g(self, row: StoichiometryRow) -> float | None:
        """Masse in g (aus Stoffmenge und molarer Masse)."""
        amount = self.amount_mmol(row)
        if amount is None or row.molar_mass is None:
            return None
        return amount * row.molar_mass / 1000.0

    def volume_ml(self, row: StoichiometryRow) -> float | None:
        """Volumen in mL (aus Masse und Dichte)."""
        mass = self.mass_g(row)
        if mass is None or row.density is None:
            return None
        return mass / row.density

    # -- Eingaben ---------------------------------------------------------
    def rename(self, index: int, name: str) -> str | None:
        """Benennt eine Zeile um; der Anwender kann z. B. „Reagenz 1“ ersetzen."""
        if not 0 <= index < len(self.rows):
            raise StoichiometryError("Unbekannte Tabellenzeile.")
        cleaned = name.strip()
        if not cleaned:
            return "Der Name darf nicht leer sein."
        self.rows[index].name = cleaned
        return None

    def set_value(
        self,
        index: int,
        field_name: str,
        value: float | None,
    ) -> str | None:
        """Übernimmt einen bearbeiteten Tabellenwert.

        Liefert ``None`` bei Erfolg oder eine deutsche Fehlermeldung, wenn die
        Eingabe nicht übernommen werden kann (z. B. fehlende molare Masse).
        """
        if not 0 <= index < len(self.rows):
            raise StoichiometryError("Unbekannte Tabellenzeile.")
        if field_name not in NUMERIC_FIELDS:
            raise StoichiometryError(f"Unbekannte Spalte: {field_name}")
        row = self.rows[index]

        if field_name == "eq":
            if value is not None and value <= 0:
                return "Äquivalente müssen größer als 0 sein."
            row.equivalents = value
            return None
        if field_name == "M":
            if value is not None and value <= 0:
                return "Die molare Masse muss größer als 0 sein."
            row.molar_mass = value
            return None
        if field_name == "rho":
            if value is not None and value <= 0:
                return "Die Dichte muss größer als 0 sein."
            row.density = value
            return None

        if value is None:
            # Leere abgeleitete Zellen werden beim Neuzeichnen wieder aufgefüllt.
            return None
        if value < 0:
            return "Werte dürfen nicht negativ sein."

        if field_name == "n":
            self._apply_amount(index, value)
            return None
        if field_name == "m":
            if row.molar_mass is None:
                return "Für die Stoffmenge fehlt die molare Masse (M)."
            self._apply_amount(index, value / row.molar_mass * 1000.0)
            return None
        if field_name == "V":
            if row.density is None:
                return "Für die Masse fehlt die Dichte (ρ)."
            if row.molar_mass is None:
                return "Für die Stoffmenge fehlt die molare Masse (M)."
            mass = value * row.density
            self._apply_amount(index, mass / row.molar_mass * 1000.0)
            return None
        raise StoichiometryError(f"Unbekannte Spalte: {field_name}")

    def _apply_amount(self, index: int, amount_mmol: float) -> None:
        """Setzt die Bezugsmenge so, dass Zeile ``index`` diese Stoffmenge hat."""
        row = self.rows[index]
        if row.equivalents is None or row.equivalents <= 0:
            row.equivalents = 1.0
        self.base_amount_mmol = amount_mmol / row.equivalents


def format_value(value: float | None, decimals: int = 3) -> str:
    """Zahl für die Tabelle formatieren (ohne überflüssige Nullen)."""
    if value is None:
        return ""
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


_LATEX_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    """Sonderzeichen für die Verwendung in einer LaTeX-Tabelle maskieren."""
    return "".join(_LATEX_ESCAPES.get(character, character) for character in text)


def latex_table(table: "StoichiometryTable") -> str:
    """Ansatztabelle als einfügbarer LaTeX-``tabular``-Code."""
    lines = [
        "% Ansatztabelle (ValenceDraw)",
        "% Dezimaltrennzeichen: Punkt",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\hline",
        (
            r"Substanz & Rolle & $eq$ & $M$/(g\,mol$^{-1}$) & $n$/mmol & "
            r"$m$/g & $\rho$/(g\,mL$^{-1}$) & $V$/mL \\"
        ),
        r"\hline",
    ]
    for row in table.rows:
        values = [
            latex_escape(row.name),
            latex_escape(ROLE_LABELS[row.role]),
            format_value(row.equivalents, 4),
            format_value(row.molar_mass, 4),
            format_value(table.amount_mmol(row), 4),
            format_value(table.mass_g(row), 5),
            format_value(row.density, 4),
            format_value(table.volume_ml(row), 4),
        ]
        lines.append(" & ".join(values) + r" \\")
    lines.extend((r"\hline", r"\end{tabular}"))
    return "\n".join(lines)
