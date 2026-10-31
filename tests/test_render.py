from __future__ import annotations

import math

import pytest
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter

from valencedraw.core.geometry import BOND_LENGTH, Point2D, polar
from valencedraw.core.molecule import Molecule, charge_text
from valencedraw.demo import benzene, ethane, ethanol
from valencedraw.render.export import render_image, save_png, save_svg
from valencedraw.render.painter import (
    atom_label,
    atom_label_full,
    atom_label_markup,
    bond_end_inset,
    bond_segments,
    charge_direction,
    charge_rect,
    charge_rect_at,
    label_center,
    label_extent,
    label_half_size,
    label_rect,
    paint_hover_atom,
)
from valencedraw.render.style import DEFAULT_STYLE


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def test_carbon_is_unlabelled() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    assert atom_label(molecule, atom_id) == ""


def test_heteroatom_is_labelled() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("O", Point2D(0.0, 0.0))
    assert atom_label(molecule, atom_id) == "O"


def test_charges_are_shown() -> None:
    molecule = Molecule()
    positive = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)
    negative = molecule.add_atom("O", Point2D(50.0, 0.0), charge=-1)
    assert atom_label_full(molecule, positive) == "N+"
    assert atom_label_full(molecule, negative) == "O\u2212"


def test_charge_text() -> None:
    assert charge_text(0) == ""
    assert charge_text(1) == "+"
    assert charge_text(2) == "2+"
    assert charge_text(-1) == "\u2212"
    assert charge_text(-7) == "7\u2212"


def test_charge_is_not_part_of_the_atom_label() -> None:
    """Das Elementlabel bleibt unverändert – die Ladung steht separat daneben."""
    molecule = Molecule()
    neutral = molecule.add_atom("N", Point2D(0.0, 0.0))
    charged = molecule.add_atom("N", Point2D(50.0, 0.0), charge=2)

    assert atom_label(molecule, neutral) == "N"
    assert atom_label(molecule, charged) == "N"
    assert atom_label_markup(molecule, charged) == "N"
    assert atom_label_full(molecule, charged) == "N2+"


def test_charged_carbon_becomes_visible() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    assert atom_label_markup(molecule, atom_id) == ""

    molecule.set_charge(atom_id, 1)

    assert atom_label_markup(molecule, atom_id) == "C"
    assert atom_label_full(molecule, atom_id) == "C+"


def test_group_label_keeps_an_additional_charge() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)
    molecule.set_label(atom_id, "OTs")

    assert atom_label_markup(molecule, atom_id) == "OTs"
    assert atom_label_full(molecule, atom_id) == "OTs+"


def test_charge_does_not_change_the_label_box() -> None:
    """Die Ladung darf Bindungsenden und Zentrierung nicht verschieben."""
    molecule = Molecule()
    neutral = molecule.add_atom("N", Point2D(0.0, 0.0))
    charged = molecule.add_atom("N", Point2D(80.0, 0.0), charge=7)

    assert label_half_size(molecule, charged) == label_half_size(molecule, neutral)


def test_charge_rect_sits_top_right_of_the_label() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=2)

    charge = charge_rect(molecule, atom_id)
    label = label_rect(molecule, atom_id)

    assert charge is not None and label is not None
    # oben rechts: rechts vom Label, aber auf dessen Hälfte
    assert charge.left() > 0.0
    assert charge.top() < label.top() + label.height() * 0.5
    assert label.contains(charge)


def test_neutral_atom_has_no_charge_rect() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0))
    assert charge_rect(molecule, atom_id) is None


def test_charge_follows_a_chosen_direction() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=2)
    default = charge_rect(molecule, atom_id)

    molecule.set_charge_direction(atom_id, Point2D(0.0, 1.0))  # unten
    below = charge_rect(molecule, atom_id)

    assert default is not None and below is not None
    assert below.top() > 0.0                      # unterhalb des Atoms
    assert below.center().x() == pytest.approx(0.0, abs=1.0)
    assert below.top() != pytest.approx(default.top())


def test_charge_rect_at_previews_any_direction() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("N", Point2D(0.0, 0.0), charge=1)

    rect = charge_rect_at(molecule, atom_id, Point2D(-1.0, 0.0))

    assert rect is not None
    assert rect.right() < 0.0


def test_charge_direction_defaults_to_the_free_corner() -> None:
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(0.0, BOND_LENGTH))
    molecule.add_bond(carbon, nitrogen)

    direction = charge_direction(molecule, nitrogen)

    # Bindung zeigt nach oben (-y) → Ladung nach unten weg
    assert direction.y > 0.0
    assert direction.length == pytest.approx(1.0)


