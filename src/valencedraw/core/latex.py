"""LaTeX-Mathematik in Textbeschriftungen.

Die Textbeschriftungen des Editors kennen bereits eine kleine Auszeichnung
(``_{…}``, ``^{…}``, ``**fett**``, ``*kursiv*``). Dieser Baustein übersetzt
Formeln zwischen ``$…$`` in genau diese Auszeichnung – es ist also **kein**
voller TeX-Satz, sondern eine praxistaugliche Teilmenge:

* Symbole werden zu echten Unicode-Zeichen: ``\\alpha`` → α, ``\\rightarrow``
  → →, ``\\cdot`` → ·, ``\\infty`` → ∞ …
* Hoch- und Tiefstellung: ``x^2``, ``K_a``, ``SO_4^{2-}``
* Brüche werden **einzeilig** gesetzt: ``\\frac{a}{b}`` → ``a/b``, bei Summen
  automatisch mit Klammern: ``\\frac{a+b}{c}`` → ``(a+b)/c``
* Wurzeln: ``\\sqrt{2}`` → √2, ``\\sqrt[3]{x}`` → ∛x
* Schriftstile: ``\\mathrm{…}`` / ``\\text{…}``, ``\\mathbf{…}`` → fett,
  ``\\mathit{…}`` → kursiv
* Akzente: ``\\bar{x}``, ``\\hat{x}``, ``\\vec{v}``, ``\\dot{x}`` …
* Abstände: ``\\,``, ``\\;``, ``\\quad``, ``\\qquad``

Das Ergebnis wird von :mod:`valencedraw.core.markup` ganz normal weiterverarbeitet,
gilt also überall, wo Text gerendert wird: Beschriftungen, Gruppenlabels,
Dialog-Vorschau, SVG/PNG-Export und Projektdatei.
"""

from __future__ import annotations

MATH_DELIMITER = "$"
_ESCAPE = "\\"

#: Zeichen, die als Befehl (ohne Backslash) direkt übersetzt werden.
SYMBOLS: dict[str, str] = {
    # griechische Kleinbuchstaben
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "vartheta": "ϑ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "varpi": "ϖ",
    "rho": "ρ",
    "varrho": "ϱ",
    "sigma": "σ",
    "varsigma": "ς",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "varphi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    # griechische Großbuchstaben
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
    # Operatoren und Relationen
    "cdot": "·",
    "times": "×",
    "div": "÷",
    "pm": "±",
    "mp": "∓",
    "ast": "∗",
    "star": "⋆",
    "circ": "∘",
    "bullet": "•",
    "oplus": "⊕",
    "otimes": "⊗",
    "neq": "≠",
    "ne": "≠",
    "equiv": "≡",
    "approx": "≈",
    "cong": "≅",
    "sim": "∼",
    "simeq": "≃",
    "propto": "∝",
    "leq": "≤",
    "le": "≤",
    "geq": "≥",
    "ge": "≥",
    "ll": "≪",
    "gg": "≫",
    "lll": "⋘",
    "ggg": "⋙",
    "in": "∈",
    "notin": "∉",
    "ni": "∋",
    "subset": "⊂",
    "supset": "⊃",
    "subseteq": "⊆",
    "supseteq": "⊇",
    "cup": "∪",
    "cap": "∩",
    "setminus": "∖",
    "emptyset": "∅",
    "varnothing": "∅",
    "forall": "∀",
    "exists": "∃",
    "nexists": "∄",
    "neg": "¬",
    "lnot": "¬",
    "wedge": "∧",
    "land": "∧",
    "vee": "∨",
    "lor": "∨",
    "perp": "⊥",
    "parallel": "∥",
    "angle": "∠",
    "triangle": "△",
    "degree": "°",
    "prime": "′",
    "hbar": "ℏ",
    "ell": "ℓ",
    "infty": "∞",
    "partial": "∂",
    "nabla": "∇",
    "sum": "∑",
    "prod": "∏",
    "coprod": "∐",
    "int": "∫",
    "iint": "∬",
    "iiint": "∭",
    "oint": "∮",
    "radical": "√",
    # Pfeile
    "to": "→",
    "rightarrow": "→",
    "longrightarrow": "⟶",
    "leftarrow": "←",
    "longleftarrow": "⟵",
    "leftrightarrow": "↔",
    "longleftrightarrow": "⟷",
    "Rightarrow": "⇒",
    "Longrightarrow": "⟹",
    "Leftarrow": "⇐",
    "Leftrightarrow": "⇔",
    "iff": "⇔",
    "implies": "⇒",
    "uparrow": "↑",
    "downarrow": "↓",
    "mapsto": "↦",
    "rightleftharpoons": "⇌",
    "leftrightharpoons": "⇋",
    "rightleftarrows": "⇄",
    "updownarrow": "↕",
    "nearrow": "↗",
    "searrow": "↘",
    "swarrow": "↙",
    "nwarrow": "↖",
    # Auslassungen und Sonstiges
    "dots": "…",
    "ldots": "…",
    "cdots": "⋯",
    "vdots": "⋮",
    "ddots": "⋱",
    "textellipsis": "…",
    "S": "§",
    "P": "¶",
    "copyright": "©",
    "AA": "Å",
    "textdegree": "°",
    "textmu": "µ",
}

