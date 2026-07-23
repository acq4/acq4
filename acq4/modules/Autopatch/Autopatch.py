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
from .example_protocols import install_example_protocols
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
        # First-run convenience: seed the protocol dir with the bundled example
        # protocols (never overwriting a file that's already there) before the
        # picker below lists its contents.
        install_example_protocols(protocolDir)
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
        self._tornDown = False
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
        # Belt-and-suspenders on top of teardown(): parenting the orchestrator
        # (a QObject, not otherwise part of the widget tree) to this window
        # means Qt's own parent/child cascade destroys it deterministically,
        # on the GUI thread, when the window is destroyed -- rather than
        # leaning solely on teardown() having already dropped every reference.
        self.orchestrator.setParent(self)
        self.statusPanel.bindOrchestrator(self.orchestrator, onStart=self._resolvePipette)
        self.cellPanel.bindOrchestrator(self.orchestrator)

    def teardown(self) -> None:
        """Break the Orchestrator/Cell QObject cycle deterministically.

        Without this, the orchestrator and seeded Cell objects are parentless
        QObjects cross-wired to the window's panels via Qt signal/slot
        connections -- a reference cycle only Python's cyclic GC can reclaim,
        and that collector may run non-deterministically (possibly off the GUI
        thread), tearing down live QObjects outside Qt's safe teardown path and
        crashing on exit. Calling this before the window is destroyed stops the
        orchestrator and severs every one of those connections up front, so the
        remaining objects are plain refcounted and go away immediately.

        Idempotent: safe to call more than once (e.g. once explicitly from
        Autopatch.quit() and again via closeEvent() when the operator closes
        the window directly).
        """
        if self._tornDown:
            return
        self._tornDown = True
        if self.orchestrator is not None:
            self.orchestrator.stop()
            try:
                # Bounded wait so a stuck action can't hang teardown forever;
                # any outcome (finished, stopped, timed out) is fine here since
                # we are about to drop every reference to the orchestrator
                # regardless.
                self.orchestrator.wait(timeout=5.0)
            except Exception:
                pass
            # The orchestrator's context factory closes over this window (to
            # read the cached pipette) and over cellPanel (to log), so as long
            # as the orchestrator is alive it keeps both alive too -- fine on
            # its own, but setParent(self) above also makes Qt's parent/child
            # bookkeeping keep the orchestrator alive for as long as this
            # window is, which would turn that one-way dependency back into a
            # cycle. Unparenting here breaks that, so dropping the reference
            # below is enough for plain refcounting to free everything.
            self.orchestrator.setParent(None)
        self.statusPanel.unbindOrchestrator()
        self.cellPanel.unbindOrchestrator()
        self.cellPanel.clearCells()
        self.orchestrator = None

    def closeEvent(self, event) -> None:
        self.teardown()
        super().closeEvent(event)


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
        if hasattr(self, "ui"):
            self.ui.teardown()
            if not fromUi:
                self.ui.close()
        super().quit()
