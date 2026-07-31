"""SearchPanel: Area 2's cell-finding config -- the search constraints that
parameterise a cell producer, plus region seeding and a survey progress readout."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.experiment.slice import SearchConstraints
from acq4.util import Qt


class SearchPanel(Qt.QWidget):
    """The four Area 2 search constraints, a region-seeding button, and a readout.

    Emits `sigConstraintsChanged` with a fresh SearchConstraints on every edit,
    or with None when the widget values do not describe a valid search (an
    operator dragging a spinbox passes through invalid intermediate values, and
    that must not raise on the GUI thread). Region *graphics* are not this
    panel's job: it asks its owner to seed a region and shows how much of the
    result has been surveyed.
    """

    sigConstraintsChanged = Qt.Signal(object)  # SearchConstraints, or None if invalid
    sigAddRegionRequested = Qt.Signal()

    def __init__(self):
        super().__init__()
        defaults = SearchConstraints()
        # The two independent things errorLabel can be showing, kept apart so
        # neither silently erases the other. The constraint message describes
        # the spin box values themselves and is rewritten (or cleared) by every
        # call to constraints(); the external one is a condition only this
        # panel's owner can see -- no camera selected, say -- and stays true
        # regardless of what the operator types here, so an edit must not wipe
        # it. See _showError for which wins.
        self._constraintError = ""
        self._externalError = ""

        # Depths are offsets from the tissue surface, negative being deeper, so
        # the spin boxes read the way the design doc writes them (-20 um to
        # -60 um) rather than as unsigned depths that get subtracted somewhere
        # else. The bounds keep that sign on the widget itself: a positive
        # offset would search the bath above the tissue, and SearchConstraints
        # rejects it, but a control that cannot be dragged there at all is
        # better than an error message after the fact.
        self.nearDepthSpin = self._makeSpin(
            defaults.depth_range[0],
            bounds=(-1e-3, 0.0),
            step=5e-6,
            suffix="m",
            siPrefix=True,
        )
        self.farDepthSpin = self._makeSpin(
            defaults.depth_range[1],
            bounds=(-1e-3, 0.0),
            step=5e-6,
            suffix="m",
            siPrefix=True,
        )
        # A probability, not a physical quantity: no unit to prefix, so this one
        # takes the same widget purely for consistent look and stepping.
        self.minHealthSpin = self._makeSpin(
            defaults.min_health,
            bounds=(0.0, 1.0),
            step=0.05,
        )
        self.maxDensitySpin = self._makeSpin(
            defaults.max_cell_density,
            bounds=(1.0, 1e18),
            step=1e12,
            suffix="/m³",
            siPrefix=True,
        )
        self.rescansCheck = Qt.QCheckBox("Rescans allowed")
        self.rescansCheck.setChecked(defaults.rescans_allowed)

        self.addRegionBtn = Qt.QPushButton("Add region here")
        self.addRegionBtn.setToolTip(
            "Add a search region covering roughly 3x3 fields of view around the "
            "camera's current center."
        )
        self.surveyLabel = Qt.QLabel("no region")
        self.errorLabel = Qt.QLabel("")
        self.errorLabel.setStyleSheet("color: red;")

        form = Qt.QFormLayout()
        form.addRow("Depth from surface, near", self.nearDepthSpin)
        form.addRow("Depth from surface, far", self.farDepthSpin)
        form.addRow("Minimum health", self.minHealthSpin)
        form.addRow("Maximum cell density", self.maxDensitySpin)

        layout = Qt.QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.rescansCheck)
        layout.addWidget(self.addRegionBtn)
        layout.addWidget(self.surveyLabel)
        layout.addWidget(self.errorLabel)
        self.setLayout(layout)

        for spin in (
            self.nearDepthSpin,
            self.farDepthSpin,
            self.minHealthSpin,
            self.maxDensitySpin,
        ):
            spin.valueChanged.connect(self._onEdited)
        self.rescansCheck.toggled.connect(self._onEdited)
        self.addRegionBtn.clicked.connect(self.sigAddRegionRequested)

    @staticmethod
    def _makeSpin(value, bounds, step, suffix="", siPrefix=False):
        """A pyqtgraph SpinBox, the spin box the rest of acq4 uses for these
        quantities.

        `siPrefix` is what makes a depth read "-20 µm" instead of
        "-0.0000200 m" and a density "5 T/m³" instead of "5000000000000 /m³";
        `value()` still returns plain metres and plain cells per cubic metre, so
        the constraints built from these controls are unaffected by how they
        render.
        """
        return pg.SpinBox(
            value=value, bounds=bounds, step=step, suffix=suffix, siPrefix=siPrefix
        )

    def constraints(self) -> SearchConstraints | None:
        """The current widget values as constraints, or None if they are invalid.

        Returning None rather than raising is what lets an operator drag a
        spinbox through an invalid intermediate value without a traceback on
        the GUI thread; the reason lands in errorLabel instead.
        """
        try:
            constraints = SearchConstraints(
                depth_range=(self.nearDepthSpin.value(), self.farDepthSpin.value()),
                min_health=self.minHealthSpin.value(),
                max_cell_density=self.maxDensitySpin.value(),
                rescans_allowed=self.rescansCheck.isChecked(),
            )
        except ValueError as exc:
            self._constraintError = str(exc)
            self._showError()
            return None
        self._constraintError = ""
        self._showError()
        return constraints

    def setError(self, message: str) -> None:
        """Show a message from this panel's owner on the panel's error line.

        For conditions the panel cannot see for itself -- no camera selected,
        say -- so the operator reads them where they already read constraint
        errors, instead of the owner writing into errorLabel behind the panel's
        back and having the next constraint edit clear it. An empty message
        retracts it.
        """
        self._externalError = message
        self._showError()

    def _showError(self) -> None:
        """Render whichever error is current, the constraint one first.

        A constraint error is about the control the operator is touching right
        now, so it takes the line while it lasts; the owner's message is still
        held and comes back once the values are valid again, because whatever it
        reported (no camera, say) is not something editing a spin box fixes.
        """
        self.errorLabel.setText(self._constraintError or self._externalError)

    def _onEdited(self, *_args) -> None:
        self.sigConstraintsChanged.emit(self.constraints())

    def setSurveyStats(self, total: int, covered: int, percent: float) -> None:
        if total == 0:
            self.surveyLabel.setText("no region")
            return
        self.surveyLabel.setText(f"{covered}/{total} tiles imaged ({percent:.0f}%)")

    def setInteractionLocked(self, locked: bool) -> None:
        """Disable editing while a run is in flight; the readout stays visible.

        The constraints parameterise a producer that is already surveying, so
        editing them mid-run would silently change the search under it.
        """
        for w in (
            self.nearDepthSpin,
            self.farDepthSpin,
            self.minHealthSpin,
            self.maxDensitySpin,
            self.rescansCheck,
            self.addRegionBtn,
        ):
            w.setEnabled(not locked)
