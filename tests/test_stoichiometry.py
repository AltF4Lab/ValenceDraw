"""Tests für Reaktionsanalyse und Ansatztabelle."""

from __future__ import annotations

import pytest

from valencedraw.core.annotations import ArrowKind, ArrowObject
from valencedraw.core.geometry import Point2D
from valencedraw.core.stoichiometry import (
    ROLE_LABELS,
    RowRole,
    StoichiometryRow,
    StoichiometryTable,
    latex_escape,
    latex_table,
)
from valencedraw.document.document import Document
from valencedraw.document.reaction import (
    ReactionAnalysisError,
    analyze_reaction,
    table_from_analysis,
)
from valencedraw.ui.main_window import MainWindow
from valencedraw.ui.stoichiometry_panel import StoichiometryPanel


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001, PT004
    yield


def _reaction_document() -> Document:
    """H2 + 0.5 O2 → H2O mit Reagenz, Lösemittel und abgehender Gruppe."""
    document = Document()
    molecule = document.molecule

    hydrogen_a = molecule.add_atom("H", Point2D(-100.0, 0.0))
    hydrogen_b = molecule.add_atom("H", Point2D(-60.0, 0.0))
    molecule.add_bond(hydrogen_a, hydrogen_b)

    oxygen_a = molecule.add_atom("O", Point2D(-20.0, 0.0))
    oxygen_b = molecule.add_atom("O", Point2D(20.0, 0.0))
    molecule.add_bond(oxygen_a, oxygen_b, order=2)

    oxygen = molecule.add_atom("O", Point2D(150.0, 0.0))
    water_h_a = molecule.add_atom("H", Point2D(120.0, 30.0))
    water_h_b = molecule.add_atom("H", Point2D(180.0, 30.0))
    molecule.add_bond(oxygen, water_h_a)
    molecule.add_bond(oxygen, water_h_b)

    document.add_text(Point2D(30.0, -40.0), "H_2N-OH")  # Reagenz über dem Pfeil
    document.add_text(Point2D(30.0, 40.0), "EtOH")      # Lösemittel darunter
    document.add_text(Point2D(30.0, -90.0), "-R")       # abgehende Gruppe
    document.add_arrow(Point2D(40.0, 0.0), Point2D(120.0, 0.0), ArrowKind.FORWARD)
    return document


def _analysis():  # noqa: ANN202
    document = _reaction_document()
    return analyze_reaction(
        document.molecule,
        document.texts,
        document.arrows,
    )


def test_analysis_sorts_educts_products_reagents_and_ignores_solvent() -> None:
    analysis = _analysis()

    assert [species.name for species in analysis.educts] == ["H2", "O2"]
    assert [species.name for species in analysis.products] == ["H2O"]
    # Reagenzien werden nie als Summenformel interpretiert, sondern nur
    # fortlaufend benannt; der Anwender kann den Namen in der Tabelle ändern.
    assert [species.name for species in analysis.reagents] == ["Reagenz 1"]
    assert analysis.reagents[0].formula == ""
    assert analysis.solvents == ("EtOH",)
    assert analysis.ignored == ("-R",)


def test_analysis_computes_formulas_and_molar_masses() -> None:
    analysis = _analysis()

    assert analysis.educts[0].formula == "H2"
    assert analysis.educts[0].molar_mass == pytest.approx(2.016, abs=0.001)
    assert analysis.educts[1].formula == "O2"
    assert analysis.educts[1].molar_mass == pytest.approx(31.998, abs=0.001)
    assert analysis.products[0].formula == "H2O"
    assert analysis.products[0].molar_mass == pytest.approx(18.015, abs=0.001)
    assert analysis.reagents[0].molar_mass is None


