"""SearchPanel: Area 2's cell-finding config -- the search constraints that
parameterise a cell producer, plus region seeding and a survey progress readout."""

from __future__ import annotations

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

        # Depths are offsets from the tissue surface, negative being deeper, so
        # the spin boxes read the way the design doc writes them (-20 um to
        # -60 um) rather than as unsigned depths that get subtracted somewhere
        # else.
        self.nearDepthSpin = self._makeSpin(
            defaults.depth_range[0],
            minimum=-1e-3,
            maximum=0.0,
            step=5e-6,
            suffix="m",
            decimals=7,
        )
        self.farDepthSpin = self._makeSpin(
            defaults.depth_range[1],
            minimum=-1e-3,
            maximum=0.0,
            step=5e-6,
            suffix="m",
            decimals=7,
        )
        self.minHealthSpin = self._makeSpin(
            defaults.min_health,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            suffix="",
            decimals=2,
        )
        self.maxDensitySpin = self._makeSpin(
            defaults.max_cell_density,
            minimum=1.0,
            maximum=1e18,
            step=1e12,
            suffix="/m³",
            decimals=0,
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
    def _makeSpin(value, minimum, maximum, step, suffix, decimals):
        spin = Qt.QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        if suffix:
            spin.setSuffix(f" {suffix}")
        spin.setValue(value)
        return spin

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
            self.errorLabel.setText(str(exc))
            return None
        self.errorLabel.setText("")
        return constraints

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
