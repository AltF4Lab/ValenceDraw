from __future__ import annotations

import pytest

from valencedraw.core.geometry import Point2D
from valencedraw.core.page import (
    SCENE_UNITS_PER_MM,
    Orientation,
    Page,
    PageFormat,
)


def test_default_page_is_a4_portrait() -> None:
    page = Page()
    assert page.format is PageFormat.A4
    assert page.orientation is Orientation.PORTRAIT
    assert page.width_mm == 210.0
    assert page.height_mm == 297.0


def test_scene_units_follow_millimetres() -> None:
    page = Page()
    assert page.width == 210.0 * SCENE_UNITS_PER_MM
    assert page.height == 297.0 * SCENE_UNITS_PER_MM


def test_landscape_swaps_width_and_height() -> None:
    page = Page(PageFormat.A4, Orientation.LANDSCAPE)
    assert page.width_mm == 297.0
    assert page.height_mm == 210.0
    assert page.width > page.height


@pytest.mark.parametrize(
    ("page_format", "width_mm", "height_mm"),
    [
        (PageFormat.A4, 210.0, 297.0),
        (PageFormat.A3, 297.0, 420.0),
        (PageFormat.A5, 148.0, 210.0),
        (PageFormat.LETTER, 215.9, 279.4),
        (PageFormat.LEGAL, 215.9, 355.6),
    ],
)
def test_known_formats(page_format: PageFormat, width_mm: float, height_mm: float) -> None:
    page = Page(page_format)
    assert (page.width_mm, page.height_mm) == (width_mm, height_mm)


def test_a4_and_letter_are_available() -> None:
    formats = set(PageFormat)
    assert PageFormat.A4 in formats
    assert PageFormat.LETTER in formats


def test_bounds_are_centred_around_origin() -> None:
    low, high = Page().bounds
    assert low == Point2D(-1050.0, -1485.0)
    assert high == Point2D(1050.0, 1485.0)


def test_with_format_and_orientation_keep_the_other_setting() -> None:
    page = Page().with_format(PageFormat.LETTER).with_orientation(Orientation.LANDSCAPE)
    assert page.format is PageFormat.LETTER
    assert page.orientation is Orientation.LANDSCAPE


def test_toggled_switches_orientation() -> None:
    assert Page().toggled().orientation is Orientation.LANDSCAPE
    assert Page().toggled().toggled() == Page()
