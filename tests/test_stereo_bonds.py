from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from valencedraw.core.geometry import BOND_LENGTH, Point2D
from valencedraw.core.molecule import BondStereo, Molecule
from valencedraw.document.document import Document
from valencedraw.document.io import (
    RDKIT_AVAILABLE,
    molecule_from_molblock,
    molecule_to_rdkit,
)
from valencedraw.document.project import Project, project_from_data, project_to_data
from valencedraw.render.painter import (
    bond_segments,
    hashed_wedge_lines,
    paint_molecule,
    stereo_bond_ends,
    stereo_bond_hatches,
    stereo_bond_triangle,
    to_qpoint,
    wedge_triangle,
)
from valencedraw.render.style import DEFAULT_STYLE
from valencedraw.ui.tools import HashedBondTool, WedgeBondTool
from qt_helpers import move as _move
from qt_helpers import press as _press
from qt_helpers import release as _release


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _chain(stereo: BondStereo = BondStereo.NONE, narrow: str = "a") -> Molecule:
    """Zwei Atome mit einer Bindung (Atom 0 links, Atom 1 rechts)."""
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    right = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(
        left,
        right,
        1,
        0,
        False,
        stereo,
        left if narrow == "a" else right,
    )
    return molecule


# -- Modell --------------------------------------------------------------
def test_bond_stores_stereo_and_direction() -> None:
    molecule = _chain(BondStereo.WEDGE, narrow="b")
    bond = molecule.bonds[0]

    assert bond.stereo is BondStereo.WEDGE
    assert bond.narrow_atom == bond.b
    assert bond.wide_atom == bond.a


def test_stereo_is_only_kept_on_single_bonds() -> None:
    molecule = Molecule()
    a = molecule.add_atom()
    b = molecule.add_atom()
    bond = molecule.add_bond(a, b, order=2, stereo=BondStereo.WEDGE, stereo_from=a)

    assert bond.stereo is BondStereo.NONE
    assert bond.stereo_from is None


def test_set_bond_stereo_forces_a_single_bond() -> None:
    molecule = Molecule()
    a = molecule.add_atom()
    b = molecule.add_atom()
    molecule.add_bond(a, b, order=2)
    bond = molecule.bonds[0]

    molecule.set_bond_stereo(bond, BondStereo.HASHED, b)

    updated = molecule.bonds[0]
    assert updated.order == 1
    assert updated.stereo is BondStereo.HASHED
    assert updated.narrow_atom == b


def test_set_bond_order_drops_stereo() -> None:
    molecule = _chain(BondStereo.WEDGE)
    bond = molecule.bonds[0]

    molecule.set_bond_order(bond, 2)

    assert molecule.bonds[0].stereo is BondStereo.NONE
    assert molecule.bonds[0].stereo_from is None


def test_removing_stereo_turns_the_bond_back_into_a_line() -> None:
    molecule = _chain(BondStereo.WEDGE)
    bond = molecule.bonds[0]

    molecule.set_bond_stereo(bond, BondStereo.NONE)

    assert molecule.bonds[0].stereo is BondStereo.NONE
    assert bond_segments(molecule, molecule.bonds[0]) == [
        (Point2D(0.0, 0.0), Point2D(BOND_LENGTH, 0.0))
    ]


# -- Dokument ------------------------------------------------------------
def test_document_sets_stereo_in_one_undo_step() -> None:
    document = Document(_chain())
    bond = document.molecule.bonds[0]

    document.set_bond_stereo(bond, BondStereo.WEDGE)
    assert document.undo_stack.count() == 1
    assert document.molecule.bonds[0].stereo is BondStereo.WEDGE

    document.undo_stack.undo()
    assert document.molecule.bonds[0].stereo is BondStereo.NONE


def test_document_flips_the_wedge_direction() -> None:
    document = Document(_chain(BondStereo.WEDGE))
    bond = document.molecule.bonds[0]
    assert bond.narrow_atom == bond.a

    document.flip_bond_stereo(bond)

    flipped = document.molecule.bonds[0]
    assert flipped.narrow_atom == flipped.b
    assert document.undo_stack.count() == 1


def test_flip_without_stereo_does_nothing() -> None:
    document = Document(_chain())

    document.flip_bond_stereo(document.molecule.bonds[0])

    assert document.undo_stack.count() == 0


# -- Renderer ------------------------------------------------------------
def test_wedge_narrows_towards_its_start_atom() -> None:
    molecule = _chain(BondStereo.WEDGE, narrow="a")
    ends = stereo_bond_ends(molecule, molecule.bonds[0])

    assert ends is not None
    narrow, wide = ends
    assert narrow == Point2D(0.0, 0.0)
    assert wide == Point2D(BOND_LENGTH, 0.0)


def test_wedge_follows_the_flipped_direction() -> None:
    molecule = _chain(BondStereo.WEDGE, narrow="b")
    ends = stereo_bond_ends(molecule, molecule.bonds[0])

    assert ends is not None
    assert ends[0] == Point2D(BOND_LENGTH, 0.0)
    assert ends[1] == Point2D(0.0, 0.0)


def test_wedge_triangle_is_as_wide_as_the_style_says() -> None:
    triangle = wedge_triangle(
        Point2D(0.0, 0.0), Point2D(BOND_LENGTH, 0.0), DEFAULT_STYLE.wedge_width
    )

    assert triangle.count() == 3
    assert triangle.at(0) == to_qpoint(Point2D(0.0, 0.0))
    width = triangle.at(1).y() - triangle.at(2).y()
    assert width == pytest.approx(DEFAULT_STYLE.wedge_width)