def test_charge_keeps_bond_endings_identical() -> None:
    """Das Ladungszeichen selbst kürzt die Bindungen nicht anders.

    Am vierbindigen Stickstoff (Ammonium) verschiebt die Ladung die Zahl der
    impliziten H-Atome nicht – Label und Bindungsenden bleiben gleich.
    """
    molecule = Molecule()
    center = Point2D(0.0, 0.0)
    middle = molecule.add_atom("N", center)
    for angle in (0.0, 90.0, 180.0, 270.0):
        neighbor = molecule.add_atom("C", polar(center, angle, BOND_LENGTH))
        molecule.add_bond(middle, neighbor)

    before = [segment for bond in molecule.bonds for segment in bond_segments(molecule, bond)]
    molecule.set_charge(middle, 1)
    after = [segment for bond in molecule.bonds for segment in bond_segments(molecule, bond)]

    assert before == after


def test_custom_label_overrides_element_and_charge() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))

    molecule.set_label(atom_id, "NO2")
    assert atom_label(molecule, atom_id) == "NO2"

    molecule.set_label(atom_id, "Fe^{3+}")
    assert atom_label(molecule, atom_id) == "Fe3+"


def test_terminal_label_starts_at_bond_end() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(a, b)

    start, end = bond_segments(molecule, molecule.bonds[0])[0]
    # Die Linie endet Kappenbreite + Label-Abstand vor dem Label, damit die
    # runde Spitze nicht halb von der weißen Label-Maske überdeckt wird.
    gap = DEFAULT_STYLE.bond_label_gap
    cap_radius = DEFAULT_STYLE.bond_width / 2.0
    assert start.distance_to(end) == pytest.approx(BOND_LENGTH - gap - cap_radius)

    half_width, _half_height = label_half_size(molecule, b)
    center = label_center(molecule, b)
    # Der linke Buchstabe liegt am Bindungsende, das Label wächst nach außen.
    assert center.x - half_width == pytest.approx(BOND_LENGTH)
    assert center.x > BOND_LENGTH
    assert center.y == pytest.approx(0.0)


def test_terminal_label_is_offset_away_from_the_bond() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("O", polar(Point2D(), 60.0, BOND_LENGTH))
    molecule.add_bond(a, b)

    anchor = molecule.atom(b).position
    offset = label_center(molecule, b) - anchor
    away = Point2D(math.cos(math.radians(60.0)), math.sin(math.radians(60.0)))

    assert offset.x * away.x + offset.y * away.y > 0.0


def test_terminal_label_stays_on_bond_height_for_flat_bonds() -> None:
    """Bei flachen Bindungen sitzt das Label seitlich, nicht nach unten versetzt."""
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("O", polar(Point2D(), 30.0, BOND_LENGTH))
    molecule.add_bond(a, b)

    offset = label_center(molecule, b) - molecule.atom(b).position

    assert offset.y == pytest.approx(0.0)
    assert offset.x > 0.0


def test_group_labels_stay_on_the_bond_height() -> None:
    """TsO/OTs hängen nicht unter der Bindung, sondern sitzen auf ihrer Höhe."""
    molecule = Molecule()
    center = molecule.add_atom("C", Point2D(0.0, 0.0))
    left = molecule.add_atom("O", polar(Point2D(), 210.0, BOND_LENGTH))
    right = molecule.add_atom("O", polar(Point2D(), 330.0, BOND_LENGTH))
    molecule.add_bond(center, left)
    molecule.add_bond(center, right)
    molecule.set_label(left, "TsO")
    molecule.set_label(right, "OTs")

    left_offset = label_center(molecule, left) - molecule.atom(left).position
    right_offset = label_center(molecule, right) - molecule.atom(right).position

    assert left_offset.y == pytest.approx(0.0)
    assert right_offset.y == pytest.approx(0.0)
    assert left_offset.x < 0.0 < right_offset.x


def _first_char_width(text: str) -> float:
    font = QFont(DEFAULT_STYLE.label_font_family)
    font.setPixelSize(DEFAULT_STYLE.label_pixel_size)
    return QFontMetricsF(font).horizontalAdvance(text[0])


