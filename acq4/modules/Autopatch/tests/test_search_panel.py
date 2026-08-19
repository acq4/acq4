"""Tests for Area 2's cell-finding config: the search constraints it builds, the
region-seeding request it emits, and the survey readout it shows."""

import pytest

from acq4.experiment.slice import SearchConstraints
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def makePanel(**kwargs):
    from acq4.modules.Autopatch.search_panel import SearchPanel

    return SearchPanel(**kwargs)


def test_defaults_match_the_engines_defaults(qapp):
    # An operator who touches nothing must get the same search the engine
    # documents, not a second set of defaults that silently disagrees.
    assert makePanel().constraints() == SearchConstraints()


def test_the_physical_controls_read_in_si_units(qapp):
    # On the control that decides how deep an objective travels, "-20 µm" is the
    # readable form; "-0.0000200 m" is a value an operator has to count zeros
    # in. The µ here is U+00B5, the character pyqtgraph's SI_PREFIXES uses.
    panel = makePanel()
    assert panel.nearDepthSpin.text() == "-20 µm"
    assert panel.farDepthSpin.text() == "-60 µm"
    # A probability has no unit to prefix, so it reads as itself.
    assert panel.minHealthSpin.text() == "0.5"


def test_the_density_control_reads_in_cells_per_nanolitre(qapp):
    # max_cell_density is stored in SI (cells/m^3), but "5 T/m³" is not a
    # number an operator reasons about a field of view in; "5 cells/nL" is,
    # since a typical z-stack field of view is a couple of nanolitres.
    panel = makePanel()
    assert panel.maxDensitySpin.text() == "5 cells/nL"


def test_the_detection_step_reads_in_si_units(qapp):
    # step_z is a z distance, the same unit family as the depth controls, so
    # it reads the same way: "2 µm" rather than "0.0000020 m".
    panel = makePanel(step_z=2e-6)
    assert panel.stepZSpin.text() == "2 µm"


def test_the_min_volume_control_reads_in_si_cubic_metres(qapp):
    # Mirrors AutomationDebug's own minimum-volume spin box (m³, SI-prefixed):
    # a volume floor is small enough that a raw m^3 number is unreadable
    # without prefixing.
    panel = makePanel(min_volume_m3=5e-17)
    assert panel.minVolumeSpin.text() == "50 am³"


def test_the_detection_controls_are_seeded_from_the_constructor_defaults(qapp):
    # Area 2 has no idea what a rig's `misc` config says; its owner reads
    # that and passes it in here, so an operator opening Area 2 for the first
    # time sees the rig's own starting point, not a hard-coded one.
    panel = makePanel(min_volume_m3=5e-17, step_z=2e-6)
    assert panel.minVolumeSpin.value() == pytest.approx(5e-17)
    assert panel.stepZSpin.value() == pytest.approx(2e-6)


def test_the_detection_controls_default_to_the_engines_defaults(qapp):
    # An owner that passes nothing (a manager-less window, say) must not end
    # up with a search Area 2 itself disagrees with.
    panel = makePanel()
    assert panel.minVolumeSpin.value() == pytest.approx(SearchConstraints().min_volume_m3)
    assert panel.stepZSpin.value() == pytest.approx(SearchConstraints().step_z)


def test_editing_the_depth_range_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.nearDepthSpin.setValue(-10e-6)
    panel.farDepthSpin.setValue(-50e-6)
    assert panel.constraints().depth_range == (
        pytest.approx(-10e-6),
        pytest.approx(-50e-6),
    )


@pytest.mark.parametrize("widgetName", ["nearDepthSpin", "farDepthSpin"])
def test_the_depth_controls_cannot_be_driven_above_the_surface(qapp, widgetName):
    # Depths are signed offsets from the tissue surface, so a positive value
    # would search the bath above it. SearchConstraints rejects that, but the
    # widget's own bounds are what stop the operator getting there at all.
    panel = makePanel()
    spin = getattr(panel, widgetName)

    spin.setValue(50e-6)

    assert spin.value() == pytest.approx(0.0)


def test_editing_the_health_cutoff_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.minHealthSpin.setValue(0.8)
    assert panel.constraints().min_health == pytest.approx(0.8)


def test_editing_the_max_cell_density_is_reflected_in_the_constraints(qapp):
    # The spin box is in cells/nL; SearchConstraints.max_cell_density is SI
    # cells/m^3. Setting 2 cells/nL must reach the constraint as 2e12
    # cells/m^3 (1 nL == 1e-12 m^3) -- a dropped or inverted scale factor
    # would leave this as 2.0 or 2e-12 instead.
    panel = makePanel()
    panel.maxDensitySpin.setValue(2.0)
    assert panel.constraints().max_cell_density == pytest.approx(2e12)


