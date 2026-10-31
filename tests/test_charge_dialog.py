from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from valencedraw.core.molecule import MAX_ATOM_CHARGE
from valencedraw.ui.charge_dialog import ChargeDialog


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def test_dialog_prefills_the_charge() -> None:
    dialog = ChargeDialog(2, "N")

    assert dialog.charge() == 2


def test_dialog_covers_the_full_charge_range() -> None:
    dialog = ChargeDialog()

    assert dialog._spin.minimum() == -MAX_ATOM_CHARGE
    assert dialog._spin.maximum() == MAX_ATOM_CHARGE
    assert MAX_ATOM_CHARGE >= 7  # Mn in MnO4-


def test_dialog_returns_the_typed_charge() -> None:
    dialog = ChargeDialog(0, "N")

    dialog.set_charge(-3)

    assert dialog.charge() == -3


def test_preview_shows_the_superscript_charge() -> None:
    dialog = ChargeDialog(0, "N")

    dialog.set_charge(2)
    preview = dialog._preview.text()
    assert "N" in preview
    assert "<sup>" in preview
    assert "2+" in preview

    dialog.set_charge(0)
    assert "<sup>" not in dialog._preview.text()


def test_ask_returns_the_value(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        ChargeDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )

    assert ChargeDialog.ask(None, 4, "Mn") == 4


def test_ask_returns_none_on_cancel(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        ChargeDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )

    assert ChargeDialog.ask(None, 4, "Mn") is None