def test_drawn_reagent_gets_generic_name_and_no_molar_mass() -> None:
    document = _reaction_document()
    molecule = document.molecule
    left = molecule.add_atom("C", Point2D(70.0, -70.0))
    right = molecule.add_atom("C", Point2D(100.0, -70.0))
    molecule.add_bond(left, right)

    analysis = analyze_reaction(document.molecule, document.texts, document.arrows)

    drawn = next(species for species in analysis.reagents if species.atom_ids)
    assert {species.name for species in analysis.reagents} == {
        "Reagenz 1",
        "Reagenz 2",
    }
    assert drawn.formula == ""
    assert drawn.molar_mass is None


def test_analysis_balances_the_equation() -> None:
    analysis = _analysis()

    assert analysis.educts[0].equivalents == pytest.approx(1.0)
    assert analysis.educts[1].equivalents == pytest.approx(0.5)
    assert analysis.products[0].equivalents == pytest.approx(1.0)


def test_analysis_without_arrow_is_rejected() -> None:
    document = _reaction_document()

    with pytest.raises(ReactionAnalysisError):
        analyze_reaction(document.molecule, document.texts, ())


def test_analysis_with_selected_arrow_uses_all_structures() -> None:
    document = _reaction_document()

    analysis = analyze_reaction(
        document.molecule,
        document.texts,
        document.arrows,
        selected_arrows={0},
    )

    assert len(analysis.educts) == 2
    assert len(analysis.products) == 1


def _table() -> StoichiometryTable:
    return table_from_analysis(_analysis())


def test_table_edits_mass_and_updates_all_rows() -> None:
    table = _table()

    assert table.amount_mmol(table.rows[0]) is None
    assert table.set_value(0, "m", 0.1) is None

    hydrogen, oxygen, _reagent, water = table.rows
    assert table.amount_mmol(hydrogen) == pytest.approx(0.1 / 2.016 * 1000.0)
    assert table.amount_mmol(oxygen) == pytest.approx(0.5 * table.base_amount_mmol)
    assert table.mass_g(water) == pytest.approx(
        table.amount_mmol(water) * 18.015 / 1000.0
    )


def test_editing_product_mass_scales_educts() -> None:
    table = _table()

    assert table.set_value(3, "m", 0.36) is None

    hydrogen, oxygen, _reagent, water = table.rows
    # 0,36 g Wasser = 0,36/18,015 mol; H2 1 eq, O2 0,5 eq
    assert table.amount_mmol(water) == pytest.approx(0.36 / 18.015 * 1000.0)
    assert table.mass_g(hydrogen) == pytest.approx(0.36 / 18.015 * 2.016)
    assert table.mass_g(oxygen) == pytest.approx(0.36 / 18.015 * 0.5 * 31.998)


def test_editing_density_and_volume_updates_mass_and_amount() -> None:
    table = _table()

    assert table.set_value(3, "rho", 1.0) is None
    assert table.set_value(3, "V", 1.0) is None

    water = table.rows[3]
    assert table.mass_g(water) == pytest.approx(1.0)
    assert table.amount_mmol(water) == pytest.approx(1.0 / 18.015 * 1000.0)


def test_editing_equivalents_changes_amounts() -> None:
    table = _table()
    table.set_value(0, "m", 0.1)
    base = table.base_amount_mmol

    assert table.set_value(1, "eq", 1.0) is None

    assert table.amount_mmol(table.rows[1]) == pytest.approx(base)


def test_reagent_needs_molar_mass_before_mass() -> None:
    table = _table()
    table.set_value(0, "m", 0.1)

    error = table.set_value(2, "m", 0.2)

    assert error is not None and "molare Masse" in error
    assert table.set_value(2, "M", 98.08) is None
    assert table.mass_g(table.rows[2]) is None  # noch keine Äquivalente

    assert table.set_value(2, "eq", 1.0) is None
    assert table.mass_g(table.rows[2]) == pytest.approx(
        table.base_amount_mmol * 98.08 / 1000.0
    )