def test_label_below_vertical_bond_centres_the_first_letter() -> None:
    """Imin-Fall: das N sitzt mittig über der Bindungsachse, nicht daneben."""
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(0.0, BOND_LENGTH))
    molecule.add_bond(carbon, nitrogen, order=2)
    molecule.set_label(nitrogen, "NH")

    half_width, half_height = label_half_size(molecule, nitrogen)
    center = label_center(molecule, nitrogen)
    ink_left = center.x - (half_width - DEFAULT_STYLE.label_padding)

    # Das erste Zeichen steht mittig auf der Bindungsachse (x = 0) …
    assert ink_left + _first_char_width("NH") / 2.0 == pytest.approx(0.0)
    # … und die Box schließt mit ihrer Oberkante am Atom an.
    assert center.y - half_height == pytest.approx(BOND_LENGTH)


def test_label_above_vertical_bond_centres_the_first_letter() -> None:
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    nitrogen = molecule.add_atom("N", Point2D(0.0, -BOND_LENGTH))
    molecule.add_bond(carbon, nitrogen, order=2)
    molecule.set_label(nitrogen, "NH")

    half_width, half_height = label_half_size(molecule, nitrogen)
    center = label_center(molecule, nitrogen)
    ink_left = center.x - (half_width - DEFAULT_STYLE.label_padding)

    assert ink_left + _first_char_width("NH") / 2.0 == pytest.approx(0.0)
    assert center.y + half_height == pytest.approx(-BOND_LENGTH)


def test_single_element_on_vertical_bond_stays_centred() -> None:
    """Ein einzelnes Elementsymbol bleibt mittig unter der Bindung."""
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(0.0, BOND_LENGTH))
    molecule.add_bond(carbon, oxygen, order=2)  # Keton: kein H am O

    offset = label_center(molecule, oxygen) - molecule.atom(oxygen).position

    assert offset.x == pytest.approx(0.0)
    assert offset.y > 0.0


def test_terminal_oh_centres_the_oxygen_on_the_bond_axis() -> None:
    """Die Bindung zeigt auf das O von ``OH``, nicht zwischen O und H."""
    molecule = Molecule()
    carbon = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(0.0, BOND_LENGTH))
    molecule.add_bond(carbon, oxygen)

    half_width, _half_height = label_half_size(molecule, oxygen)
    center = label_center(molecule, oxygen)
    ink_left = center.x - (half_width - DEFAULT_STYLE.label_padding)

    assert ink_left + _first_char_width("O") / 2.0 == pytest.approx(0.0)


def test_internal_label_is_trimmed_at_bond() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", polar(Point2D(BOND_LENGTH, 0.0), 60.0, BOND_LENGTH))
    molecule.add_bond(left, middle)
    bond = molecule.add_bond(middle, oxygen)
    molecule.set_label(middle, "CH2")

    start, end = bond_segments(molecule, bond)[0]
    assert start.distance_to(end) < BOND_LENGTH
    assert label_extent(molecule, middle, Point2D(0.5, math.sqrt(3.0) / 2.0)) > 0.0


def test_bond_to_label_is_not_trimmed_at_box_corner() -> None:
    molecule = Molecule()
    angle = math.radians(15.0)
    center = molecule.add_atom("C", Point2D(0.0, 0.0))
    molecule.add_bond(center, molecule.add_atom("C", polar(Point2D(), 15.0, BOND_LENGTH)))
    molecule.add_bond(center, molecule.add_atom("C", polar(Point2D(), 195.0, BOND_LENGTH)))
    molecule.set_label(center, "CH2")

    toward = Point2D(math.cos(angle), math.sin(angle))
    half_width, half_height = label_half_size(molecule, center)
    box_extent = min(half_width / abs(toward.x), half_height / abs(toward.y))

    # Abgerundete Label-Box: die Bindung endet näher am Label als an der Ecke
    # des vollen Rechtecks (sonst wirkt die Bindung unnötig kurz).
    assert label_extent(molecule, center, toward) < box_extent - 1.0


def test_group_label_uses_tight_glyph_height() -> None:
    """Gruppenlabels (Rich-Text) werden wie Elementlabels positioniert.

    ``QTextDocument`` liefert die volle Zeilenhöhe inkl. Durchschuss; würde die
    als Labelhöhe verwendet, säße der Text zu weit von der Bindung entfernt.
    """
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(left, oxygen)
    _width, plain_height = label_half_size(molecule, oxygen)

    molecule.set_label(oxygen, "OTs")
    _group_width, group_height = label_half_size(molecule, oxygen)

    assert group_height == pytest.approx(plain_height, abs=2.0)


