"""Autopatch module: the operator-facing run window for the experiment
orchestration engine (acq4/experiment/). See autopatch-orchestration-design.md."""
from __future__ import annotations

import os

from acq4.experiment.orchestrator import Orchestrator
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.InterfaceCombo import InterfaceCombo

from .cell_panel import CellPanel
from .context_factory import make_context_factory
from .protocol_panel import ProtocolPanel
from .status_panel import StatusPanel


class AutopatchWindow(Qt.QWidget):
    """The Autopatch run window: five labeled areas per the design doc.

    Areas 1/2 stay empty placeholders in P1; Areas 3/4/5 hold the real
    status/protocol/cell-queue content wired to a live Orchestrator.
    """

    def __init__(
        self,
        module: "Autopatch | None" = None,
        protocolDir: str | None = None,
        pipetteSelector=None,
        cameraSelector=None,
    ):
        super().__init__()
        self.module = module
        self.manager = module.manager if module is not None else None
        self.setWindowTitle("Autopatch")

        self.area1Box = Qt.QGroupBox("Area 1 — Slice && region")
        self.area2Box = Qt.QGroupBox("Area 2 — Cell finding")
        self.area3Box = Qt.QGroupBox("Area 3 — Status && actions")
        self.area4Box = Qt.QGroupBox("Area 4 — Protocol && params")
        self.area5Box = Qt.QGroupBox("Area 5 — Current cell")

        for box in (self.area1Box, self.area2Box, self.area3Box, self.area4Box, self.area5Box):
            box.setLayout(Qt.QVBoxLayout())

        leftCol = Qt.QVBoxLayout()
        leftCol.addWidget(self.area1Box)
        leftCol.addWidget(self.area2Box)

        rightCol = Qt.QVBoxLayout()
        rightCol.addWidget(self.area3Box)
        rightCol.addWidget(self.area4Box)
        rightCol.addWidget(self.area5Box)

        outer = Qt.QHBoxLayout()
        outer.addLayout(leftCol)
        outer.addLayout(rightCol)
        self.setLayout(outer)

        if protocolDir is None:
            if self.manager is None:
                raise ValueError(
                    "AutopatchWindow needs a `module` (for module.manager.configDir) "
                    "or an explicit `protocolDir`"
                )
            protocolDir = os.path.join(self.manager.configDir, "autopatch_protocols")
        self.protocolPanel = ProtocolPanel(protocolDir=protocolDir)
        self.area4Box.layout().addWidget(self.protocolPanel)

        self.pipetteSelector = (
            pipetteSelector if pipetteSelector is not None else InterfaceCombo(types=["pipette"])
        )
        self.cameraSelector = (
            cameraSelector if cameraSelector is not None else InterfaceCombo(types=["camera"])
        )
        self.area4Box.layout().addWidget(self.pipetteSelector)
        self.area4Box.layout().addWidget(self.cameraSelector)

        self.statusPanel = StatusPanel()
        self.area3Box.layout().addWidget(self.statusPanel)

        self.cellPanel = CellPanel(
            pipetteGetter=self.pipetteSelector.getSelectedObj,
            cameraGetter=self.cameraSelector.getSelectedObj,
        )
        self.area5Box.layout().addWidget(self.cellPanel)

        self.orchestrator = None
        # The pipette resolved from self.pipetteSelector at the moment Start was
        # last pressed (GUI thread). The orchestrator's contextFactory reads this
        # cached value rather than the selector widget, since _walk() calls the
        # factory from the orchestrator's worker thread -- see _resolvePipette().
        self._cachedPipette = None
        self.protocolPanel.sigProtocolLoaded.connect(self._onProtocolLoaded)

    def _resolvePipette(self) -> None:
        """Snapshot the currently-selected pipette on the GUI thread. Called at
        Start (before the orchestrator's worker thread starts running), so the
        in-flight run never reads InterfaceCombo's currentIndex()/interfaceMap
        off-thread. Re-resolved on every Start, so the selection may still
        change between runs."""
        self._cachedPipette = self.pipetteSelector.getSelectedObj()

    def _onProtocolLoaded(self, protocol) -> None:
        contextFactory = make_context_factory(
            pipetteGetter=lambda: self._cachedPipette,
            manager=self.manager,
            log=self.cellPanel.appendLog,
        )
        self.orchestrator = Orchestrator(
            protocol, manager=self.manager, contextFactory=contextFactory
        )
        self.statusPanel.bindOrchestrator(self.orchestrator, onStart=self._resolvePipette)
        self.cellPanel.bindOrchestrator(self.orchestrator)


class Autopatch(Module):
    moduleDisplayName = "Autopatch"
    moduleCategory = "Utilities"
    _instance = None

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        if Autopatch._instance is not None:
            Autopatch._instance.ui.raise_()
            Autopatch._instance.ui.activateWindow()
            Qt.QTimer.singleShot(0, self.quit)
            return
        Autopatch._instance = self
        self.ui = AutopatchWindow(self)
        manager.declareInterface(name, ["autopatchModule"], self)
        self.ui.show()

    def window(self):
        return self.ui

    def quit(self, fromUi=False):
        if Autopatch._instance is self:
            Autopatch._instance = None
        if hasattr(self, "ui") and not fromUi:
            self.ui.close()
        super().quit()