def test_invalid_values_are_rejected() -> None:
    table = _table()

    assert table.set_value(0, "eq", 0) is not None
    assert table.set_value(0, "M", 0) is not None
    assert table.set_value(0, "rho", -1) is not None
    assert table.set_value(3, "m", -1) is not None


def test_reagent_name_can_be_changed() -> None:
    table = _table()

    assert table.rows[2].name == "Reagenz 1"
    assert table.rename(2, "Hydroxylamin") is None
    assert table.rows[2].name == "Hydroxylamin"
    assert table.rename(2, "   ") is not None
    assert table.rows[2].name == "Hydroxylamin"


def test_latex_export_contains_table_and_values() -> None:
    table = _table()
    table.set_value(0, "m", 0.1)

    latex = latex_table(table)

    assert r"\begin{tabular}" in latex
    assert r"\end{tabular}" in latex
    assert "Substanz & Rolle" in latex
    assert "H2" in latex and "O2" in latex and "H2O" in latex
    assert "Reagenz 1" in latex
    assert "0.1" in latex


def test_latex_export_escapes_special_characters() -> None:
    table = _table()
    name = r"a&b_c%d$e#f{g}h~i^j\k"
    assert table.rename(2, name) is None

    latex = latex_table(table)

    assert (
        r"a\&b\_c\%d\$e\#f\{g\}h\textasciitilde{}i\textasciicircum{}j"
        r"\textbackslash{}k"
    ) in latex
    assert latex_escape("50% & 1_2") == r"50\% \& 1\_2"


def test_panel_copies_latex_to_clipboard() -> None:
    from PySide6.QtWidgets import QApplication

    panel = StoichiometryPanel()
    try:
        panel.set_table(_table())
        QApplication.clipboard().clear()

        panel.copy_button.click()

        text = QApplication.clipboard().text()
        assert r"\begin{tabular}" in text
        assert "Reagenz 1" in text
        assert "Zwischenablage" in panel._message.text()
    finally:
        panel.close()


def test_panel_edits_update_the_model() -> None:
    table = _table()
    panel = StoichiometryPanel()
    try:
        panel.set_table(table)

        assert panel.table_widget.rowCount() == 4
        assert panel.table_widget.columnCount() == 8
        assert "2px solid #000000" in panel.table_widget.styleSheet()
        # Spalte 5 = m / g; Produktmasse eintragen.
        panel.table_widget.item(3, 5).setText("0,36")

        assert table.mass_g(table.rows[3]) == pytest.approx(0.36, abs=1e-6)
        assert table.mass_g(table.rows[0]) == pytest.approx(0.36 / 18.015 * 2.016)
        assert panel.table_widget.item(0, 5).text() != ""

        # Spalte 0 = Substanz; Reagenzname direkt in der Tabelle ändern.
        panel.table_widget.item(2, 0).setText("Hydroxylamin")
        assert table.rows[2].name == "Hydroxylamin"
    finally:
        panel.close()


def test_panel_reports_invalid_input() -> None:
    panel = StoichiometryPanel()
    try:
        panel.set_table(_table())

        panel.table_widget.item(0, 5).setText("keine Zahl")

        assert "keine Zahl" in panel._message.text()
    finally:
        panel.close()


def test_main_window_creates_the_stoichiometry_panel() -> None:
    window = MainWindow(_reaction_document())
    try:
        window.document.select_all()
        window._show_stoichiometry()

        assert window._stoich_panel is not None
        assert window._stoich_panel.table is not None
        assert window._stoich_panel.table.rows[0].name == "H2"
    finally:
        window.document.mark_saved()
        window.close()


def test_row_role_labels_are_german() -> None:
    assert ROLE_LABELS[RowRole.EDUKT] == "Edukt"
    assert ROLE_LABELS[RowRole.PRODUKT] == "Produkt"
    assert ROLE_LABELS[RowRole.REAGENZ] == "Reagenz"
    assert StoichiometryRow("H2O", RowRole.PRODUKT).role is RowRole.PRODUKT