#: Abstandsbefehle (der Schlüssel ist der Befehl ohne Backslash).
SPACES: dict[str, str] = {
    ",": "\u2009",  # schmaler Abstand
    ":": "\u2005",
    ";": "\u2004",
    "!": "",
    " ": " ",
    "enspace": "\u2002",
    "quad": "\u2002\u2002",
    "qquad": "\u2002\u2002\u2002\u2002",
    "thinspace": "\u2009",
    "medspace": "\u2005",
    "thickspace": "\u2004",
}

#: Befehle, deren Argument unverändert (aufrecht) übernommen wird.
TEXT_COMMANDS = frozenset(
    {
        "mathrm",
        "text",
        "textrm",
        "textup",
        "textnormal",
        "operatorname",
        "mathsf",
        "mathtt",
        "mbox",
        "hbox",
        "ce",
    }
)

BOLD_COMMANDS = frozenset({"mathbf", "boldsymbol", "bm", "textbf", "bf"})
ITALIC_COMMANDS = frozenset({"mathit", "textit", "emph", "it"})

#: Kombinierende Zeichen für Akzentbefehle.
ACCENTS: dict[str, str] = {
    "hat": "\u0302",
    "widehat": "\u0302",
    "bar": "\u0304",
    "overline": "\u0305",
    "tilde": "\u0303",
    "widetilde": "\u0303",
    "vec": "\u20d7",
    "dot": "\u0307",
    "ddot": "\u0308",
    "acute": "\u0301",
    "grave": "\u0300",
    "breve": "\u0306",
    "check": "\u030c",
}

FRACTION_COMMANDS = frozenset({"frac", "dfrac", "tfrac", "cfrac"})

#: Funktionsnamen (aufrecht gesetzt, mit Abstand zum Argument: ``\ln K``).
FUNCTION_COMMANDS = frozenset(
    {
        "ln",
        "log",
        "lg",
        "exp",
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "arcsin",
        "arccos",
        "arctan",
        "sinh",
        "cosh",
        "tanh",
        "coth",
        "lim",
        "max",
        "min",
        "sup",
        "inf",
        "det",
        "gcd",
        "deg",
        "dim",
        "ker",
        "arg",
        "mod",
        "hom",
        "Pr",
    }
)

#: Befehle ohne Ausgabe (nur Satzsteuerung).
IGNORED_COMMANDS = frozenset(
    {
        "displaystyle",
        "textstyle",
        "scriptstyle",
        "scriptscriptstyle",
        "limits",
        "nolimits",
        "nonumber",
        "notag",
        "relax",
        "mathstrut",
        "strut",
    }
)

#: Zeichen nach ``\left``/``\right``/``\bigl`` …
DELIMITERS: dict[str, str] = {
    ".": "",
    "(": "(",
    ")": ")",
    "[": "[",
    "]": "]",
    "|": "|",
    "/": "/",
    "<": "⟨",
    ">": "⟩",
}

#: Benannte Begrenzer (nach Backslash).
NAMED_DELIMITERS: dict[str, str] = {
    "{": "{",
    "}": "}",
    "|": "‖",
    "vert": "|",
    "Vert": "‖",
    "lvert": "|",
    "rvert": "|",
    "lVert": "‖",
    "rVert": "‖",
    "langle": "⟨",
    "rangle": "⟩",
    "lfloor": "⌊",
    "rfloor": "⌋",
    "lceil": "⌈",
    "rceil": "⌉",
    "lbrack": "[",
    "rbrack": "]",
    "uparrow": "↑",
    "downarrow": "↓",
    "backslash": "\\",
}

#: Einzelzeichen, die in Mathe anders aussehen als im Quelltext.
PLAIN_CHARS: dict[str, str] = {
    "-": "\u2212",  # echtes Minuszeichen
    "*": "·",
    "'": "′",
    "~": " ",
}

_OPERATORS = frozenset(" +−·×÷=/<>±∓≤≥≠≈≡∑∏∫")