def test_editing_the_min_volume_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.minVolumeSpin.setValue(5e-17)
    assert panel.constraints().min_volume_m3 == pytest.approx(5e-17)


def test_editing_the_detection_step_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.stepZSpin.setValue(2e-6)
    assert panel.constraints().step_z == pytest.approx(2e-6)


def test_the_detection_step_cannot_be_driven_to_zero_or_below(qapp):
    # step_z is a z increment for a detection stack; SearchConstraints rejects
    # a non-positive one, but the widget's own lower bound is what stops the
    # operator getting there at all, the same discipline the depth controls
    # use for their own single-field bound.
    panel = makePanel()
    panel.stepZSpin.setValue(-1e-6)
    assert panel.stepZSpin.value() > 0.0


def test_editing_rescans_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.rescansCheck.setChecked(True)
    assert panel.constraints().rescans_allowed is True


@pytest.mark.parametrize(
    "edit, attr, expected",
    [
        (
            lambda panel: panel.nearDepthSpin.setValue(-15e-6),
            "depth_range",
            (pytest.approx(-15e-6), pytest.approx(-60e-6)),
        ),
        (
            lambda panel: panel.farDepthSpin.setValue(-70e-6),
            "depth_range",
            (pytest.approx(-20e-6), pytest.approx(-70e-6)),
        ),
        (
            lambda panel: panel.minHealthSpin.setValue(0.75),
            "min_health",
            pytest.approx(0.75),
        ),
        (
            lambda panel: panel.maxDensitySpin.setValue(2.0),
            "max_cell_density",
            pytest.approx(2e12),
        ),
        (lambda panel: panel.rescansCheck.setChecked(True), "rescans_allowed", True),
        (
            lambda panel: panel.minVolumeSpin.setValue(5e-17),
            "min_volume_m3",
            pytest.approx(5e-17),
        ),
        (
            lambda panel: panel.stepZSpin.setValue(2e-6),
            "step_z",
            pytest.approx(2e-6),
        ),
    ],
    ids=[
        "near_depth",
        "far_depth",
        "min_health",
        "max_density",
        "rescans",
        "min_volume",
        "step_z",
    ],
)
def test_an_edit_emits_the_new_constraints(qapp, edit, attr, expected):
    # Each control is wired to _onEdited independently; the window listens on
    # sigConstraintsChanged to push edits into the live search, so a control
    # missing this wiring means the operator changes a setting and nothing
    # happens. Exercising every control here, not just constraints() directly,
    # is what would catch a dropped connection.
    panel = makePanel()
    emitted = []
    panel.sigConstraintsChanged.connect(emitted.append)

    edit(panel)

    assert emitted, "editing a constraint must announce the new search"
    assert getattr(emitted[-1], attr) == expected


def test_an_invalid_depth_range_does_not_raise_out_of_the_widget(qapp):
    # Constraint validation raises, and an operator dragging a spinbox through
    # an invalid intermediate value must not crash the GUI thread.
    panel = makePanel()
    panel.nearDepthSpin.setValue(-30e-6)
    panel.farDepthSpin.setValue(-30e-6)
    assert panel.constraints() is None
    assert panel.errorLabel.text() != ""


def test_an_invalid_edit_announces_none_rather_than_staying_silent(qapp):
    # A listener holding the last-good constraints has to be told the widget no
    # longer describes a valid search, or it cannot decide to keep them.
    panel = makePanel()
    emitted = []
    panel.sigConstraintsChanged.connect(emitted.append)

    panel.farDepthSpin.setValue(panel.nearDepthSpin.value())

    assert emitted[-1] is None


def test_recovering_from_an_invalid_range_clears_the_error(qapp):
    panel = makePanel()
    panel.farDepthSpin.setValue(panel.nearDepthSpin.value())
    assert panel.constraints() is None
    panel.farDepthSpin.setValue(-70e-6)
    assert panel.constraints() is not None
    assert panel.errorLabel.text() == ""


def test_the_min_volume_cannot_be_driven_negative(qapp):
    # min_volume_m3 must be non-negative; the widget's own lower bound is what
    # stops the operator getting there, so constraints() never sees a
    # negative value to raise over.
    panel = makePanel()
    panel.minVolumeSpin.setValue(-5e-17)
    assert panel.minVolumeSpin.value() >= 0.0
    assert panel.constraints() is not None


