from __future__ import annotations

import pytest
import shiboken6
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox

from valencedraw.core.annotations import ArrowKind, TextObject
from valencedraw.core.geometry import Point2D
from valencedraw.core.page import Orientation, PageFormat
from valencedraw.demo import ethane
from valencedraw.document.document import Document
from valencedraw.document.project import Project, load_project, save_project
from valencedraw.ui.charge_dialog import ChargeDialog
from valencedraw.ui.main_window import MainWindow
from valencedraw.ui.text_dialog import TextDialog


@pytest.fixture
def window(qapp):  # noqa: ANN001
    main_window = MainWindow(Document(ethane()))
    yield main_window
    # Ohne "gespeichert" fragt close() modal nach dem Speichern -> Test hängt.
    main_window.document.mark_saved()
    main_window.close()


@pytest.fixture(autouse=True)
def _clear_clipboard(qapp):  # noqa: ANN001
    """Jeder Test startet mit leerer Zwischenablage."""
    QGuiApplication.clipboard().clear()
    yield


def test_window_starts_with_expected_tools(window) -> None:  # noqa: ANN001
    names = {tool.name for tool in window._tools.values()}
    assert {
        "Auswahl",
        "Bindung",
        "Atom",
        "Ladung",
        "Elektronen",
        "Ring",
        "Text",
        "Pfeil",
        "Radierer",
        "Keil",
        "Strichkeil",
        "Teilladung",
    } <= names


def test_electron_tool_can_be_activated(window) -> None:  # noqa: ANN001
    window._activate_tool("electron")

    assert window.canvas.tool is window._tools["electron"]
    assert "Elektronenpaar" in window._hint_label.text()


def test_wedge_tools_can_be_activated(window) -> None:  # noqa: ANN001
    window._activate_tool("wedge")
    assert window.canvas.tool is window._tools["wedge"]
    assert "Keil" in window._hint_label.text()

    window._activate_tool("hashed")
    assert window.canvas.tool is window._tools["hashed"]
    assert "Strichkeil" in window._hint_label.text()


def test_partial_charge_tool_can_be_activated(window) -> None:  # noqa: ANN001
    window._activate_tool("partial")

    assert window.canvas.tool is window._tools["partial"]
    assert "Teilladung" in window._hint_label.text()
    # In der Toolbar steht nur das kurze δ, im Menü der volle Name.
    assert window._tool_actions["partial"].iconText() == "\u03b4"
    assert window._tool_actions["partial"].text() == "Teilladung"


def test_charge_tool_can_be_activated(window) -> None:  # noqa: ANN001
    window._activate_tool("charge")

    assert window.canvas.tool is window._tools["charge"]
    assert "Ladung" in window._hint_label.text()


def test_charge_menu_action_edits_the_selected_atom(window, monkeypatch) -> None:  # noqa: ANN001
    atom_id = window.document.molecule.atom_ids()[0]
    window.document.select_only(atom_id)
    monkeypatch.setattr(
        ChargeDialog, "ask", classmethod(lambda _cls, _parent, charge=0, symbol="": 6)
    )

    window._edit_selected_charge()

    assert window.document.molecule.atom(atom_id).charge == 6


def test_charge_menu_action_needs_exactly_one_atom(window, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        ChargeDialog, "ask", classmethod(lambda _cls, _parent, charge=0, symbol="": 6)
    )
    window.document.select_all()

    window._edit_selected_charge()

    assert all(atom.charge == 0 for atom in window.document.molecule.atoms.values())


def test_default_window_starts_with_empty_document(qapp) -> None:  # noqa: ANN001
    main_window = MainWindow()
    try:
        assert len(main_window.document.molecule) == 0
        assert main_window.document.texts == ()
    finally:
        main_window.document.mark_saved()
        main_window.close()


def test_text_request_creates_text_object(window, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        TextDialog, "ask", classmethod(lambda cls, parent, markup="": "H_2O")
    )

    window._on_text_requested(Point2D(10.0, 20.0), None)

    assert len(window.document.texts) == 1
    assert window.document.texts[0].markup == "H_2O"


def test_text_request_edits_existing_object(window, monkeypatch) -> None:  # noqa: ANN001
    existing = window.document.add_text(Point2D(0.0, 0.0), "alt")
    monkeypatch.setattr(
        TextDialog, "ask", classmethod(lambda cls, parent, markup="": "Fe^{3+}")
    )

    window._on_text_requested(Point2D(0.0, 0.0), existing)

    assert window.document.texts[0].markup == "Fe^{3+}"
    assert window.document.texts[0].position == existing.position