#: Befehle, die nur ihren Begrenzer setzen (``\left(`` → ``(``).
DELIMITER_COMMANDS = frozenset(
    {
        "left",
        "right",
        "big",
        "Big",
        "bigg",
        "Bigg",
        "bigl",
        "bigr",
        "Bigl",
        "Bigr",
    }
)


#: Schließende Begrenzer – ein Leerzeichen davor wird entfernt (``(a)``).
_CLOSING_DELIMITERS = frozenset({")", "]", "}", "⟩", "⌋", "⌉", "|", "‖"})


def _trim_space(parts: list[str]) -> None:
    """Entfernt Leerraum am Ende der bisherigen Ausgabe."""
    while parts and not parts[-1].strip():
        parts.pop()
    if parts:
        parts[-1] = parts[-1].rstrip(" ")


def _is_wrapped(text: str) -> bool:
    """Ist ``text`` bereits vollständig von Klammern umschlossen?"""
    if len(text) < 2:
        return False
    return (text[0], text[-1]) in {("(", ")"), ("[", "]"), ("{", "}"), ("⟨", "⟩")}


def _needs_parens(text: str) -> bool:
    """Braucht der Teil in einem Bruch eigene Klammern?"""
    if not text or _is_wrapped(text):
        return False
    return any(char in _OPERATORS for char in text)


def _wrap(text: str) -> str:
    """Klammert einen Bruch-/Wurzelteil nur dann, wenn es nötig ist."""
    stripped = text.strip()
    if not stripped:
        return ""
    return f"({stripped})" if _needs_parens(stripped) else stripped


def _word_like(char: str) -> bool:
    """Zählt das Zeichen als „Wortzeichen“ (Leerzeichen darf dann entfallen)?"""
    return bool(char) and (char.isalnum() or char in "′°")


