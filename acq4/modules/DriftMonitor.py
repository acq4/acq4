import pyqtgraph as pg

from acq4.devices.Pipette.tracker import DriftMonitorWidget
from acq4.modules.Module import Module
from acq4.util import Qt


class DriftMonitor(Module):
    """Monitor pipette tip drift over time using the camera imager."""

    moduleDisplayName = "Drift Monitor"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)

        self.monitor = None

        self.win = Qt.QSplitter()
        self.win.setWindowTitle("Drift Monitor")

        ctrl = pg.LayoutWidget()
        self.win.addWidget(ctrl)

        # Pipette selection
        ctrl.addWidget(Qt.QLabel("Pipettes:"), row=0, col=0)
        self._pipetteGroup = Qt.QWidget()
        self._pipetteLayout = Qt.QVBoxLayout()
        self._pipetteLayout.setContentsMargins(0, 0, 0, 0)
        self._pipetteGroup.setLayout(self._pipetteLayout)
        ctrl.addWidget(self._pipetteGroup, row=1, col=0)
        self._checkboxes = {}  # name -> QCheckBox

        self.applyCheck = Qt.QCheckBox("Apply corrections")
        self.applyCheck.setChecked(True)
        ctrl.addWidget(self.applyCheck, row=2, col=0)

        self.params = pg.parametertree.Parameter.create(
            name="params",
            type="group",
            children=[
                dict(
                    name="interval",
                    type="float",
                    value=2.0,
                    suffix="s",
                    siPrefix=True,
                    limits=[0.1, None],
                    step=0.5,
                ),
            ],
        )
        ptree = pg.parametertree.ParameterTree()
        ptree.setParameters(self.params)
        ctrl.addWidget(ptree, row=3, col=0)

        self.startBtn = Qt.QPushButton("Start")
        self.startBtn.setCheckable(True)
        ctrl.addWidget(self.startBtn, row=4, col=0)

        self.resetBtn = Qt.QPushButton("Reset")
        ctrl.addWidget(self.resetBtn, row=5, col=0)

        # Right-side placeholder; replaced by DriftMonitorWidget on first start
        self._plotArea = Qt.QWidget()
        self._plotLayout = Qt.QVBoxLayout()
        self._plotLayout.setContentsMargins(0, 0, 0, 0)
        self._plotArea.setLayout(self._plotLayout)
        self.win.addWidget(self._plotArea)

        self.startBtn.toggled.connect(self._startToggled)
        self.applyCheck.toggled.connect(self._applyToggled)
        self.resetBtn.clicked.connect(self._reset)

        manager.interfaceDir.sigInterfaceListChanged.connect(self._updatePipetteList)
        self._updatePipetteList(["pipette"])

        self.win.show()

    def _updatePipetteList(self, types):
        if "pipette" not in types:
            return
        current = set(self._checkboxes)
        found = set(self.manager.listInterfaces("pipette"))

        for name in found - current:
            cb = Qt.QCheckBox(name)
            cb.setChecked(True)
            self._pipetteLayout.addWidget(cb)
            self._checkboxes[name] = cb

        for name in current - found:
            cb = self._checkboxes.pop(name)
            self._pipetteLayout.removeWidget(cb)
            cb.deleteLater()

        self._updateStartEnabled()

    def _selectedTrackers(self):
        trackers = []
        for name, cb in self._checkboxes.items():
            if cb.isChecked():
                trackers.append(self.manager.getDevice(name).tracker)
        return trackers

    def _updateStartEnabled(self):
        has_selection = any(cb.isChecked() for cb in self._checkboxes.values())
        self.startBtn.setEnabled(has_selection and not self.startBtn.isChecked())
        if not self._checkboxes:
            self.startBtn.setToolTip("No pipette devices found")
        elif not has_selection:
            self.startBtn.setToolTip("Select at least one pipette")
        else:
            self.startBtn.setToolTip("")

    def _startToggled(self, start):
        if start:
            trackers = self._selectedTrackers()
            if not trackers:
                self.startBtn.setChecked(False)
                return

            # Replace monitor widget with one built for the current selection
            if self.monitor is not None:
                self.monitor.stop()
                self._plotLayout.removeWidget(self.monitor)
                self.monitor.deleteLater()

            self.monitor = DriftMonitorWidget(trackers, applyCorrections=self.applyCheck.isChecked())
            self._plotLayout.addWidget(self.monitor)

            for cb in self._checkboxes.values():
                cb.setEnabled(False)

            self.monitor.start(interval_ms=int(self.params["interval"] * 1000))
            self.startBtn.setText("Stop")
            self.startBtn.setEnabled(True)
        else:
            if self.monitor is not None:
                self.monitor.stop()
            for cb in self._checkboxes.values():
                cb.setEnabled(True)
            self._updateStartEnabled()
            self.startBtn.setText("Start")

    def _applyToggled(self, apply):
        if self.monitor is not None:
            self.monitor.applyCorrections = apply

    def _reset(self):
        if self.monitor is not None:
            self.monitor.reset()

    def quit(self):
        if self.monitor is not None:
            self.monitor.stop()
        Module.quit(self)
