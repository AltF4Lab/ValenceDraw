"""Hauptfenster: Menüs, Toolbar, Statusleiste und Dateioperationen."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QMimeData, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from ..core.annotations import ARROW_LABELS, ArrowKind
from ..core.colors import RGB
from ..core.elements import ELEMENT_ORDER
from ..core.geometry import Point2D
from ..core.molecule import Molecule
from ..core.page import Orientation, Page, PageFormat
from ..core.templates import RING_TEMPLATES
from ..document.clipboard import (
    CLIPBOARD_MIME,
    Fragment,
    fragment_from_json,
    fragment_to_json,
)
from ..document.document import Document
from ..document.io import ChemistryError, load_molecule, save_molecule
from ..document.project import (
    PROJECT_SUFFIX,
    Project,
    ProjectError,
    load_project,
    save_project,
)
from ..document.reaction import (
    ReactionAnalysisError,
    analyze_reaction,
    table_from_analysis,
)
from ..render.export import save_png, save_svg
from ..render.painter import atom_label, atom_label_full
from ..render.style import DEFAULT_STYLE, Style
from .canvas import Canvas
from .charge_dialog import ChargeDialog
from .color_palette import ColorPalette
from .settings_dialog import SettingsDialog
from .stoichiometry_panel import StoichiometryPanel
from .text_dialog import TextDialog
from .tools import (
    AtomTool,
    ArrowTool,
    BondTool,
    ChargeTool,
    ElectronTool,
    EraseTool,
    HashedBondTool,
    PartialChargeTool,
    RingTool,
    SelectTool,
    TextTool,
    Tool,
    WedgeBondTool,
)

TOOL_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("select", "Auswahl", "V"),
    ("bond", "Bindung", "B"),
    ("wedge", "Keil", "K"),
    ("hashed", "Strichkeil", "S"),
    ("atom", "Atom", "A"),
    ("charge", "Ladung", "L"),
    ("partial", "Teilladung", "Shift+L"),
    ("electron", "Elektronen", "D"),
    ("ring", "Ring", "R"),
    ("text", "Text", "T"),
    ("arrow", "Pfeil", "P"),
    ("erase", "Radierer", "E"),
)

TOOL_TOOLBAR_LABELS: dict[str, str] = {
    "partial": "\u03b4",
}
"""Kurze Beschriftung in der Toolbar (das Menü zeigt den vollen Namen)."""

BOND_ORDERS: tuple[tuple[str, int], ...] = (
    ("Einfach", 1),
    ("Doppel", 2),
    ("Dreifach", 3),
)


class MainWindow(QMainWindow):
    """Fenster mit Canvas, Werkzeugleiste und Datei-I/O."""

    def __init__(
        self,
        document: Document | None = None,
        style: Style = DEFAULT_STYLE,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._style = style
        self._document = document if document is not None else Document()
        self._path: Path | None = None
        self._paste_count = 0
        self._stoich_panel: StoichiometryPanel | None = None

        self._canvas = Canvas(self._document, style, self)
        self.setCentralWidget(self._canvas)

        self._tools: dict[str, Tool] = {
            "select": SelectTool(self._document, style, self),
            "bond": BondTool(self._document, style, self),
            "wedge": WedgeBondTool(self._document, style, self),
            "hashed": HashedBondTool(self._document, style, self),
            "atom": AtomTool(self._document, style, self),
            "charge": ChargeTool(self._document, style, self),
            "partial": PartialChargeTool(self._document, style, self),
            "electron": ElectronTool(self._document, style, self),
            "ring": RingTool(self._document, style, self),
            "text": TextTool(self._document, style, self),
            "arrow": ArrowTool(self._document, style, self),
            "erase": EraseTool(self._document, style, self),
        }
        text_tool = self._tools["text"]
        if isinstance(text_tool, TextTool):
            text_tool.text_requested.connect(self._on_text_requested)
            text_tool.atom_label_requested.connect(self._on_atom_label_requested)
        self._tool_actions: dict[str, QAction] = {}

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_color_toolbar()
        self._create_statusbar()

        self._document.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)
        self._document.page_changed.connect(self._on_page_changed)
        self._sync_page_ui()

        self.resize(1100, 780)
        self._activate_tool("select")
        self._update_title()
        QTimer.singleShot(0, self._canvas.fit_page_width)

    # -- Aufbau ----------------------------------------------------------
    @property
    def document(self) -> Document:
        return self._document

    @property
    def canvas(self) -> Canvas:
        return self._canvas

    @property
    def style(self) -> Style:
        """Aktueller Zeichenstil (Einstellungen)."""
        return self._style

    def _create_actions(self) -> None:
        self._new_action = QAction("&Neu", self)
        self._new_action.setShortcut(QKeySequence.StandardKey.New)
        self._new_action.triggered.connect(self._new_document)

        self._open_action = QAction("&Öffnen…", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.triggered.connect(self._open_document)

        self._save_action = QAction("&Speichern", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self._save_document)

        self._save_as_action = QAction("Speichern &unter…", self)
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.triggered.connect(self._save_document_as)

        self._export_svg_action = QAction("Als &SVG exportieren…", self)
        self._export_svg_action.triggered.connect(self._export_svg)

        self._export_png_action = QAction("Als &PNG exportieren…", self)
        self._export_png_action.triggered.connect(self._export_png)

        self._quit_action = QAction("&Beenden", self)
        self._quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._quit_action.triggered.connect(self.close)

        self._undo_action = self._document.undo_stack.createUndoAction(self, "Rückgängig")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._redo_action = self._document.undo_stack.createRedoAction(self, "Wiederholen")
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        self._delete_action = QAction("&Löschen", self)
        self._delete_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self._delete_action.triggered.connect(self._document.delete_selection)

        self._cut_action = QAction("A&usschneiden", self)
        self._cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self._cut_action.triggered.connect(self._cut_selection)

        self._copy_action = QAction("&Kopieren", self)
        self._copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self._copy_action.triggered.connect(self._copy_selection)

        self._paste_action = QAction("&Einfügen", self)
        self._paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self._paste_action.triggered.connect(self._paste)

        self._select_all_action = QAction("Alles &auswählen", self)
        self._select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self._select_all_action.triggered.connect(self._document.select_all)

        self._clear_selection_action = QAction("Auswahl &aufheben", self)
        self._clear_selection_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        self._clear_selection_action.triggered.connect(self._document.clear_selection)

        self._settings_action = QAction("&Einstellungen…", self)
        self._settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self._settings_action.triggered.connect(self._open_settings)

        self._charge_action = QAction("&Ladung eingeben…", self)
        self._charge_action.setToolTip(
            "Formalladung des ausgewählten Atoms eintippen (oder Doppelklick "
            "mit dem Ladungswerkzeug)"
        )
        self._charge_action.triggered.connect(self._edit_selected_charge)

        self._stoich_action = QAction("Ansatztabelle", self)
        self._stoich_action.setShortcut(QKeySequence("F9"))
        self._stoich_action.setToolTip(
            "Aus der ausgewählten Reaktionsgleichung eine Ansatztabelle "
            "erzeugen (Reagenzien über dem Pfeil werden übernommen)"
        )
        self._stoich_action.triggered.connect(self._show_stoichiometry)

        self._zoom_in_action = QAction("&Vergrößern", self)
        self._zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._zoom_in_action.triggered.connect(self._canvas.zoom_in)

        self._zoom_out_action = QAction("&Verkleinern", self)
        self._zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._zoom_out_action.triggered.connect(self._canvas.zoom_out)

        self._fit_action = QAction("Einpassen", self)
        self._fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self._fit_action.triggered.connect(self._canvas.fit_to_view)

        self._fit_width_action = QAction("Blattbreite einpassen", self)
        self._fit_width_action.setShortcut(QKeySequence("Ctrl+Shift+0"))
        self._fit_width_action.triggered.connect(self._canvas.fit_page_width)

        # Seitenformat und Ausrichtung (Menü „Seite“)
        self._page_format_group = QActionGroup(self)
        self._page_format_group.setExclusive(True)
        self._page_format_actions: dict[PageFormat, QAction] = {}
        for page_format in PageFormat:
            action = QAction(page_format.label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=page_format: self._set_page_format(value)
            )
            self._page_format_group.addAction(action)
            self._page_format_actions[page_format] = action

        self._orientation_group = QActionGroup(self)
        self._orientation_group.setExclusive(True)
        self._orientation_actions: dict[Orientation, QAction] = {}
        for orientation in Orientation:
            action = QAction(orientation.label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=orientation: self._set_orientation(value)
            )
            self._orientation_group.addAction(action)
            self._orientation_actions[orientation] = action

        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        for key, label, shortcut in TOOL_DEFINITIONS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setIconText(TOOL_TOOLBAR_LABELS.get(key, label))
            action.triggered.connect(lambda _checked=False, tool_key=key: self._activate_tool(tool_key))
            self._tool_group.addAction(action)
            self._tool_actions[key] = action

        # Bindungsordnung direkt per Zifferntaste
        self._bond_order_actions: dict[int, QAction] = {}
        for label, order in BOND_ORDERS:
            action = QAction(f"{label}bindung ({order})", self)
            action.setShortcut(QKeySequence(str(order)))
            action.triggered.connect(lambda _checked=False, value=order: self._set_bond_order(value))
            self._bond_order_actions[order] = action

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Datei")
        file_menu.addAction(self._new_action)
        file_menu.addAction(self._open_action)
        file_menu.addSeparator()
        file_menu.addAction(self._save_action)
        file_menu.addAction(self._save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self._export_svg_action)
        file_menu.addAction(self._export_png_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

        edit_menu = self.menuBar().addMenu("&Bearbeiten")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._cut_action)
        edit_menu.addAction(self._copy_action)
        edit_menu.addAction(self._paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._delete_action)
        edit_menu.addAction(self._select_all_action)
        edit_menu.addAction(self._clear_selection_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._settings_action)

        view_menu = self.menuBar().addMenu("&Ansicht")
        view_menu.addAction(self._zoom_in_action)
        view_menu.addAction(self._zoom_out_action)
        view_menu.addAction(self._fit_action)
        view_menu.addAction(self._fit_width_action)

        page_menu = self.menuBar().addMenu("&Seite")
        format_menu = page_menu.addMenu("&Format")
        for page_format in PageFormat:
            format_menu.addAction(self._page_format_actions[page_format])
        page_menu.addSeparator()
        for orientation in Orientation:
            page_menu.addAction(self._orientation_actions[orientation])
        page_menu.addSeparator()
        page_menu.addAction(self._fit_action)
        page_menu.addAction(self._fit_width_action)

        tool_menu = self.menuBar().addMenu("&Werkzeuge")
        for key, _label, _shortcut in TOOL_DEFINITIONS:
            tool_menu.addAction(self._tool_actions[key])
        tool_menu.addSeparator()
        for _label, order in BOND_ORDERS:
            tool_menu.addAction(self._bond_order_actions[order])
        tool_menu.addSeparator()
        tool_menu.addAction(self._charge_action)
        tool_menu.addSeparator()
        tool_menu.addAction(self._stoich_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Werkzeuge", self)
        toolbar.setObjectName("toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for key, _label, _shortcut in TOOL_DEFINITIONS:
            toolbar.addAction(self._tool_actions[key])
        toolbar.addSeparator()

        self._element_combo = QComboBox(self)
        self._element_combo.addItems(ELEMENT_ORDER)
        self._element_combo.setToolTip("Element für das Atom-Werkzeug")
        self._element_combo.currentTextChanged.connect(self._on_element_changed)
        toolbar.addWidget(QLabel(" Element: ", self))
        toolbar.addWidget(self._element_combo)

        self._bond_combo = QComboBox(self)
        for label, order in BOND_ORDERS:
            self._bond_combo.addItem(label, order)
        self._bond_combo.setToolTip("Bindungsordnung für das Bindung-Werkzeug")
        self._bond_combo.currentIndexChanged.connect(self._on_bond_order_changed)
        toolbar.addWidget(QLabel("  Bindung: ", self))
        toolbar.addWidget(self._bond_combo)

        self._ring_combo = QComboBox(self)
        for template in RING_TEMPLATES:
            self._ring_combo.addItem(template.name, template)
        self._ring_combo.setToolTip("Ring-Template für das Ring-Werkzeug")
        self._ring_combo.currentIndexChanged.connect(self._on_ring_template_changed)
        toolbar.addWidget(QLabel("  Ring: ", self))
        toolbar.addWidget(self._ring_combo)

        self._arrow_combo = QComboBox(self)
        for kind in (
            ArrowKind.FORWARD,
            ArrowKind.EQUILIBRIUM,
            ArrowKind.PAIR_FLOW,
            ArrowKind.RADICAL_FLOW,
        ):
            self._arrow_combo.addItem(ARROW_LABELS[kind], kind)
        self._arrow_combo.setToolTip(
            "Pfeilart für das Pfeil-Werkzeug – „Paar“/„Radikal“ zeichnen "
            "gebogene Elektronenfluss-Pfeile für Reaktionsmechanismen"
        )
        self._arrow_combo.currentIndexChanged.connect(self._on_arrow_kind_changed)
        toolbar.addWidget(QLabel("  Pfeil: ", self))
        toolbar.addWidget(self._arrow_combo)

        toolbar.addSeparator()
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)

    def _create_color_toolbar(self) -> None:
        """Zweite Leiste mit der Farbpalette (färbt die aktuelle Auswahl)."""
        toolbar = QToolBar("Farbe", self)
        toolbar.setObjectName("color_toolbar")
        toolbar.setMovable(False)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(toolbar)

        self._color_palette = ColorPalette(self)
        self._color_palette.color_selected.connect(self._apply_color_to_selection)
        toolbar.addWidget(QLabel("Farbe: ", self))
        toolbar.addWidget(self._color_palette)
        toolbar.addSeparator()
        toolbar.addAction(self._stoich_action)
        toolbar.addWidget(
            QLabel(
                "  Objekte auswählen, dann Farbe anklicken – „Standard“ hebt die Farbe auf.",
                self,
            )
        )

    def _apply_color_to_selection(self, color: RGB | None) -> None:
        """Färbt die aktuelle Auswahl (oder erklärt, dass nichts ausgewählt ist)."""
        if not self._document.has_selection():
            self.statusBar().showMessage(
                "Zuerst Objekte auswählen, dann eine Farbe anklicken.", 2500
            )
            return
        count = self._document.set_selection_color(color, "Farbe ändern")
        if count:
            name = "Standard" if color is None else f"RGB{color}"
            self.statusBar().showMessage(f"Farbe: {name} ({count} Objekte)", 2000)

    # -- Ansatztabelle ---------------------------------------------------
    def _show_stoichiometry(self) -> None:
        """Erzeugt aus der Auswahl (oder dem ganzen Dokument) die Tabelle."""
        try:
            analysis = analyze_reaction(
                self._document.molecule,
                self._document.texts,
                self._document.arrows,
                selected_atoms=self._document.selection,
                selected_texts=self._document.text_selection,
                selected_arrows=self._document.arrow_selection,
            )
        except ReactionAnalysisError as exc:
            QMessageBox.information(self, "Ansatztabelle", str(exc))
            return
        table = table_from_analysis(analysis)
        if self._stoich_panel is None:
            self._stoich_panel = StoichiometryPanel(self)
            self.addDockWidget(
                Qt.DockWidgetArea.BottomDockWidgetArea, self._stoich_panel
            )
        self._stoich_panel.set_table(table)
        self._stoich_panel.show()
        self._stoich_panel.raise_()
        self.statusBar().showMessage(
            f"Ansatztabelle: {len(table.rows)} Substanzen", 3000
        )

    def _create_statusbar(self) -> None:
        self._hint_label = QLabel("", self)
        self._page_label = QLabel("", self)
        self._zoom_label = QLabel("Zoom: 100 %", self)
        self.statusBar().addWidget(self._hint_label, 1)
        self.statusBar().addPermanentWidget(self._page_label)
        self.statusBar().addPermanentWidget(self._zoom_label)

    # -- Werkzeuge -------------------------------------------------------
    def _activate_tool(self, key: str) -> None:
        tool = self._tools[key]
        self._canvas.set_tool(tool)
        action = self._tool_actions.get(key)
        if action is not None:
            action.setChecked(True)
        self._hint_label.setText(tool.hint)

    def _on_element_changed(self, symbol: str) -> None:
        atom_tool = self._tools["atom"]
        if isinstance(atom_tool, AtomTool):
            atom_tool.element = symbol

    def _on_bond_order_changed(self, index: int) -> None:
        bond_tool = self._tools["bond"]
        if isinstance(bond_tool, BondTool):
            bond_tool.bond_order = int(self._bond_combo.itemData(index) or 1)

    def _on_ring_template_changed(self, index: int) -> None:
        ring_tool = self._tools["ring"]
        template = self._ring_combo.itemData(index)
        if isinstance(ring_tool, RingTool) and template is not None:
            ring_tool.template = template

    def _on_arrow_kind_changed(self, index: int) -> None:
        arrow_tool = self._tools["arrow"]
        kind = self._arrow_combo.itemData(index)
        if isinstance(arrow_tool, ArrowTool) and kind is not None:
            arrow_tool.kind = kind

    def _set_bond_order(self, order: int) -> None:
        for position in range(self._bond_combo.count()):
            if self._bond_combo.itemData(position) == order:
                self._bond_combo.setCurrentIndex(position)
                break
        self._activate_tool("bond")
        self.statusBar().showMessage(f"Bindung: {order}-fach", 2000)

    def _on_text_requested(self, position, existing) -> None:  # noqa: ANN001
        """Das Text-Werkzeug meldet einen Klick – hier kommt der Dialog."""
        initial = existing.markup if existing is not None else ""
        markup = TextDialog.ask(self, initial)
        if markup is None:
            return
        if existing is not None:
            self._document.replace_text(existing, markup)
        else:
            self._document.add_text(position, markup)
        self.statusBar().showMessage("Text gesetzt", 2000)

    def _on_atom_label_requested(self, atom_id: int) -> None:
        """Klick auf ein Atom: Gruppenlabel direkt am Atom setzen."""
        atom = self._document.molecule.atom(atom_id)
        markup = TextDialog.ask(self, atom.label, title="Atomlabel")
        if markup is None:
            return
        self._document.set_atom_label(atom_id, markup)
        if markup.strip():
            self.statusBar().showMessage(f"Label '{markup}' gesetzt", 2000)
        else:
            self.statusBar().showMessage("Atomlabel entfernt", 2000)

    def _on_zoom_changed(self, level: float) -> None:
        self._zoom_label.setText(f"Zoom: {round(level * 100)} %")

    def _edit_selected_charge(self) -> None:
        """Ladung des ausgewählten Atoms eintippen (Menü „Werkzeuge“)."""
        atoms = sorted(self._document.selection)
        if len(atoms) != 1:
            self.statusBar().showMessage("Genau ein Atom auswählen", 2000)
            return
        atom_id = atoms[0]
        molecule = self._document.molecule
        atom = molecule.atom(atom_id)
        charge = ChargeDialog.ask(self, atom.charge, atom_label(molecule, atom_id))
        if charge is None or charge == atom.charge:
            return
        self._document.set_atom_charge(atom_id, charge, "Ladung eingeben")
        label = atom_label_full(molecule, atom_id)
        self.statusBar().showMessage(f"Ladung: {label}", 2000)

    # -- Einstellungen ---------------------------------------------------
    def _open_settings(self) -> None:
        style = SettingsDialog.ask(self, self._style)
        if style is None:
            return
        self._apply_style(style)
        self.statusBar().showMessage("Einstellungen übernommen", 2000)

    def _apply_style(self, style: Style) -> None:
        """Reicht einen geänderten Stil an Canvas und alle Werkzeuge weiter."""
        if style == self._style:
            return
        self._style = style
        for tool in self._tools.values():
            tool.set_style(style)
        self._canvas.set_style(style)

    # -- Seite -----------------------------------------------------------
    def _set_page_format(self, page_format: PageFormat) -> None:
        self._document.set_page_format(page_format)
        self.statusBar().showMessage(f"Seitenformat: {page_format.label}", 2000)

    def _set_orientation(self, orientation: Orientation) -> None:
        self._document.set_orientation(orientation)
        self.statusBar().showMessage(f"Ausrichtung: {orientation.label}", 2000)

    def _on_page_changed(self, _page: Page) -> None:
        self._sync_page_ui()
        self._canvas.fit_page_width()

    def _sync_page_ui(self) -> None:
        page = self._document.page
        for page_format, action in self._page_format_actions.items():
            action.setChecked(page_format is page.format)
        for orientation, action in self._orientation_actions.items():
            action.setChecked(orientation is page.orientation)
        self._page_label.setText(f"{page.format.label} · {page.orientation.label}")

    # -- Dateien ---------------------------------------------------------
    def _on_clean_changed(self, _clean: bool) -> None:
        """Undo-Stack wurde (un)gespeichert markiert: Titel aktualisieren."""
        self._update_title()

    def _document_is_modified(self) -> bool:
        """Liefert ``True``, wenn ungespeicherte Änderungen vorliegen.

        Beim Herunterfahren kann der ``QUndoStack`` bereits gelöscht sein; in
        diesem Fall wird ``False`` geliefert, statt eine ``RuntimeError``-Spur
        im Terminal zu erzeugen.
        """
        try:
            return self._document.is_modified()
        except RuntimeError:  # C++-Objekt bereits freigegeben
            return False

    def _update_title(self) -> None:
        name = self._path.name if self._path else "Unbenannt"
        marker = "*" if self._document_is_modified() else ""
        self.setWindowTitle(f"{name}{marker} – ValenceDraw")

    def _maybe_save(self) -> bool:
        if not self._document_is_modified():
            return True
        answer = QMessageBox.warning(
            self,
            "Ungespeicherte Änderungen",
            "Soll die aktuelle Struktur gespeichert werden?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._save_document()
        return answer == QMessageBox.StandardButton.Discard

    def _new_document(self) -> None:
        if not self._maybe_save():
            return
        self._document.replace_molecule(Molecule(), "Neu")
        self._document.undo_stack.clear()
        self._path = None
        self._canvas.fit_to_view()
        self._update_title()
        self.statusBar().showMessage("Neue Struktur", 2000)

    def _open_document(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Struktur öffnen",
            str(self._path.parent if self._path else Path.cwd()),
            "ValenceDraw-Projekt (*.valencedraw);;"
            "Chemie-Dateien (*.smi *.smiles *.mol *.sdf);;Alle Dateien (*)",
        )
        if not path:
            return
        file_path = Path(path)
        try:
            if file_path.suffix.lower() == PROJECT_SUFFIX:
                project = load_project(file_path)
                self._document.replace_content(
                    project.molecule,
                    project.texts,
                    project.arrows,
                    project.page,
                    text="Projekt öffnen",
                )
            else:
                molecule = load_molecule(file_path)
                self._document.replace_molecule(molecule, "Datei öffnen")
        except (ChemistryError, ProjectError, OSError) as exc:
            QMessageBox.critical(self, "Fehler beim Öffnen", str(exc))
            return
        self._document.undo_stack.clear()
        self._path = file_path
        self._canvas.fit_to_view()
        self._update_title()
        self.statusBar().showMessage(f"Geöffnet: {self._path.name}", 3000)

    def _save_document(self) -> bool:
        if self._path is None:
            return self._save_document_as()
        return self._write_to(self._path)

    def _save_document_as(self) -> bool:
        suggested = str(self._path) if self._path else f"struktur{PROJECT_SUFFIX}"
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Struktur speichern",
            suggested,
            "ValenceDraw-Projekt (*.valencedraw);;"
            "MDL Molfile (*.mol);;SDF (*.sdf);;SMILES (*.smi)",
        )
        if not path:
            return False
        file_path = Path(path)
        if not file_path.suffix:
            suffix = PROJECT_SUFFIX if "Projekt" in selected_filter else ".mol"
            file_path = file_path.with_suffix(suffix)
        self._path = file_path
        return self._write_to(file_path)

    def _write_to(self, path: Path) -> bool:
        is_project = path.suffix.lower() == PROJECT_SUFFIX
        if not is_project and not self._confirm_lossy_save(path.suffix):
            return False
        try:
            if is_project:
                save_project(self._project(), path)
            else:
                save_molecule(self._document.molecule, path)
        except (ChemistryError, ProjectError, OSError) as exc:
            QMessageBox.critical(self, "Fehler beim Speichern", str(exc))
            return False
        self._document.mark_saved()
        self._update_title()
        self.statusBar().showMessage(f"Gespeichert: {path.name}", 3000)
        return True

    def _project(self) -> Project:
        """Aktueller Dokumentinhalt als Projekt (für ``.valencedraw``)."""
        return Project(
            molecule=self._document.molecule.clone(),
            texts=self._document.texts,
            arrows=self._document.arrows,
            page=self._document.page,
        )

    def _confirm_lossy_save(self, suffix: str) -> bool:
        """Warnt, wenn das Zieldformat Texte, Pfeile, Labels oder δ nicht kennt."""
        molecule = self._document.molecule
        has_labels = any(
            molecule.atom(atom_id).label or molecule.atom(atom_id).partial_charge
            for atom_id in molecule.atom_ids()
        )
        has_colors = (
            any(molecule.atom(atom_id).color for atom_id in molecule.atom_ids())
            or any(bond.color for bond in molecule.bonds)
            or any(obj.color for obj in self._document.texts)
            or any(arrow.color for arrow in self._document.arrows)
        )
        if not (
            self._document.texts
            or self._document.arrows
            or has_labels
            or has_colors
        ):
            return True
        answer = QMessageBox.warning(
            self,
            "Nicht alles wird gespeichert",
            f"Das Format „{suffix}“ speichert nur Atome und Bindungen. "
            "Texte, Pfeile, Atomlabels, Teilladungen (δ⁺/δ⁻) und Farben "
            "gehen dabei verloren.\n\n"
            "Trotzdem speichern? (Für das komplette Dokument: .valencedraw)",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Save

    def _export_svg(self) -> None:
        """Exportiert die Zeichnung als SVG."""
        self._export_image(save_svg, "SVG", "struktur.svg", "SVG (*.svg)")

    def _export_png(self) -> None:
        """Exportiert die Zeichnung als PNG."""
        self._export_image(save_png, "PNG", "struktur.png", "PNG (*.png)")

    def _export_image(
        self,
        writer: Callable[..., Path],
        title: str,
        suggested: str,
        file_filter: str,
    ) -> None:
        """Gemeinsamer Ablauf für SVG- und PNG-Export."""
        path, _ = QFileDialog.getSaveFileName(
            self, f"Als {title} exportieren", suggested, file_filter
        )
        if not path:
            return
        try:
            writer(
                self._document.molecule,
                Path(path),
                style=self._style,
                texts=self._document.texts,
                arrows=self._document.arrows,
            )
        except OSError as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return
        self.statusBar().showMessage(f"{title} exportiert: {Path(path).name}", 3000)

    # -- Zwischenablage --------------------------------------------------
    PASTE_OFFSET = Point2D(20.0, 20.0)
    """Versatz je Einfügevorgang (2 mm), damit Kopien nicht aufeinander liegen."""

    def _copy_selection(self) -> None:
        fragment = self._document.copy_selection()
        if fragment.is_empty():
            self.statusBar().showMessage("Nichts ausgewählt", 2000)
            return
        self._paste_count = 0
        self._write_clipboard(fragment)
        self.statusBar().showMessage("Kopiert", 2000)

    def _cut_selection(self) -> None:
        fragment = self._document.copy_selection()
        if fragment.is_empty():
            self.statusBar().showMessage("Nichts ausgewählt", 2000)
            return
        self._paste_count = 0
        self._write_clipboard(fragment)
        self._document.delete_selection()
        self.statusBar().showMessage("Ausgeschnitten", 2000)

    def _paste(self) -> None:
        fragment = self._read_clipboard()
        if fragment is None or fragment.is_empty():
            self.statusBar().showMessage("Zwischenablage enthält keine Objekte", 2000)
            return
        self._paste_count += 1
        offset = self.PASTE_OFFSET * self._paste_count
        self._document.paste_fragment(fragment, offset)
        self.statusBar().showMessage("Eingefügt", 2000)

    def _write_clipboard(self, fragment: Fragment) -> None:
        """Legt das Fragment in die System-Zwischenablage."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - ohne GUI-Umgebung
            return
        data = QMimeData()
        data.setData(CLIPBOARD_MIME, fragment_to_json(fragment).encode("utf-8"))
        clipboard.setMimeData(data)

    def _read_clipboard(self) -> Fragment | None:
        """Liest ein Fragment aus der System-Zwischenablage (oder ``None``)."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - ohne GUI-Umgebung
            return None
        data = clipboard.mimeData()
        if data is None or not data.hasFormat(CLIPBOARD_MIME):
            return None
        try:
            return fragment_from_json(bytes(data.data(CLIPBOARD_MIME)).decode("utf-8"))
        except (ProjectError, UnicodeDecodeError):
            return None

    # -- Fenster ---------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._maybe_save():
            event.ignore()
            return
        self._disconnect_document()
        event.accept()

    def _disconnect_document(self) -> None:
        """Trennt die Dokument-Signale vor dem Beenden des Fensters.

        Sonst kann ``cleanChanged`` noch feuern, wenn die Qt-Objekte beim
        Herunterfahren schon gelöscht sind.
        """
        try:
            self._document.undo_stack.cleanChanged.disconnect(self._on_clean_changed)
        except (RuntimeError, TypeError):  # pragma: no cover - Shutdown
            pass
        try:
            self._document.page_changed.disconnect(self._on_page_changed)
        except (RuntimeError, TypeError):  # pragma: no cover - Shutdown
            pass
