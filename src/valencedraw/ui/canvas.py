"""Canvas: ``QGraphicsView`` mit Zoom, Pan und austauschbarem Werkzeug."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QNativeGestureEvent, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..core.geometry import Point2D
from ..document.document import Document
from ..render.export import content_bounds
from ..render.painter import (
    paint_hover_atom,
    paint_hover_bond,
    paint_scene,
    qcolor,
)
from ..render.style import DEFAULT_STYLE, Style
from .tools import Tool


class SceneItem(QGraphicsItem):
    """Zeichnet den kompletten Dokumentinhalt mit dem gemeinsamen Renderer."""

    def __init__(self, document: Document, style: Style = DEFAULT_STYLE) -> None:
        super().__init__()
        self._document = document
        self._style = style
        document.changed.connect(self._on_changed)
        document.selection_changed.connect(self._on_changed)

    def _on_changed(self) -> None:
        self.prepareGeometryChange()
        self.update()

    def set_style(self, style: Style) -> None:
        """Übernimmt einen geänderten Zeichenstil (Einstellungen)."""
        if style == self._style:
            return
        self.prepareGeometryChange()
        self._style = style
        self.update()

    def boundingRect(self) -> QRectF:
        return content_bounds(
            self._document.molecule,
            self._style,
            self._document.texts,
            self._document.arrows,
        )

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        paint_scene(
            painter,
            self._document.molecule,
            self._document.texts,
            self._document.arrows,
            self._style,
            self._document.selection,
            text_selection=self._document.text_selection,
            arrow_selection=self._document.arrow_selection,
        )


class Canvas(QGraphicsView):
    """Zeichenfläche mit Zoom (Mausrad) und Pan (mittlere Maustaste)."""

    zoom_changed = Signal(float)

    MIN_ZOOM = 0.02
    MAX_ZOOM = 8.0
    PAGE_MARGIN: float = 75.0
    """Grauer Rand über/unter dem Blatt (Szeneneinheiten, 7,5 mm).

    Ohne diesen Rand klebt das Blatt beim Scrollen am Fensterrand – man sieht
    dann nicht, dass man am oberen bzw. unteren Blattende angekommen ist.
    """

    def __init__(
        self,
        document: Document,
        style: Style = DEFAULT_STYLE,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._style = style
        self._tool: Tool | None = None
        self._panning = False
        self._pan_origin = QPointF()
        self._centering = False

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = SceneItem(document, style)
        self._scene.addItem(self._item)
        self._scene.setSceneRect(self.scene_rect())

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        # Zoom wird explizit um den Mauszeiger verankert (siehe ``zoom_by``);
        # Qts ``AnchorUnderMouse`` würde nur den Cursor und nicht das konkrete
        # Rad-/Gestenereignis auswerten.
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        # Vertikal immer scrollbar; horizontal nur, wenn das Blatt breiter als
        # das Fenster ist (die Scrollbar erscheint dann automatisch).
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setBackgroundBrush(QBrush(qcolor(style.workspace_background)))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        document.page_changed.connect(self._on_page_changed)

        # Manche Treiber schicken Pan-Gesten an das Fenster statt an den Viewport.
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.installEventFilter(self)

    # -- Werkzeuge -------------------------------------------------------
    @property
    def document(self) -> Document:
        return self._document

    @property
    def style(self) -> Style:
        """Aktueller Zeichenstil (Einstellungen)."""
        return self._style

    def set_style(self, style: Style) -> None:
        """Übernimmt einen geänderten Zeichenstil und zeichnet neu."""
        if style == self._style:
            return
        self._style = style
        self.setBackgroundBrush(QBrush(qcolor(style.workspace_background)))
        self._item.set_style(style)
        self.viewport().update()

    @property
    def tool(self) -> Tool | None:
        return self._tool

    def set_tool(self, tool: Tool | None) -> None:
        if self._tool is tool:
            return
        if self._tool is not None:
            self._tool.changed.disconnect(self._on_tool_changed)
            self._tool.deactivate()
        self._tool = tool
        if tool is not None:
            tool.changed.connect(self._on_tool_changed)
            tool.activate()
            self.setCursor(tool.cursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def _on_tool_changed(self) -> None:
        """Das Werkzeug hat sich selbst geändert (z. B. Auswahl eingeblendet)."""
        self.viewport().update()

    # -- Zoom ------------------------------------------------------------
    def page_rect(self) -> QRectF:
        """Blattfläche in Szenenkoordinaten (mittig um den Ursprung)."""
        low, high = self._document.page.bounds
        return QRectF(low.x, low.y, high.x - low.x, high.y - low.y)

    def scene_rect(self) -> QRectF:
        """Scrollbare Fläche: Blatt plus ``PAGE_MARGIN`` oben und unten."""
        margin = self.PAGE_MARGIN
        return self.page_rect().adjusted(0.0, -margin, 0.0, margin)

    def _on_page_changed(self, _page: object) -> None:
        self._scene.setSceneRect(self.scene_rect())
        self._keep_page_centred_if_needed()
        self.viewport().update()

    def _center_horizontally(self) -> None:
        """Setzt die horizontale Scrollposition immer auf die Blattmitte."""
        if self._centering:
            return
        bar = self.horizontalScrollBar()
        target = round((bar.minimum() + bar.maximum()) / 2.0)
        if bar.value() == target:
            return
        self._centering = True
        try:
            bar.setValue(target)
        finally:
            self._centering = False

    def _page_wider_than_viewport(self) -> bool:
        """Ragt das Blatt bei aktuellem Zoom über das Fenster hinaus?"""
        width = self.transform().mapRect(self.page_rect()).width()
        return width > self.viewport().width() + 0.5

    def _keep_page_centred_if_needed(self) -> None:
        """Blatt mittig halten, solange es (noch) ganz sichtbar ist.

        Sobald das Blatt breiter als das Fenster ist, darf **nicht** zentriert
        werden – sonst springt der Zoom vom Mauszeiger weg.
        """
        wide = self._page_wider_than_viewport()
        if not wide:
            self._center_horizontally()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        """Horizontal nur scrollen, wenn das Blatt überhaupt Spielraum hat."""
        bar = self.horizontalScrollBar()
        if bar.maximum() > bar.minimum():
            super().scrollContentsBy(dx, dy)
        else:
            super().scrollContentsBy(0, dy)
            self._center_horizontally()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._keep_page_centred_if_needed()

    def zoom_level(self) -> float:
        return self.transform().m11()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        """Zoomt um ``factor``; ``anchor`` (Viewport-Koordinaten) bleibt fix.

        Ohne ``anchor`` wird um die Mitte des sichtbaren Bereichs gezoomt
        (Tastatur/Menü). Der Punkt unter dem Mauszeiger bleibt bei Rad- und
        Pinch-Zoom exakt an derselben Stelle.
        """
        target = self.zoom_level() * factor
        if target < self.MIN_ZOOM or target > self.MAX_ZOOM:
            return
        if anchor is None:
            anchor = QPointF(self.viewport().rect().center())
        scene_point = self.mapToScene(anchor.toPoint())
        self.scale(factor, factor)
        self._scroll_to_keep_point(scene_point, anchor)
        self._keep_page_centred_if_needed()
        self.zoom_changed.emit(self.zoom_level())

    def _scroll_to_keep_point(self, scene_point: QPointF, anchor: QPointF) -> None:
        """Scrollt so, dass ``scene_point`` wieder unter ``anchor`` liegt."""
        moved = self.mapFromScene(scene_point)
        dx = round(moved.x() - anchor.x())
        dy = round(moved.y() - anchor.y())
        self._scroll_pixels(self.horizontalScrollBar(), dx)
        self._scroll_pixels(self.verticalScrollBar(), dy)

    @staticmethod
    def _scroll_pixels(bar, delta: int) -> None:
        """Scrollt eine Leiste um ``delta``-Pixel, sofern sie Spielraum hat."""
        if delta and bar.maximum() > bar.minimum():
            bar.setValue(bar.value() + delta)

    def zoom_in(self) -> None:
        self.zoom_by(1.2)

    def zoom_out(self) -> None:
        self.zoom_by(1 / 1.2)

    def fit_to_view(self) -> None:
        """Das ganze Blatt vollständig einpassen."""
        rect = self.page_rect()
        padding = self._style.bond_length * 1.5
        rect = rect.adjusted(-padding, -padding, padding, padding)
        if rect.isEmpty():
            return
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.zoom_level() > 1.5:
            self.setTransform(QTransform.fromScale(1.5, 1.5))
        self.centerOn(rect.center())
        self._keep_page_centred_if_needed()
        self.zoom_changed.emit(self.zoom_level())

    def fit_page_width(self) -> None:
        """Blattbreite einpassen und auf den Inhalt zentrieren (vertikal scrollbar)."""
        page = self.page_rect()
        if page.isEmpty():
            return
        padding = self._style.bond_length * 1.5
        scale = self.viewport().width() / (page.width() + 2 * padding)
        scale = max(self.MIN_ZOOM, min(self.MAX_ZOOM, scale, 1.0))
        self.setTransform(QTransform.fromScale(scale, scale))
        target = self._item.boundingRect().center()
        self.centerOn(target.x(), target.y())
        self._keep_page_centred_if_needed()
        self.zoom_changed.emit(self.zoom_level())

    # -- Mausereignisse --------------------------------------------------
    def _scene_position(self, event) -> Point2D:
        point = self.mapToScene(event.position().toPoint())
        return Point2D(point.x(), point.y())

    def _delegate(self, action: str, event) -> bool:
        tool = self._tool
        if tool is None:
            return False
        position = self._scene_position(event)
        if (
            action in ("press", "double_click")
            and event.button() == Qt.MouseButton.LeftButton
            and not tool.is_on_page(position)
        ):
            # Zeichnen ist nur auf dem Blatt erlaubt.
            return False
        handler = getattr(tool, f"mouse_{action}")
        repaint = handler(position, event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if repaint:
            self.viewport().update()
        return True

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_origin = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        ) and self._delegate("press", event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._panning:
            delta = event.position() - self._pan_origin
            self._pan_origin = event.position()
            if self._page_wider_than_viewport():
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            self._keep_page_centred_if_needed()
            event.accept()
            return
        if self._delegate("move", event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(self._tool.cursor if self._tool else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        ) and self._delegate("release", event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._delegate("double_click", event):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Mausrad/Zwei-Finger: scrollen; mit ``Strg`` zoomen."""
        self._handle_wheel(event)

    def _handle_wheel(self, event) -> bool:
        """Verarbeitet ein Rad-/Touchpad-Event; liefert ``True`` wenn behandelt.

        Vertikal wird immer gescrollt, horizontal nur, wenn das Blatt breiter
        als das Fenster ist. ``Shift`` + Mausrad scrollt horizontal.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y() * 10.0
            if delta != 0:
                self.zoom_by(1.15 ** (delta / 120.0), event.position())
            event.accept()
            return True

        pixel = event.pixelDelta()
        angle = event.angleDelta()
        # Achsenweise kombinieren: manche Treiber liefern nur eine der beiden
        # Quellen pro Achse (z. B. pixelDelta y + angleDelta x).
        dx = float(pixel.x()) if pixel.x() else angle.x() / 2.0
        dy = float(pixel.y()) if pixel.y() else angle.y() / 2.0
        # Shift wandelt nur ein rein vertikales Rad in horizontales Scrollen um;
        # eine bereits horizontale Geste darf nicht verworfen werden.
        dx, dy = self._apply_shift_axis(dx, dy, event.modifiers())
        self._scroll_by(dx, dy)
        event.accept()
        return True

    @staticmethod
    def _apply_shift_axis(
        dx: float,
        dy: float,
        modifiers: Qt.KeyboardModifier,
    ) -> tuple[float, float]:
        """Mit ``Shift`` scrollt eine vertikale Geste horizontal."""
        if modifiers & Qt.KeyboardModifier.ShiftModifier and dx == 0.0 and dy != 0.0:
            return dy, 0.0
        return dx, dy

    def _scroll_by(self, dx: float, dy: float) -> None:
        """Scrollt um Pixel-Deltas; der Szenenrand begrenzt alles aufs Blatt."""
        self._scroll_pixels(self.verticalScrollBar(), -self._delta_to_pixels(dy))
        self._scroll_pixels(self.horizontalScrollBar(), -self._delta_to_pixels(dx))

    @staticmethod
    def _delta_to_pixels(delta: float) -> int:
        """Kleine Touchpad-Deltas nicht auf 0 abschneiden."""
        if delta == 0:
            return 0
        pixels = round(delta)
        if pixels == 0:
            return 1 if delta > 0 else -1
        return pixels

    def event(self, event) -> bool:
        """Touchpad-Gesten: Pinch zoomt, Zwei-Finger-Pan scrollt."""
        if isinstance(event, QNativeGestureEvent) and self._handle_native_gesture(event):
            return True
        return super().event(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802
        """Rad-Events und Gesten direkt am Viewport abfangen."""
        if event.type() == QEvent.Type.Leave:
            self._clear_hover()
        if event.type() == QEvent.Type.Wheel:
            return self._handle_wheel(event)
        if isinstance(event, QNativeGestureEvent) and self._handle_native_gesture(event):
            return True
        return super().viewportEvent(event)

    def _clear_hover(self) -> None:
        """Hover-Hinweis entfernen, wenn der Cursor die Fläche verlässt."""
        tool = self._tool
        if tool is not None and tool.clear_hover():
            self.viewport().update()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Native Gesten auch dann abfangen, wenn sie nicht am Viewport landen."""
        if (
            isinstance(event, QNativeGestureEvent)
            and self._cursor_over_canvas()
            and self._handle_native_gesture(event)
        ):
            return True
        return super().eventFilter(watched, event)

    def _cursor_over_canvas(self) -> bool:
        if not self.isVisible() or not self.viewport().isVisible():
            return False
        local = self.viewport().mapFromGlobal(QCursor.pos())
        return self.viewport().rect().contains(local)

    def _handle_native_gesture(self, event: QNativeGestureEvent) -> bool:
        gesture = event.gestureType()
        if gesture == Qt.NativeGestureType.ZoomNativeGesture:
            factor = max(0.5, min(2.0, 1.0 + event.value()))
            anchor = QPointF(self.viewport().mapFromGlobal(QCursor.pos()))
            self.zoom_by(factor, anchor)
            event.accept()
            return True
        if gesture == Qt.NativeGestureType.PanNativeGesture:
            delta = event.delta()
            dx, dy = self._apply_shift_axis(delta.x(), delta.y(), event.modifiers())
            self._scroll_by(dx, dy)
            event.accept()
            return True
        return False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._document.delete_selection()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._document.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- Overlay ---------------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Graue Arbeitsfläche mit weißem Blatt und weichem Schatten."""
        painter.fillRect(rect, qcolor(self._style.workspace_background))
        page = self.page_rect()
        shadow = page.translated(
            self._style.page_shadow_offset,
            self._style.page_shadow_offset,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, self._style.page_shadow_alpha))
        painter.drawRect(shadow)

        border = QPen(qcolor(self._style.page_border))
        border.setCosmetic(True)
        border.setWidthF(1.0)
        painter.setPen(border)
        painter.setBrush(QBrush(qcolor(self._style.background)))
        painter.drawRect(page)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802, ARG002
        super().drawForeground(painter, rect)
        tool = self._tool
        if tool is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Einrast-Ziel (Atom) und Bindung unter dem Cursor vor der Vorschau.
        paint_hover_atom(painter, self._document.molecule, tool.snap_atom, self._style)
        paint_hover_bond(
            painter, self._document.molecule, tool.hovered_bond, self._style
        )
        tool.paint_overlay(painter)
        painter.restore()