def test_cancelled_text_dialog_changes_nothing(window, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(TextDialog, "ask", classmethod(lambda cls, parent, markup="": None))

    window._on_text_requested(Point2D(0.0, 0.0), None)

    assert window.document.texts == ()


def test_atom_label_dialog_sets_label(window, monkeypatch) -> None:  # noqa: ANN001
    atom_id = window.document.molecule.atom_ids()[0]
    monkeypatch.setattr(
        TextDialog,
        "ask",
        classmethod(lambda cls, parent, markup="", title="Text": "NO2"),
    )

    window._on_atom_label_requested(atom_id)

    assert window.document.molecule.atom_label(atom_id) == "NO2"
    assert window.document.undo_stack.count() == 1


def test_atom_label_dialog_can_remove_label(window, monkeypatch) -> None:  # noqa: ANN001
    atom_id = window.document.molecule.atom_ids()[0]
    window.document.set_atom_label(atom_id, "NO2")
    monkeypatch.setattr(
        TextDialog,
        "ask",
        classmethod(lambda cls, parent, markup="", title="Text": ""),
    )

    window._on_atom_label_requested(atom_id)

    assert window.document.molecule.atom_label(atom_id) == ""


def test_cancelled_atom_label_dialog_changes_nothing(window, monkeypatch) -> None:  # noqa: ANN001
    atom_id = window.document.molecule.atom_ids()[0]
    monkeypatch.setattr(
        TextDialog,
        "ask",
        classmethod(lambda cls, parent, markup="", title="Text": None),
    )

    window._on_atom_label_requested(atom_id)

    assert window.document.molecule.atom_label(atom_id) == ""
    assert window.document.undo_stack.count() == 0


def test_bond_order_shortcut_updates_tool(window) -> None:  # noqa: ANN001
    window._set_bond_order(3)

    bond_tool = window._tools["bond"]
    assert bond_tool.bond_order == 3
    assert window.canvas.tool is bond_tool


# -- Seite ---------------------------------------------------------------
def test_page_format_action_updates_document(window) -> None:  # noqa: ANN001
    window._page_format_actions[PageFormat.LETTER].trigger()

    assert window.document.page.format is PageFormat.LETTER
    assert window._page_format_actions[PageFormat.LETTER].isChecked()
    assert "Letter" in window._page_label.text()


def test_orientation_action_updates_document(window) -> None:  # noqa: ANN001
    window._orientation_actions[Orientation.LANDSCAPE].trigger()

    assert window.document.page.orientation is Orientation.LANDSCAPE
    assert window._orientation_actions[Orientation.LANDSCAPE].isChecked()
    assert "Querformat" in window._page_label.text()
    assert window.canvas.page_rect().width() > window.canvas.page_rect().height()


def test_page_ui_lists_every_format(window) -> None:  # noqa: ANN001
    assert set(window._page_format_actions) == set(PageFormat)
    assert set(window._orientation_actions) == set(Orientation)


# -- Pfeile --------------------------------------------------------------
def test_arrow_selector_offers_reactions_and_electron_flow(window) -> None:  # noqa: ANN001
    kinds = [
        window._arrow_combo.itemData(index)
        for index in range(window._arrow_combo.count())
    ]
    assert kinds == [
        ArrowKind.FORWARD,
        ArrowKind.EQUILIBRIUM,
        ArrowKind.PAIR_FLOW,
        ArrowKind.RADICAL_FLOW,
    ]


# -- Zwischenablage ------------------------------------------------------
def test_copy_and_paste_through_the_clipboard(window) -> None:  # noqa: ANN001
    window.document.select_all()
    window._copy_selection()

    window._paste()

    assert len(window.document.molecule) == 4
    assert len(window.document.molecule.bonds) == 2
    # Die Kopie ist ausgewählt und liegt versetzt über dem Original.
    assert window.document.selection == frozenset({2, 3})


def test_cut_removes_selection_and_paste_restores_it(window) -> None:  # noqa: ANN001
    window.document.select_all()
    window._cut_selection()

    assert len(window.document.molecule) == 0

    window._paste()

    assert len(window.document.molecule) == 2


def test_paste_without_clipboard_content_does_nothing(window) -> None:  # noqa: ANN001
    QGuiApplication.clipboard().clear()

    window._paste()

    assert len(window.document.molecule) == 2


# -- Speichern / Öffnen --------------------------------------------------
def test_project_save_keeps_texts_and_arrows(window, tmp_path) -> None:  # noqa: ANN001
    window.document.add_text(Point2D(10.0, 20.0), "Ph")
    window.document.add_arrow(Point2D(0.0, 60.0), Point2D(80.0, 60.0))
    path = tmp_path / "projekt.valencedraw"

    assert window._write_to(path)

    loaded = load_project(path)
    assert [obj.markup for obj in loaded.texts] == ["Ph"]
    assert len(loaded.arrows) == 1


def test_open_project_restores_texts(window, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    project = Project(
        molecule=ethane(),
        texts=(TextObject(Point2D(5.0, 5.0), "Hallo"),),
    )
    path = save_project(project, tmp_path / "projekt.valencedraw")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(path), ""))
    )

    window._open_document()

    assert [obj.markup for obj in window.document.texts] == ["Hallo"]
    assert len(window.document.molecule) == 2
    assert window._path == path


def test_saving_chemistry_format_warns_about_lost_objects(
    window, monkeypatch, tmp_path
) -> None:  # noqa: ANN001
    window.document.add_text(Point2D(10.0, 20.0), "Ph")
    warnings: list[str] = []

    def _warning(_parent, _title, message, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        warnings.append(message)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))
    path = tmp_path / "struktur.mol"

    assert window._write_to(path) is False
    assert warnings
    assert not path.exists()


def test_saving_chemistry_format_without_objects_does_not_warn(
    window, monkeypatch, tmp_path
) -> None:  # noqa: ANN001
    calls: list[object] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: calls.append(args)),  # noqa: ANN002, ANN003
    )
    path = tmp_path / "struktur.mol"

    assert window._write_to(path) is True
    assert calls == []


def test_title_ignores_already_deleted_undo_stack(qapp) -> None:  # noqa: ANN001
    """Beim Herunterfahren kann der QUndoStack schon weg sein (kein Traceback)."""
    main_window = MainWindow(Document(ethane()))

    shiboken6.delete(main_window.document.undo_stack)

    main_window._on_clean_changed(False)  # darf nicht werfen
    main_window._update_title()
    assert main_window.windowTitle() == "Unbenannt – ValenceDraw"
    assert main_window._maybe_save() is True

    main_window.close()  # trennt die Signale ohne Fehler

