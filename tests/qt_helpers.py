"""Kleine Helfer für simulierte Mausereignisse in Qt-Tests."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPointingDevice


def mouse_event(
    event_type: QEvent.Type,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    buttons: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    """Baut ein ``QMouseEvent`` ohne echten Widget-Kontext."""
    return QMouseEvent(
        event_type,
        QPointF(0.0, 0.0),
        QPointF(0.0, 0.0),
        button,
        buttons,
        modifiers,
        QPointingDevice.primaryPointingDevice(),
    )


def press(
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
) -> QMouseEvent:
    return mouse_event(
        QEvent.Type.MouseButtonPress, button=button, buttons=button, modifiers=modifiers
    )


def move(modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> QMouseEvent:
    return mouse_event(QEvent.Type.MouseMove, modifiers=modifiers)


def release() -> QMouseEvent:
    return mouse_event(QEvent.Type.MouseButtonRelease, buttons=Qt.MouseButton.NoButton)
