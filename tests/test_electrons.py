"""Elektronenpaare (zwei Punkte) und Radikale (ein Punkt)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import (
    ELECTRON_HIT_ANGLE,
    MAX_LONE_PAIRS,
    MAX_RADICALS,
    Molecule,
)
from valencedraw.demo import ethane
from valencedraw.document.document import Document
from valencedraw.document.project import (
    Project,
    ProjectError,
    project_from_data,
    project_from_json,
    project_to_data,
    project_to_json,
)
from valencedraw.render.painter import (
    electron_anchor,
    electron_bounds,
    electron_dots,
    electron_preview,
    label_center,
    label_extent,
    label_half_size,
)
from valencedraw.render.style import DEFAULT_STYLE
from valencedraw.ui.tools import ElectronTool, EraseTool
from qt_helpers import move as _move
from qt_helpers import press as _press
from qt_helpers import release as _release


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


# -- Modell ---------------------------------------------------------------
def test_lone_pair_direction_is_normalized() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))

    molecule.add_lone_pair(atom_id, Point2D(30.0, 0.0))

    (direction,) = molecule.atom(atom_id).lone_pairs
    assert direction.length == pytest.approx(1.0)
    assert direction.x == pytest.approx(1.0)


def test_radical_is_stored_per_direction() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))

    molecule.add_radical(atom_id, Point2D(0.0, -1.0))

    assert molecule.atom(atom_id).radicals == (Point2D(0.0, -1.0),)
    assert molecule.atom(atom_id).lone_pairs == ()


def test_lone_pairs_are_limited() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    for index in range(MAX_LONE_PAIRS):
        molecule.add_lone_pair(atom_id, Point2D(1.0, float(index)))

    with pytest.raises(ValueError):
        molecule.add_lone_pair(atom_id, Point2D(0.0, 1.0))


def test_radicals_are_limited() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    for _ in range(MAX_RADICALS):
        molecule.add_radical(atom_id, Point2D(1.0, 0.0))

    with pytest.raises(ValueError):
        molecule.add_radical(atom_id, Point2D(0.0, 1.0))


def test_remove_electrons_by_index() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(0.0, 1.0))
    molecule.add_radical(atom_id, Point2D(-1.0, 0.0))

    molecule.remove_lone_pair(atom_id, 0)
    molecule.remove_radical(atom_id, 0)

    assert molecule.atom(atom_id).lone_pairs == (Point2D(0.0, 1.0),)
    assert molecule.atom(atom_id).radicals == ()


def test_electron_at_finds_the_matching_direction() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))
    molecule.add_radical(atom_id, Point2D(0.0, 1.0))

    assert molecule.electron_at(atom_id, Point2D(1.0, 0.2)) == ("pair", 0)
    assert molecule.electron_at(atom_id, Point2D(0.1, 1.0)) == ("radical", 0)
    assert molecule.electron_at(atom_id, Point2D(-1.0, 0.0)) is None


def test_electron_hit_angle_is_respected() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))

    inside = Point2D(1.0, 0.4)  # ~22°
    outside = Point2D(1.0, 1.0)  # 45°
    assert molecule.electron_at(atom_id, inside) is not None
    assert molecule.electron_at(atom_id, outside) is None
    assert molecule.electron_at(atom_id, outside, max_angle_deg=ELECTRON_HIT_ANGLE + 20) is not None


def test_reset_atom_clears_electrons() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0), charge=-1)
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))
    molecule.add_radical(atom_id, Point2D(0.0, 1.0))

    molecule.reset_atom(atom_id)

    atom = molecule.atom(atom_id)
    assert atom.lone_pairs == ()
    assert atom.radicals == ()


def test_clone_keeps_electrons() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))

    copy = molecule.clone()

    assert copy.atom(atom_id).lone_pairs == (Point2D(1.0, 0.0),)


def test_copy_and_paste_keep_electrons() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.toggle_electron(atom_id, Point2D(0.0, 1.0))
    document.toggle_electron(atom_id, Point2D(0.0, -1.0), radical=True)
    document.select_only(atom_id)

    fragment = document.copy_selection()
    assert document.paste_fragment(fragment) is True

    pasted = document.molecule.atom_ids()[-1]
    atom = document.molecule.atom(pasted)
    assert len(atom.lone_pairs) == 1
    assert len(atom.radicals) == 1


def test_eraser_clears_electrons_before_deleting() -> None:
    from valencedraw.ui.tools import EraseTool

    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.toggle_electron(atom_id, Point2D(0.0, 1.0))
    tool = EraseTool(document)

    tool.mouse_press(Point2D(BOND_LENGTH / 2, 0.0), _press())

    assert len(document.molecule) == 2
    assert document.molecule.atom(atom_id).lone_pairs == ()


# -- Document -------------------------------------------------------------
def test_toggle_electron_adds_and_removes() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]

    assert document.toggle_electron(atom_id, Point2D(0.0, 1.0)) is True
    assert len(document.molecule.atom(atom_id).lone_pairs) == 1

    assert document.toggle_electron(atom_id, Point2D(0.0, 1.0)) is True
    assert document.molecule.atom(atom_id).lone_pairs == ()
    assert document.undo_stack.count() == 2


def test_toggle_electron_respects_the_limit() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    for direction in (
        Point2D(1.0, 0.0),
        Point2D(0.0, 1.0),
        Point2D(-1.0, 0.0),
        Point2D(0.0, -1.0),
    ):
        assert document.toggle_electron(atom_id, direction) is True

    assert document.toggle_electron(atom_id, Point2D(1.0, 1.0)) is False
    assert len(document.molecule.atom(atom_id).lone_pairs) == MAX_LONE_PAIRS


def test_toggle_radical_removes_a_pair_first() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.toggle_electron(atom_id, Point2D(0.0, 1.0))

    # Ein Klick auf dasselbe Elektron entfernt es, egal welche Maustaste
    assert document.toggle_electron(atom_id, Point2D(0.1, 1.0), radical=True) is True

    assert document.molecule.atom(atom_id).lone_pairs == ()
    assert document.molecule.atom(atom_id).radicals == ()


def test_toggle_electron_is_undoable() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.toggle_electron(atom_id, Point2D(1.0, 0.0))

    document.undo_stack.undo()

    assert document.molecule.atom(atom_id).lone_pairs == ()


# -- Werkzeug -------------------------------------------------------------
def _click(tool, position, event=None) -> None:  # noqa: ANN001
    tool.mouse_press(position, event or _press())
    tool.mouse_release(position, _release())


def _assert_direction(actual: Point2D, expected: tuple[float, float]) -> None:
    """Richtung mit Toleranz vergleichen (``polar`` liefert kleine Reste)."""
    assert actual.x == pytest.approx(expected[0], abs=1e-6)
    assert actual.y == pytest.approx(expected[1], abs=1e-6)


def test_electron_tool_sets_a_pair_in_click_direction() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    _click(tool, position + Point2D(0.0, 18.0))

    (direction,) = document.molecule.atom(atom_id).lone_pairs
    _assert_direction(direction, (0.0, 1.0))


def test_electron_tool_second_click_removes() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    _click(tool, position + Point2D(0.0, 18.0))
    assert len(document.molecule.atom(atom_id).lone_pairs) == 1

    _click(tool, position + Point2D(0.0, 18.0))

    assert document.molecule.atom(atom_id).lone_pairs == ()


def test_electron_tool_right_click_sets_a_radical() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    _click(tool, position + Point2D(0.0, 18.0), _press(button=Qt.MouseButton.RightButton))

    assert len(document.molecule.atom(atom_id).radicals) == 1
    assert document.molecule.atom(atom_id).lone_pairs == ()


def test_electron_tool_ignores_far_clicks() -> None:
    document = Document(ethane())
    tool = ElectronTool(document)

    assert tool.mouse_press(Point2D(200.0, 150.0), _press()) is False
    assert document.undo_stack.count() == 0


def test_electron_tool_hover_marks_the_atom() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)

    tool._update_snap_hover(document.molecule.atom(atom_id).position + Point2D(15.0, 0.0))

    assert tool.snap_atom == atom_id


# -- Positionsauswahl (Gedrückthalten) ------------------------------------
def test_holding_the_button_shows_the_positions() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    tool.mouse_press(position + Point2D(0.0, 18.0), _press())
    assert tool.chooser_active is False  # erst nach kurzer Wartezeit

    tool._show_chooser()  # ersetzt den Timer

    assert tool.chooser_active is True
    assert len(tool.chooser_directions()) == ElectronTool.CHOOSER_STEPS
    _assert_direction(tool.chooser_direction, (0.0, 1.0))


def test_chooser_shows_nothing_before_the_delay() -> None:
    document = Document()
    tool = ElectronTool(document)

    assert tool.chooser_active is False
    assert tool.mouse_release(Point2D(), _release()) is False


def test_release_in_the_chooser_uses_the_selected_position() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    tool.mouse_press(position + Point2D(0.0, 18.0), _press())
    tool._show_chooser()
    tool.mouse_move(position + Point2D(-18.0, 0.0), _move())
    tool.mouse_release(position + Point2D(-18.0, 0.0), _release())

    (direction,) = document.molecule.atom(atom_id).lone_pairs
    _assert_direction(direction, (-1.0, 0.0))
    assert tool.chooser_active is False


def test_chooser_keeps_radicals_single() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    tool.mouse_press(position + Point2D(0.0, 18.0), _press(button=Qt.MouseButton.RightButton))
    tool._show_chooser()
    tool.mouse_move(position + Point2D(18.0, 0.0), _move())
    tool.mouse_release(position + Point2D(18.0, 0.0), _release())

    atom = document.molecule.atom(atom_id)
    assert atom.lone_pairs == ()
    _assert_direction(atom.radicals[0], (1.0, 0.0))


def test_deactivate_cancels_the_chooser() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    tool.mouse_press(document.molecule.atom(atom_id).position + Point2D(0.0, 18.0), _press())
    tool._show_chooser()

    tool.deactivate()

    assert tool.chooser_active is False


def test_quick_click_still_uses_the_click_direction() -> None:
    """Ohne Halten darf die Auswahl nicht dazwischenfunken."""
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    tool = ElectronTool(document)
    position = document.molecule.atom(atom_id).position

    tool.mouse_press(position + Point2D(-18.0, 0.0), _press())
    tool.mouse_release(position + Point2D(-18.0, 0.0), _release())

    (direction,) = document.molecule.atom(atom_id).lone_pairs
    assert direction.x == pytest.approx(-1.0)


# -- Radierer -------------------------------------------------------------
def test_eraser_removes_a_lone_pair_only() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[1]
    document.molecule.set_element(atom_id, "O")
    document.toggle_electron(atom_id, Point2D(0.0, -1.0))
    tool = EraseTool(document)
    (dot, _other) = electron_dots(document.molecule, atom_id)

    tool.mouse_press(dot, _press())

    atom = document.molecule.atom(atom_id)
    assert atom.lone_pairs == ()
    assert atom.element == "O"          # Atom bleibt erhalten
    assert len(document.molecule) == 2


def test_eraser_removes_a_radical_only() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    document.molecule.add_radical(atom_id, Point2D(0.0, -1.0))
    tool = EraseTool(document)
    (dot,) = electron_dots(document.molecule, atom_id)

    tool.mouse_press(dot, _press())

    assert document.molecule.atom(atom_id).radicals == ()
    assert len(document.molecule) == 2


def test_eraser_hover_marks_electrons() -> None:
    document = Document(ethane())
    atom_id = document.molecule.atom_ids()[0]
    document.molecule.add_lone_pair(atom_id, Point2D(0.0, -1.0))
    tool = EraseTool(document)
    (dot, _other) = electron_dots(document.molecule, atom_id)

    tool._update_hover(dot)

    assert tool._hover_electron == (atom_id, "pair", 0)
    assert tool._hover_atom is None


# -- Gebundene Atome (Label sitzt versetzt) -------------------------------
def _bonded_terminal_oxygen() -> tuple[Molecule, int]:
    """C–O mit endständigem O (Label sitzt außerhalb des Bindungsendes)."""
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(carbon, oxygen)
    return molecule, oxygen


def test_electron_anchor_is_the_offset_label() -> None:
    molecule, atom_id = _bonded_terminal_oxygen()

    anchor = electron_anchor(molecule, atom_id)

    assert anchor.x > molecule.atom(atom_id).position.x


def test_dots_keep_the_same_distance_on_both_sides_of_a_bond() -> None:
    """Vorher kollabierte der Abstand auf der Bindungsseite (verzerrte Anordnung)."""
    molecule, atom_id = _bonded_terminal_oxygen()
    anchor = electron_anchor(molecule, atom_id)

    outward = electron_preview(molecule, atom_id, Point2D(1.0, 0.0))[0]
    inward = electron_preview(molecule, atom_id, Point2D(-1.0, 0.0))[0]

    assert (outward - anchor).length == pytest.approx((inward - anchor).length)


def test_dots_of_a_bonded_atom_stay_outside_the_label() -> None:
    molecule, atom_id = _bonded_terminal_oxygen()
    half_width, half_height = label_half_size(molecule, atom_id)
    center = label_center(molecule, atom_id)

    for direction in (Point2D(1.0, 0.0), Point2D(-1.0, 0.0), Point2D(0.0, 1.0)):
        for dot in electron_preview(molecule, atom_id, direction):
            outside = (
                abs(dot.x - center.x) >= half_width
                or abs(dot.y - center.y) >= half_height
            )
            assert outside, f"{dot} liegt im Label von {center}"


def test_chooser_directions_follow_the_label_centre() -> None:
    """Die markierte Richtung richtet sich nach dem Label, nicht nach dem Atom."""
    document = Document(_bonded_terminal_oxygen()[0])
    atom_id = document.molecule.atom_ids()[1]
    tool = ElectronTool(document)
    anchor = electron_anchor(document.molecule, atom_id)

    tool.mouse_press(anchor + Point2D(0.0, 20.0), _press())
    tool._show_chooser()

    _assert_direction(tool.chooser_direction, (0.0, 1.0))


# -- Darstellung ----------------------------------------------------------
def test_pair_is_drawn_as_two_separate_dots() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(0.0, -1.0))

    dots = electron_dots(molecule, atom_id)

    assert len(dots) == 2
    first, second = dots
    assert first.y == pytest.approx(second.y)
    assert first.x == pytest.approx(-second.x)
    assert second.x - first.x == pytest.approx(DEFAULT_STYLE.electron_pair_gap)


def test_radical_is_drawn_as_one_dot() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    molecule.add_radical(atom_id, Point2D(1.0, 0.0))

    dots = electron_dots(molecule, atom_id)

    assert len(dots) == 1
    assert dots[0].x > 0.0


def test_dots_sit_outside_the_atom_label() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))
    direction = Point2D(1.0, 0.0)

    dots = electron_dots(molecule, atom_id)

    reach = label_extent(molecule, atom_id, direction) + DEFAULT_STYLE.electron_gap
    assert min(dot.x for dot in dots) > reach


def test_electron_bounds_cover_the_dots() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(0.0, 1.0))

    bounds = electron_bounds(molecule)

    assert bounds is not None
    assert bounds.bottom() > 0.0


def test_no_electrons_no_bounds() -> None:
    molecule = Molecule()
    molecule.add_atom("O", Point2D(0.0, 0.0))
    assert electron_bounds(molecule) is None


# -- Projektdatei ---------------------------------------------------------
def test_project_round_trips_electrons() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(10.0, 20.0), charge=-1)
    molecule.add_lone_pair(atom_id, Point2D(1.0, 0.0))
    molecule.add_lone_pair(atom_id, Point2D(0.0, 1.0))
    molecule.add_radical(atom_id, Point2D(-1.0, 0.0))
    project = Project(molecule=molecule)

    loaded = project_from_json(project_to_json(project))

    atom = loaded.molecule.atom(atom_id)
    assert len(atom.lone_pairs) == 2
    assert len(atom.radicals) == 1
    assert atom.lone_pairs[0] == Point2D(1.0, 0.0)


def test_project_without_electron_fields_still_loads() -> None:
    molecule = Molecule()
    molecule.add_atom("C", Point2D(0.0, 0.0))
    data = project_to_data(Project(molecule=molecule))

    for atom in data["molecule"]["atoms"]:
        atom.pop("pairs")
        atom.pop("radicals")

    loaded = project_from_data(data)

    assert loaded.molecule.atom(0).lone_pairs == ()


def test_broken_electron_data_is_reported() -> None:
    molecule = Molecule()
    molecule.add_atom("C", Point2D(0.0, 0.0))
    data = project_to_data(Project(molecule=molecule))
    data["molecule"]["atoms"][0]["pairs"] = "kaputt"

    assert project_from_data(data).molecule.atom(0).lone_pairs == ()

    data["molecule"]["atoms"][0]["pairs"] = [["keine Zahl", 0.0]]
    with pytest.raises(ProjectError):
        project_from_data(data)


# -- Rendering ------------------------------------------------------------
def test_electrons_are_painted() -> None:
    from PySide6.QtGui import QImage, QPainter

    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(carbon, oxygen)
    molecule.add_lone_pair(oxygen, Point2D(1.0, 0.0))

    image = QImage(200, 120, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.translate(20.0, 60.0)
    from valencedraw.render.painter import paint_scene

    paint_scene(painter, molecule, ())
    painter.end()

    dark = sum(
        1
        for x in range(0, image.width())
        for y in range(0, image.height())
        if image.pixelColor(x, y).lightness() < 120
    )
    assert dark > 0
