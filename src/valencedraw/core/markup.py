"""Sehr einfache Text-Auszeichnung für Beschriftungen.

Syntax (wie in vielen Chemie-Werkzeugen üblich):

* ``H_2O``        – die ``2`` wird tiefgestellt
* ``SO_4^{2-}``   – die ``4`` tiefgestellt, ``2-`` hochgestellt
* ``**fett**``    – fetter Text
* ``*kursiv*``    – kursiver Text
* ``$\Delta G^\circ = -RT \ln K$`` – LaTeX-Mathematik (siehe
  :mod:`valencedraw.core.latex`)
* ``\\_``, ``\\^``, ``\\*`` – literale Zeichen

Ein ``_`` oder ``^`` ohne folgenden Text bleibt ein normales Zeichen.
Fett und Kursiv lassen sich mit Hoch-/Tiefstellung kombinieren, z. B.
``**SO_4^{2-}**``.

Zusätzlich gibt es :func:`auto_format`, das die „Chemiker-Schreibweise“
(``NO2``, ``NO3-``, ``Ca2+``) automatisch in Markup übersetzt.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from enum import Enum

from .latex import expand_math

SUB_MARKER = "_"
SUPER_MARKER = "^"
BOLD_MARKER = "**"
ITALIC_MARKER = "*"
ESCAPE = "\\"

_EXPLICIT_MARKERS = (SUB_MARKER, SUPER_MARKER, "{", "}", ESCAPE)
_CHARGE_PATTERN = re.compile(r"(\d*)([+\-]{1,3})$")
_SUBSCRIPT_PATTERN = re.compile(r"(?<=[A-Za-z\)\]])(\d+)")
_ELEMENT_PATTERN = re.compile(r"[A-Z][a-z]?")
#: Mehrstellige Zahlen am Ende sind praktisch immer Indizes (``C60-``), keine Ladung.
_MAX_CHARGE_DIGITS = 1


def _is_single_element(text: str) -> bool:
    """Steht dort genau ein Elementsymbol (z. B. ``Ca`` oder ``Fe``)?

    Bewusst auch für Symbole außerhalb der kleinen Elementtabelle – sonst würde
    ``Ca2+`` fälschlich als ``Ca_{2}^{+}`` formatiert.
    """
    return bool(_ELEMENT_PATTERN.fullmatch(text))


def auto_format(text: str) -> str:
    """Wandelt Chemiker-Schreibweise automatisch in Markup um.

    * Ziffern direkt nach Buchstaben oder Klammern werden tiefgestellt:
      ``NO2`` → ``NO_{2}``, ``(CH3)2CO`` → ``(CH_{3})_{2}CO``
    * Eine abschließende Ladung wird hochgestellt: ``NO3-`` → ``NO_{3}^{-}``
    * Steht vor der Ladung nur ein Elementsymbol, gehören die Ziffern zur
      Ladung: ``Ca2+`` → ``Ca^{2+}``
    * Enthält der Text bereits explizite Auszeichnung (``_ ^ { } \\``), bleibt
      er unverändert.
    """
    if not text.strip() or any(marker in text for marker in _EXPLICIT_MARKERS):
        return text

    body = text.rstrip()
    trailing_whitespace = text[len(body) :]
    charge = ""

    match = _CHARGE_PATTERN.search(body)
    if match is not None:
        digits, signs = match.group(1), match.group(2)
        prefix = body[: match.start(1)]
        charge_digits = len(digits) <= _MAX_CHARGE_DIGITS
        single_element = _is_single_element(prefix.strip()) or prefix.endswith(" ")
        if digits and charge_digits and single_element:
            charge = digits + signs
            body = prefix
        elif digits:
            charge = signs
            body = body[: match.start(2)]
        else:
            charge = signs
            body = prefix

    formatted = _SUBSCRIPT_PATTERN.sub(r"_{\1}", body)
    if charge:
        formatted = f"{formatted}^{{{charge}}}"
    return formatted + trailing_whitespace


class Script(Enum):
    """Vertikale Ausrichtung eines Textabschnitts."""

    NORMAL = "normal"
    SUPER = "super"
    SUB = "sub"


@dataclass(frozen=True)
class TextRun:
    """Zusammenhängender Text mit einheitlicher Ausrichtung und Schriftstil."""

    text: str
    script: Script = Script.NORMAL
    bold: bool = False
    italic: bool = False


def parse_markup(markup: str) -> tuple[TextRun, ...]:
    """Zerlegt eine Markup-Zeichenkette in Abschnitte (inkl. ``$…$``-Formeln)."""
    markup = expand_math(markup)
    runs: list[TextRun] = []
    buffer: list[str] = []
    index = 0
    length = len(markup)
    bold = False
    italic = False

    def flush() -> None:
        if buffer:
            runs.append(TextRun("".join(buffer), bold=bold, italic=italic))
            buffer.clear()

    while index < length:
        char = markup[index]

        if char == ESCAPE and index + 1 < length:
            buffer.append(markup[index + 1])
            index += 2
            continue

        if char == ITALIC_MARKER:
            flush()
            if index + 1 < length and markup[index + 1] == ITALIC_MARKER:
                bold = not bold
                index += 2
            else:
                italic = not italic
                index += 1
            continue

        if char in (SUB_MARKER, SUPER_MARKER):
            script = Script.SUB if char == SUB_MARKER else Script.SUPER
            # Gruppe: _{...} bzw. ^{...}
            if index + 1 < length and markup[index + 1] == "{":
                end = markup.find("}", index + 2)
                if end != -1:
                    flush()
                    runs.append(
                        TextRun(markup[index + 2 : end], script, bold=bold, italic=italic)
                    )
                    index = end + 1
                    continue
            # Einzelzeichen: _2 bzw. ^+
            if index + 1 < length:
                flush()
                runs.append(
                    TextRun(markup[index + 1], script, bold=bold, italic=italic)
                )
                index += 2
                continue

        buffer.append(char)
        index += 1

    flush()
    return tuple(runs)


def format_markup(markup: str) -> str:
    """Wendet :func:`auto_format` auf den Text **zwischen** den ``*``-Markern an.

    So funktioniert die Chemiker-Schreibweise auch in fettem/kursivem Text:
    ``**NO2**`` wird zu ``**NO_{2}**``. ``$…$``-Formeln werden zuvor in
    Markup übersetzt.
    """
    markup = expand_math(markup)
    if ITALIC_MARKER not in markup:
        return auto_format(markup)

    parts: list[str] = []
    buffer: list[str] = []
    index = 0
    length = len(markup)

    while index < length:
        char = markup[index]
        if char == ESCAPE and index + 1 < length:
            buffer.append(markup[index : index + 2])
            index += 2
            continue
        if char == ITALIC_MARKER:
            end = index
            while end < length and markup[end] == ITALIC_MARKER:
                end += 1
            parts.append(auto_format("".join(buffer)))
            parts.append(markup[index:end])
            buffer = []
            index = end
            continue
        buffer.append(char)
        index += 1

    parts.append(auto_format("".join(buffer)))
    return "".join(parts)


def runs_to_html(runs: tuple[TextRun, ...]) -> str:
    """Erzeugt HTML für ``QTextDocument`` (inkl. Ausrichtung und Schriftstil)."""
    parts: list[str] = []
    for run in runs:
        text = html.escape(run.text).replace("\n", "<br/>").replace(" ", "&nbsp;")
        if run.script is Script.SUPER:
            text = f"<sup>{text}</sup>"
        elif run.script is Script.SUB:
            text = f"<sub>{text}</sub>"
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        parts.append(text)
    return "".join(parts)


def markup_to_html(markup: str) -> str:
    """Markup in HTML umwandeln – inklusive automatischer Formatierung."""
    return runs_to_html(parse_markup(format_markup(markup)))


def to_plain_text(markup: str) -> str:
    """Markup ohne Auszeichnung – z. B. für Tooltips oder Dateinamen."""
    return "".join(run.text for run in parse_markup(format_markup(markup)))
