"""Tests for Area 2's cell-finding config: the search constraints it builds, the
region-seeding request it emits, and the survey readout it shows."""

import pytest

from acq4.experiment.slice import SearchConstraints
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def makePanel():
    from acq4.modules.Autopatch.search_panel import SearchPanel

    return SearchPanel()


def test_defaults_match_the_engines_defaults(qapp):
    # An operator who touches nothing must get the same search the engine
    # documents, not a second set of defaults that silently disagrees.
    assert makePanel().constraints() == SearchConstraints()


def test_editing_the_depth_range_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.nearDepthSpin.setValue(-10e-6)
    panel.farDepthSpin.setValue(-50e-6)
    assert panel.constraints().depth_range == (
        pytest.approx(-10e-6),
        pytest.approx(-50e-6),
    )


def test_editing_the_health_cutoff_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.minHealthSpin.setValue(0.8)
    assert panel.constraints().min_health == pytest.approx(0.8)


def test_editing_the_max_cell_density_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.maxDensitySpin.setValue(2e12)
    assert panel.constraints().max_cell_density == pytest.approx(2e12)


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
            lambda panel: panel.maxDensitySpin.setValue(2e12),
            "max_cell_density",
            pytest.approx(2e12),
        ),
        (lambda panel: panel.rescansCheck.setChecked(True), "rescans_allowed", True),
    ],
    ids=["near_depth", "far_depth", "min_health", "max_density", "rescans"],
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


def test_add_region_button_emits_a_request(qapp):
    panel = makePanel()
    requests = []
    panel.sigAddRegionRequested.connect(lambda: requests.append(True))

    panel.addRegionBtn.click()

    assert requests == [True]


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
        "addRegionBtn",
    ],
)
def test_locking_disables_editing_but_not_the_readout(qapp, widgetName):
    # A run in flight parameterises a producer that is already surveying, so
    # editing any constraint control or the add-region button mid-run would
    # silently change the search underneath it; the lock must reach every one
    # of them, in both directions, while leaving the readout alone.
    panel = makePanel()
    widget = getattr(panel, widgetName)

    panel.setInteractionLocked(True)
    assert not widget.isEnabled()
    assert panel.surveyLabel.isEnabled()

    panel.setInteractionLocked(False)
    assert widget.isEnabled()