def test_bond_to_group_label_keeps_the_same_inset() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(left, oxygen)

    plain_length = bond_segments(molecule, bond)[0][0].distance_to(
        bond_segments(molecule, bond)[0][1]
    )
    molecule.set_label(oxygen, "OTs")
    group_length = bond_segments(molecule, bond)[0][0].distance_to(
        bond_segments(molecule, bond)[0][1]
    )

    assert group_length == pytest.approx(plain_length)


def test_double_bond_lines_are_trimmed_at_label() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", polar(Point2D(BOND_LENGTH, 0.0), 60.0, BOND_LENGTH))
    molecule.add_bond(left, middle)
    bond = molecule.add_bond(middle, oxygen, order=2)
    molecule.set_label(middle, "CH2")

    segments = bond_segments(molecule, bond)
    lengths = [start.distance_to(end) for start, end in segments]

    assert len(segments) == 2
    main_length, side_length = lengths
    # Beide Linien enden vor dem Label, die seitliche ist zusätzlich kürzer.
    assert 0.0 < side_length < main_length < BOND_LENGTH


def test_extremely_wide_label_does_not_invert_bond() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(a, b)
    molecule.set_label(b, "N(CH3)2")

    start, end = bond_segments(molecule, molecule.bonds[0])[0]
    assert start.distance_to(end) > 0.0


def test_label_extent_is_zero_for_unlabelled_carbon() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    assert label_extent(molecule, atom_id, Point2D(1.0, 0.0)) == 0.0


# -- Runde Bindungsenden ------------------------------------------------
def test_bond_end_inset_is_zero_without_label() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))

    assert bond_end_inset(molecule, atom_id, Point2D(1.0, 0.0)) == 0.0


def test_bond_end_inset_leaves_room_for_the_round_cap_at_terminal_label() -> None:
    molecule = Molecule()
    molecule.add_atom("C", Point2D(0.0, 0.0))
    oxygen = molecule.add_atom("O", Point2D(BOND_LENGTH, 0.0))
    molecule.add_bond(0, oxygen)

    inset = bond_end_inset(molecule, oxygen, Point2D(-1.0, 0.0))

    assert inset == pytest.approx(
        DEFAULT_STYLE.bond_label_gap + DEFAULT_STYLE.bond_width / 2.0
    )


def test_bond_end_inset_adds_cap_to_internal_label() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", polar(Point2D(BOND_LENGTH, 0.0), 60.0, BOND_LENGTH))
    molecule.add_bond(left, middle)
    molecule.add_bond(middle, oxygen)
    molecule.set_label(middle, "CH2")
    toward = Point2D(0.5, math.sqrt(3.0) / 2.0)

    inset = bond_end_inset(molecule, middle, toward)

    assert inset == pytest.approx(
        label_extent(molecule, middle, toward)
        + DEFAULT_STYLE.bond_label_gap
        + DEFAULT_STYLE.bond_width / 2.0
    )


def _count_marker_pixels(image: QImage) -> int:
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).blue() > 150 and image.pixelColor(x, y).red() < 120
    )


def test_hover_marker_is_drawn_around_atom() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    image = QImage(140, 140, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(255, 255, 255))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(70.0, 70.0)
    paint_hover_atom(painter, molecule, None)
    painter.end()
    assert _count_marker_pixels(image) == 0

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(70.0, 70.0)
    paint_hover_atom(painter, molecule, atom_id)
    painter.end()
    assert _count_marker_pixels(image) > 0


def test_render_molecule_with_custom_label() -> None:
    molecule = Molecule()
    atom_id = molecule.add_atom("C", Point2D(0.0, 0.0))
    molecule.set_label(atom_id, "NO2")

    image = render_image(molecule, width=160, height=120)

    assert not image.isNull()
    dark_pixels = sum(
        1
        for x in range(0, 160)
        for y in range(0, 120)
        if image.pixelColor(x, y).lightness() < 120
    )
    assert dark_pixels > 0


def test_single_bond_has_one_segment() -> None:
    molecule = ethane()
    segments = bond_segments(molecule, molecule.bonds[0])
    assert len(segments) == 1
    start, end = segments[0]
    assert start.distance_to(end) == pytest.approx(BOND_LENGTH)


def test_double_bond_has_two_parallel_segments() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(a, b, order=2)

    segments = bond_segments(molecule, bond)
    assert len(segments) == 2
    first_start, _ = segments[0]
    second_start, _ = segments[1]
    assert abs(first_start.y - second_start.y) > 1.0