def test_hashed_wedge_grows_towards_the_wide_end() -> None:
    lines = hashed_wedge_lines(
        Point2D(0.0, 0.0),
        Point2D(BOND_LENGTH, 0.0),
        DEFAULT_STYLE.wedge_width,
        DEFAULT_STYLE.wedge_hatch_spacing,
    )

    assert len(lines) >= 3
    widths = [start.distance_to(end) for start, end in lines]
    assert widths == sorted(widths)
    assert widths[-1] == pytest.approx(DEFAULT_STYLE.wedge_width, rel=0.15)


def test_stereo_helpers_ignore_plain_bonds() -> None:
    molecule = _chain()

    assert stereo_bond_ends(molecule, molecule.bonds[0]) is None
    assert stereo_bond_triangle(molecule, molecule.bonds[0]) is None
    assert stereo_bond_hatches(molecule, molecule.bonds[0]) == []


def _ink(image: QImage) -> int:
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y) != QColor("white")
    )


def test_wedge_is_filled_and_hashed_wedge_is_dashed() -> None:
    counts = {}
    for stereo in (BondStereo.NONE, BondStereo.WEDGE, BondStereo.HASHED):
        image = QImage(320, 200, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.translate(20.0, 100.0)
        paint_molecule(painter, _chain(stereo))
        painter.end()
        counts[stereo] = _ink(image)

    assert counts[BondStereo.WEDGE] > counts[BondStereo.NONE]
    assert counts[BondStereo.HASHED] > counts[BondStereo.NONE]


# -- Projektdatei / Zwischenablage --------------------------------------
def test_project_data_keeps_stereo() -> None:
    molecule = _chain(BondStereo.HASHED, narrow="b")
    project = Project(molecule)

    data = project_to_data(project)
    restored = project_from_data(data).molecule

    bond = restored.bonds[0]
    assert bond.stereo is BondStereo.HASHED
    assert bond.narrow_atom == bond.b


def test_unknown_stereo_value_becomes_a_line() -> None:
    molecule = _chain(BondStereo.WEDGE)
    data = project_to_data(Project(molecule))
    data["molecule"]["bonds"][0]["stereo"] = "gibt-es-nicht"

    restored = project_from_data(data).molecule

    assert restored.bonds[0].stereo is BondStereo.NONE


@pytest.mark.skipif(not RDKIT_AVAILABLE, reason="RDKit ist nicht installiert")
def test_molfile_roundtrip_keeps_the_wedge_direction() -> None:
    from rdkit import Chem

    molecule = _chain(BondStereo.WEDGE, narrow="b")

    block = Chem.MolToMolBlock(molecule_to_rdkit(molecule))
    restored = molecule_from_molblock(block)

    bond = restored.bonds[0]
    assert bond.stereo is BondStereo.WEDGE
    assert bond.narrow_atom == bond.b


# -- Werkzeuge -----------------------------------------------------------
def _drag(tool, start: Point2D, end: Point2D) -> None:  # noqa: ANN001
    assert tool.mouse_press(start, _press())
    tool.mouse_move(end, _move())
    tool.mouse_release(end, _release())


def test_wedge_tool_draws_a_wedge_from_the_start_atom() -> None:
    document = Document()
    tool = WedgeBondTool(document)

    _drag(tool, Point2D(0.0, 0.0), Point2D(BOND_LENGTH, 0.0))

    assert len(document.molecule) == 2
    bond = document.molecule.bonds[0]
    assert bond.stereo is BondStereo.WEDGE
    assert bond.narrow_atom == bond.a
    assert document.undo_stack.count() == 1


def test_hashed_tool_draws_hashed_bonds() -> None:
    document = Document()
    tool = HashedBondTool(document)

    _drag(tool, Point2D(0.0, 0.0), Point2D(BOND_LENGTH, 0.0))

    assert document.molecule.bonds[0].stereo is BondStereo.HASHED


def test_click_converts_an_existing_bond_and_clicking_again_removes_it() -> None:
    document = Document(_chain())
    tool = WedgeBondTool(document)
    middle = Point2D(BOND_LENGTH / 2.0, 0.0)

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].stereo is BondStereo.WEDGE

    tool.mouse_press(middle, _press())
    tool.mouse_release(middle, _release())
    assert document.molecule.bonds[0].stereo is BondStereo.NONE


def test_right_click_mirrors_the_wedge() -> None:
    document = Document(_chain(BondStereo.WEDGE))
    tool = WedgeBondTool(document)
    middle = Point2D(BOND_LENGTH / 2.0, 0.0)

    assert tool.mouse_press(middle, _press(button=Qt.MouseButton.RightButton))

    bond = document.molecule.bonds[0]
    assert bond.narrow_atom == bond.b


def test_click_on_an_atom_appends_a_wedge_bond() -> None:
    document = Document(_chain())
    tool = WedgeBondTool(document)
    atom_id = document.molecule.atom_ids()[1]

    tool.mouse_press(document.molecule.atom(atom_id).position, _press())
    tool.mouse_release(document.molecule.atom(atom_id).position, _release())

    wedges = [bond for bond in document.molecule.bonds if bond.stereo is BondStereo.WEDGE]
    assert len(wedges) == 1
    assert wedges[0].narrow_atom == atom_id
