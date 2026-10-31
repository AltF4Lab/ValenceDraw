# Changelog

Alle nennenswerten Änderungen an ValenceDraw. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/).

## [0.1.0] – 2026-10-31

Erstes veröffentlichtes Release (MVP, Meilenstein 5).

### Hinzugefügt

- Zeichenfläche mit Ethan, Bindungswerkzeug (1–3), Ring-Templates und
  automatischem Winkel-Rasten (15°).
- Atome setzen, Atomlabels/Gruppenlabels direkt am Atom, automatische
  H-Atome an Heteroatomen inkl. Ladungsabhängigkeit.
- Ladungen (`+`, `2+` …), Teilladungen (δ⁺/δ⁻) und frei positionierbare
  Ladungspositionen.
- Elektronenpaare (zwei Punkte) und Radikale (ein Punkt).
- Keil- und Strichkeilbindungen inkl. nachträglicher Umwandlung und Spiegeln.
- Texte mit Hoch-/Tiefstellung sowie LaTeX-Formeln (`$…$`).
- Reaktionspfeile und Elektronenfluss-Pfeile (gebogen, nachträglich
  verlänger- und krümmbar).
- Auswahl, Verschieben, Kopieren/Einfügen, Undo/Redo.
- Farbpalette für Atome, Bindungen, Moleküle, Texte und Pfeile.
- Ansatztabelle (Äquivalente, molare Masse, Stoffmenge, Masse, Dichte,
  Volumen) inkl. LaTeX-Export.
- Seitenformate (A4, A3, A5, Letter, Legal) mit Hoch- und Querformat.
- Dateiformate: Projektdatei `.valencedraw` (JSON), `.mol`, `.sdf`, `.smi`
  über RDKit; Export nach SVG und PNG.

### Bekannte Einschränkungen

- Die ausführbaren Builds sind nicht signiert. Unter macOS muss das Programm
  beim ersten Start per Rechtsklick → „Öffnen“ freigegeben werden, unter
  Windows erscheint ggf. ein SmartScreen-Hinweis.

[0.1.0]: https://github.com/AltF4Lab/ValenceDraw/releases/tag/v0.1.0