def test_centered_double_bond_has_two_equal_symmetric_lines() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(a, b, order=2, centered=True)

    segments = bond_segments(molecule, bond)
    assert len(segments) == 2
    first, second = segments
    assert first[0].y == pytest.approx(-second[0].y)
    assert first[0].y != pytest.approx(0.0)
    # Beide Linien sind gleich lang (volle Bindungslänge).
    assert first[0].distance_to(first[1]) == pytest.approx(BOND_LENGTH)
    assert second[0].distance_to(second[1]) == pytest.approx(BOND_LENGTH)


def test_side_double_bond_line_is_shorter_than_the_main_line() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(a, b, order=2, side=1)

    main, side = bond_segments(molecule, bond)
    assert main[0].y == pytest.approx(0.0)
    assert side[0].y > 0.0
    assert main[0].distance_to(main[1]) == pytest.approx(BOND_LENGTH)
    assert side[0].distance_to(side[1]) < BOND_LENGTH


def _midpoint(segment: tuple[Point2D, Point2D]) -> Point2D:
    start, end = segment
    return Point2D((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)


def test_benzene_double_bonds_lie_inside_the_ring() -> None:
    molecule = benzene()
    centroid = Point2D(0.0, 0.0)

    for bond in molecule.bonds:
        if bond.order != 2:
            continue
        segments = bond_segments(molecule, bond)
        assert len(segments) == 2
        main_mid = _midpoint(segments[0])
        inner_mid = _midpoint(segments[1])
        assert inner_mid.distance_to(centroid) < main_mid.distance_to(centroid)


def test_ring_double_bond_side_ignores_neighbor_order() -> None:
    """Auch wenn eine Substituentenbindung vor den Ringbindungen entsteht."""
    molecule = Molecule()
    ring = [
        molecule.add_atom("C", polar(Point2D(), 90.0 - 60.0 * index, BOND_LENGTH))
        for index in range(6)
    ]
    substituent = molecule.add_atom("C", Point2D(0.0, 2.5 * BOND_LENGTH))
    molecule.add_bond(ring[0], substituent)  # absichtlich vor den Ringbindungen
    for index in range(6):
        molecule.add_bond(
            ring[index],
            ring[(index + 1) % 6],
            2 if index % 2 == 0 else 1,
        )

    centroid = Point2D(0.0, 0.0)
    for bond in molecule.bonds:
        if bond.order != 2:
            continue
        segments = bond_segments(molecule, bond)
        main_mid = _midpoint(segments[0])
        inner_mid = _midpoint(segments[1])
        assert inner_mid.distance_to(centroid) < main_mid.distance_to(centroid)


def test_chain_double_bond_side_can_be_flipped() -> None:
    molecule = Molecule()
    a = molecule.add_atom("C", Point2D(0.0, 0.0))
    b = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    bond = molecule.add_bond(a, b, order=2, side=1)

    segments = bond_segments(molecule, bond)
    assert segments[0][0].y == pytest.approx(0.0)
    assert segments[1][0].y > 0.0

    molecule.set_bond_order(bond, 2, side=-1)
    segments = bond_segments(molecule, molecule.bonds[0])
    assert segments[1][0].y < 0.0


def test_bond_is_trimmed_at_atom_label() -> None:
    molecule = Molecule()
    left = molecule.add_atom("C", Point2D(0.0, 0.0))
    middle = molecule.add_atom("C", Point2D(BOND_LENGTH, 0.0))
    oxygen = molecule.add_atom("O", polar(Point2D(BOND_LENGTH, 0.0), 60.0, BOND_LENGTH))
    molecule.add_bond(left, middle)
    bond = molecule.add_bond(middle, oxygen)
    molecule.set_label(middle, "CH2")

    start, end = bond_segments(molecule, bond)[0]
    assert start.distance_to(end) < BOND_LENGTH


def test_render_image_contains_structure() -> None:
    image = render_image(ethane(), width=200, height=150)
    dark_pixels = sum(
        1
        for x in range(0, 200, 2)
        for y in range(0, 150, 2)
        if image.pixelColor(x, y).lightness() < 120
    )
    assert dark_pixels > 0


def test_render_benzene_and_ethanol() -> None:
    for molecule in (benzene(), ethanol()):
        image = render_image(molecule, width=160, height=120)
        assert not image.isNull()


def test_save_png_and_svg(tmp_path) -> None:  # noqa: ANN001
    png = save_png(ethane(), tmp_path / "ethane.png", width=300, height=200)
    svg = save_svg(benzene(), tmp_path / "benzene.svg", width=300, height=200)

    assert png.exists() and png.stat().st_size > 0
    assert svg.exists() and svg.stat().st_size > 0
    assert "<svg" in svg.read_text(encoding="utf-8")
