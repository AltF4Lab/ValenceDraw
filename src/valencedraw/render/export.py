"""Raster- und Vektorexport eines Dokuments (PNG / SVG)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter

from ..core.annotations import ArrowObject, TextObject
from ..core.molecule import Molecule
from .painter import electron_bounds, label_rect, paint_scene, qcolor, text_bounds
from .style import DEFAULT_STYLE, Style

DEFAULT_EXPORT_SIZE = QSize(1200, 800)


def content_bounds(
    molecule: Molecule | None = None,
    style: Style = DEFAULT_STYLE,
    texts: tuple[TextObject, ...] = (),
    arrows: tuple[ArrowObject, ...] = (),
) -> QRectF:
    """Bounding-Box aller Inhalte inklusive Rand (Szeneneinheiten)."""
    margin = style.bond_length * 0.75
    rects: list[QRectF] = []

    if molecule is not None and not molecule.is_empty():
        bounds = molecule.bounds()
        if bounds is not None:
            low, high = bounds
            rects.append(QRectF(low.x, low.y, high.x - low.x, high.y - low.y))
        # Atomlabels können über die Atompositionen hinausragen (endständige
        # Labels liegen neben dem Bindungsende).
        rects.extend(
            rect
            for atom_id in molecule.atom_ids()
            if (rect := label_rect(molecule, atom_id, style)) is not None
        )
        electrons = electron_bounds(molecule, style)
        if electrons is not None:
            rects.append(electrons)
    rects.extend(text_bounds(text, style) for text in texts)
    for arrow in arrows:
        low, high = arrow.extent()
        rects.append(QRectF(low.x, low.y, high.x - low.x, high.y - low.y))

    if not rects:
        return QRectF(-margin, -margin, 2 * margin, 2 * margin)

    union = rects[0]
    for rect in rects[1:]:
        union = union.united(rect)
    union = QRectF(union.x(), union.y(), max(union.width(), 1.0), max(union.height(), 1.0))
    return union.adjusted(-margin, -margin, margin, margin)


def _paint_fitted(
    painter: QPainter,
    molecule: Molecule | None,
    texts: tuple[TextObject, ...],
    arrows: tuple[ArrowObject, ...],
    width: int,
    height: int,
    style: Style,
) -> None:
    content = content_bounds(molecule, style, texts, arrows)
    if content.width() <= 0 or content.height() <= 0:
        return
    scale = min(width / content.width(), height / content.height())
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.translate(width / 2.0, height / 2.0)
    painter.scale(scale, scale)
    painter.translate(-content.center().x(), -content.center().y())
    paint_scene(painter, molecule, texts, arrows, style)


def render_image(
    molecule: Molecule | None,
    width: int = DEFAULT_EXPORT_SIZE.width(),
    height: int = DEFAULT_EXPORT_SIZE.height(),
    style: Style = DEFAULT_STYLE,
    texts: tuple[TextObject, ...] = (),
    arrows: tuple[ArrowObject, ...] = (),
) -> QImage:
    """Rendert das Dokument in ein ``QImage``."""
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(*style.background))
    painter = QPainter(image)
    try:
        _paint_fitted(painter, molecule, texts, arrows, width, height, style)
    finally:
        painter.end()
    return image


def save_png(
    molecule: Molecule | None,
    path: str | Path,
    width: int = DEFAULT_EXPORT_SIZE.width(),
    height: int = DEFAULT_EXPORT_SIZE.height(),
    style: Style = DEFAULT_STYLE,
    texts: tuple[TextObject, ...] = (),
    arrows: tuple[ArrowObject, ...] = (),
) -> Path:
    """Speichert das Dokument als PNG."""
    file_path = Path(path)
    image = render_image(molecule, width, height, style, texts, arrows)
    if not image.save(str(file_path), "PNG"):
        raise OSError(f"PNG konnte nicht geschrieben werden: {file_path}")
    return file_path


def save_svg(
    molecule: Molecule | None,
    path: str | Path,
    width: int = DEFAULT_EXPORT_SIZE.width(),
    height: int = DEFAULT_EXPORT_SIZE.height(),
    style: Style = DEFAULT_STYLE,
    texts: tuple[TextObject, ...] = (),
    arrows: tuple[ArrowObject, ...] = (),
) -> Path:
    """Speichert das Dokument als SVG (vektoriell, HiDPI-fähig)."""
    from PySide6.QtSvg import QSvgGenerator

    file_path = Path(path)
    generator = QSvgGenerator()
    generator.setFileName(str(file_path))
    generator.setSize(QSize(width, height))
    generator.setViewBox(QRectF(0, 0, width, height))
    generator.setTitle("ValenceDraw")
    generator.setDescription("2D-Struktur, exportiert mit ValenceDraw")

    painter = QPainter()
    if not painter.begin(generator):
        raise OSError(f"SVG konnte nicht geschrieben werden: {file_path}")
    try:
        painter.fillRect(QRectF(0, 0, width, height), qcolor(style.background))
        _paint_fitted(painter, molecule, texts, arrows, width, height, style)
    finally:
        painter.end()
    return file_path