def test_dragging_the_detection_step_through_its_lower_bound_does_not_raise(qapp):
    # An operator dragging stepZSpin down passes through values pyqtgraph
    # clamps at the widget's own bound; that must never reach constraints()
    # as a raw ValueError out of the GUI thread.
    panel = makePanel()
    for value in (5e-6, 1e-6, 1e-9, -1e-6, 0.0):
        panel.stepZSpin.setValue(value)
        assert panel.constraints() is not None


def test_an_externally_set_error_is_shown(qapp):
    panel = makePanel()
    panel.setError("Select a camera before starting a slice.")
    assert panel.errorLabel.text() == "Select a camera before starting a slice."


def test_an_externally_set_error_survives_a_valid_constraint_edit(qapp):
    # The owner's message is about something editing a spin box does not fix (no
    # camera is selected either way), and errorLabel is the operator's only
    # feedback for it, so a constraint edit that validates cleanly must not
    # erase it.
    panel = makePanel()
    panel.setError("Select a camera before starting a slice.")

    panel.minHealthSpin.setValue(0.75)

    assert panel.constraints() is not None
    assert panel.errorLabel.text() == "Select a camera before starting a slice."


def test_a_constraint_error_takes_the_line_and_gives_it_back(qapp):
    # A constraint error describes the control being touched right now, so it
    # wins while it lasts -- and the owner's message, still true, comes back
    # once the values are valid again rather than being lost.
    panel = makePanel()
    panel.setError("Select a camera before starting a slice.")

    panel.farDepthSpin.setValue(panel.nearDepthSpin.value())
    assert panel.constraints() is None
    assert "thickness" in panel.errorLabel.text()

    panel.farDepthSpin.setValue(-70e-6)
    assert panel.constraints() is not None
    assert panel.errorLabel.text() == "Select a camera before starting a slice."


def test_an_empty_message_retracts_an_externally_set_error(qapp):
    panel = makePanel()
    panel.setError("Select a camera before starting a slice.")
    panel.setError("")
    assert panel.errorLabel.text() == ""


def test_survey_stats_are_shown(qapp):
    panel = makePanel()
    panel.setSurveyStats(9, 3, 100 / 3)
    text = panel.surveyLabel.text()
    assert "3" in text and "9" in text and "33" in text


def test_survey_stats_with_no_region_read_as_no_region(qapp):
    panel = makePanel()
    panel.setSurveyStats(0, 0, 0.0)
    assert "no region" in panel.surveyLabel.text().lower()


@pytest.mark.parametrize(
    "widgetName",
    [
        "nearDepthSpin",
        "farDepthSpin",
        "minHealthSpin",
        "maxDensitySpin",
        "rescansCheck",
        "minVolumeSpin",
        "stepZSpin",
    ],
)
def test_locking_disables_editing_but_not_the_readout(qapp, widgetName):
    # A run in flight parameterises a producer that is already surveying, so
    # editing any constraint control mid-run would silently change the search
    # underneath it; the lock must reach every one of them, in both directions,
    # while leaving the readout alone.
    panel = makePanel()
    widget = getattr(panel, widgetName)
    # A slice already exists here: this test is about the run-lock reaching
    # every control, not about the separate no-slice lock covered elsewhere.
    panel.setSliceReady(True)

    panel.setInteractionLocked(True)
    assert not widget.isEnabled()
    assert panel.surveyLabel.isEnabled()

    panel.setInteractionLocked(False)
    assert widget.isEnabled()


def _controls(panel):
    return (
        panel.nearDepthSpin,
        panel.farDepthSpin,
        panel.minHealthSpin,
        panel.maxDensitySpin,
        panel.rescansCheck,
        panel.minVolumeSpin,
        panel.stepZSpin,
    )


def test_locked_when_no_slice_and_not_running(qapp):
    panel = makePanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(False)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_locked_when_no_slice_and_running(qapp):
    panel = makePanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(True)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_locked_when_slice_ready_but_running(qapp):
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_unlocked_only_when_slice_ready_and_not_running(qapp):
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(False)
    assert all(w.isEnabled() for w in _controls(panel))


def test_a_run_ending_does_not_unlock_a_panel_with_no_slice(qapp):
    # The two-writers bug this design exists to prevent: sigInteractionLocked
    # firing False at the end of a run must not override slice-readiness.
    panel = makePanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(True)
    panel.setInteractionLocked(False)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_a_panel_starts_locked_before_any_slice_exists(qapp):
    panel = makePanel()
    assert all(not w.isEnabled() for w in _controls(panel))