class _LatexParser:
    """Kleiner rekursiver Parser für die unterstützte LaTeX-Teilmenge."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.index = 0
        self._force_space = False

    # -- Grundlagen ---------------------------------------------------
    def parse(self) -> str:
        return self._sequence().strip()

    def _peek(self) -> str:
        return self.source[self.index] if self.index < len(self.source) else ""

    def _skip_spaces(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1

    def _read_name(self) -> str:
        """Liest einen Befehlsnamen (``frac``) oder ein Einzelzeichen (``,``)."""
        start = self.index
        while self.index < len(self.source) and self.source[self.index].isalpha():
            self.index += 1
        if self.index == start:
            char = self._peek()
            if char:
                self.index += 1
            return char
        return self.source[start : self.index]

    def _sequence(self, in_script: bool = False, text_mode: bool = False) -> str:
        parts: list[str] = []
        while self.index < len(self.source):
            char = self.source[self.index]

            if char == "}":
                break

            if char.isspace():
                self._skip_spaces()
                if text_mode or self._force_space or self._space_wanted(parts):
                    parts.append(" ")
                self._force_space = False
                continue

            if char == "{":
                self.index += 1
                parts.append(self._sequence(in_script, text_mode))
                self._close_group()
                continue

            if char == _ESCAPE:
                text = self._command(in_script)
                if text in _CLOSING_DELIMITERS:
                    _trim_space(parts)
                parts.append(text)
                continue

            if char in ("^", "_"):
                parts.append(self._script(char, in_script))
                continue

            if char == MATH_DELIMITER:
                # ``$`` innerhalb einer Formel ignorieren
                self.index += 1
                continue

            self.index += 1
            parts.append(PLAIN_CHARS.get(char, char))
        return "".join(parts)

    def _space_wanted(self, parts: list[str]) -> bool:
        """Leerzeichen nur behalten, wenn es zwei Wortzeichen trennt."""
        previous = parts[-1][-1] if parts and parts[-1] else ""
        following = self._peek()
        if previous in "([{" or following in ")]},.;:":
            return False
        return not (_word_like(previous) and _word_like(following))

    def _close_group(self) -> None:
        if self._peek() == "}":
            self.index += 1

    # -- Argumente ----------------------------------------------------
    def _argument(self, in_script: bool = False, text_mode: bool = False) -> str:
        self._skip_spaces()
        if self._peek() == "{":
            self.index += 1
            content = self._sequence(in_script, text_mode)
            self._close_group()
            return content
        if self._peek() == _ESCAPE:
            return self._command(in_script)
        char = self._peek()
        if not char:
            return ""
        self.index += 1
        return PLAIN_CHARS.get(char, char)

    def _script(self, marker: str, in_script: bool) -> str:
        self.index += 1
        content = self._argument(in_script=True)
        if not content:
            return ""
        if in_script:
            # Unser Markup kennt keine verschachtelten Skripte – flach übernehmen.
            return content
        prefix = "^" if marker == "^" else "_"
        return f"{prefix}{{{content}}}"

    def _delimiter(self) -> str:
        self._skip_spaces()
        char = self._peek()
        if not char:
            return ""
        if char == _ESCAPE:
            self.index += 1
            return NAMED_DELIMITERS.get(self._read_name(), "")
        self.index += 1
        return DELIMITERS.get(char, char)

    # -- Befehle ------------------------------------------------------
    def _command(self, in_script: bool) -> str:
        self.index += 1  # Backslash
        name = self._read_name()

        if name in SPACES:
            return SPACES[name]
        if name in IGNORED_COMMANDS:
            return ""
        if name in FUNCTION_COMMANDS:
            # ``\ln K``: der Abstand zum Argument bleibt erhalten.
            self._force_space = True
            return name
        if name in FRACTION_COMMANDS:
            return self._fraction(in_script)
        if name == "sqrt":
            return self._sqrt(in_script)
        if name in TEXT_COMMANDS:
            return self._argument(in_script, text_mode=True)
        if name in BOLD_COMMANDS:
            content = self._argument(in_script, text_mode=True)
            return f"**{content}**" if content else ""
        if name in ITALIC_COMMANDS:
            content = self._argument(in_script, text_mode=True)
            return f"*{content}*" if content else ""
        if name in ACCENTS:
            return self._accent(ACCENTS[name], in_script)
        if name in DELIMITER_COMMANDS:
            return self._delimiter()
        if name in ("begin", "end"):
            self._argument(in_script)  # Umgebungsnamen verwerfen
            return ""
        if name in ("\\", "newline", "cr"):
            return " "
        if name in ("{", "}", "%", "&", "#", "_", "^", MATH_DELIMITER):
            return name
        if name in SYMBOLS:
            return SYMBOLS[name]
        # Unbekannter Befehl: Namen als Text übernehmen, damit nichts verschwindet.
        return name

    def _accent(self, mark: str, in_script: bool) -> str:
        content = self._argument(in_script, text_mode=True)
        if not content:
            return ""
        return "".join(char + mark for char in content)

    def _fraction(self, in_script: bool) -> str:
        numerator = self._argument(in_script)
        denominator = self._argument(in_script)
        if not denominator:
            return _wrap(numerator)
        if not numerator:
            return _wrap(denominator)
        return f"{_wrap(numerator)}/{_wrap(denominator)}"

    def _sqrt(self, in_script: bool) -> str:
        self._skip_spaces()
        index_text = ""
        if self._peek() == "[":
            end = self.source.find("]", self.index + 1)
            if end != -1:
                index_text = _LatexParser(self.source[self.index + 1 : end]).parse()
                self.index = end + 1
        content = _wrap(self._argument(in_script))
        index_text = index_text.strip()
        if index_text == "3":
            return "\u221b" + content
        if index_text == "4":
            return "\u221c" + content
        if index_text and not in_script:
            return f"^{{{index_text}}}\u221a{content}"
        return "\u221a" + content


def latex_to_markup(source: str) -> str:
    """Übersetzt eine LaTeX-Formel (ohne ``$``) in die Editor-Auszeichnung."""
    return _LatexParser(source).parse()


def _find_closing(markup: str, start: int, delimiter: str) -> int:
    """Position des nächsten nicht maskierten ``delimiter`` (oder ``-1``)."""
    index = start
    length = len(markup)
    while index < length:
        if markup[index] == _ESCAPE:
            index += 2
            continue
        if markup.startswith(delimiter, index):
            return index
        index += 1
    return -1


def expand_math(markup: str) -> str:
    """Ersetzt alle ``$…$``-Formeln in ``markup`` durch übersetzten Text.

    ``\\$`` bleibt ein literales Dollarzeichen; eine Formel ohne schließendes
    ``$`` bleibt unverändert stehen.
    """
    if MATH_DELIMITER not in markup:
        return markup

    parts: list[str] = []
    index = 0
    length = len(markup)
    while index < length:
        char = markup[index]
        if char == _ESCAPE and index + 1 < length:
            parts.append(markup[index : index + 2])
            index += 2
            continue
        if char != MATH_DELIMITER:
            parts.append(char)
            index += 1
            continue

        delimiter = (
            MATH_DELIMITER * 2
            if markup.startswith(MATH_DELIMITER * 2, index)
            else MATH_DELIMITER
        )
        end = _find_closing(markup, index + len(delimiter), delimiter)
        if end == -1:
            parts.append(char)
            index += 1
            continue
        parts.append(latex_to_markup(markup[index + len(delimiter) : end]))
        index = end + len(delimiter)

    return "".join(parts)


def has_math(markup: str) -> bool:
    """Enthält der Text mindestens eine ``$…$``-Formel?"""
    return expand_math(markup) != markup
