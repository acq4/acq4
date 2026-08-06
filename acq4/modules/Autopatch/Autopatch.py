"""Autopatch module: the operator-facing run window for the experiment
orchestration engine (acq4/experiment/). See autopatch-orchestration-design.md."""
from __future__ import annotations

import os

from acq4.experiment.actions.prompt import prompt
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.search_region import EllipseRegion, RectRegion
from acq4.experiment.slice import Slice
from acq4.experiment.tile_detector import make_tile_detector
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.InterfaceCombo import InterfaceCombo

from .cell_panel import CellPanel
from .context_factory import make_context_factory
from .example_protocols import install_example_protocols
from .protocol_panel import ProtocolPanel
from .search_panel import SearchPanel
from .status_panel import StatusPanel


class AutopatchWindow(Qt.QWidget):
    """The Autopatch run window: five labeled areas per the design doc.

    Area 1 starts a slice, Area 2 configures the cell search over it, and
    Areas 3/4/5 hold the status/protocol/cell-queue content wired to a live
    Orchestrator.
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
            pipetteSelector
            if pipetteSelector is not None
            else InterfaceCombo(types=["patchpipette"])
        )
        self.cameraSelector = (
            cameraSelector if cameraSelector is not None else InterfaceCombo(types=["camera"])
        )
        self.area4Box.layout().addWidget(self.pipetteSelector)
        self.area4Box.layout().addWidget(self.cameraSelector)

        self.statusPanel = StatusPanel()
        self.area3Box.layout().addWidget(self.statusPanel)

        # Area 1 holds only New slice: region graphics and the progress heatmap
        # are Area 1's remaining content and are not built here.
        self.newSliceBtn = Qt.QPushButton("New slice")
        self.newSliceBtn.setToolTip(
            "Discard the current slice -- its regions, coverage, and queued "
            "cells -- and start a fresh one for newly mounted tissue."
        )
        self.area1Box.layout().addWidget(self.newSliceBtn)

        self.searchPanel = SearchPanel()
        self.area2Box.layout().addWidget(self.searchPanel)

        self.cellPanel = CellPanel(
            pipetteGetter=self.pipetteSelector.getSelectedObj,
            cameraGetter=self.cameraSelector.getSelectedObj,
        )
        self.area5Box.layout().addWidget(self.cellPanel)

        self.orchestrator = None
        # The pipette resolved from self.pipetteSelector at the moment Start was
        # last pressed (GUI thread). The orchestrator's contextFactory reads this
        # cached value rather than the selector widget, since the factory is
        # called from the orchestrator's worker thread -- see _onStartRun().
        self._cachedPipette = None
        # The tissue currently under the objective, or None before the operator
        # has started one. A Slice outlives individual runs: it holds the
        # regions, the coverage every producer made from it shares, and the
        # search constraints. Replaced only by newSlice().
        self.slice = None
        # Camera and scope resolved from cameraSelector at the moment Start was
        # last pressed, for the same reason as _cachedPipette: the detector runs
        # on the orchestrator's worker thread and must not read a selector.
        self._cachedCamera = None
        self._cachedScope = None
        self._tornDown = False
        self.protocolPanel.sigProtocolLoaded.connect(self._onProtocolLoaded)
        # Area 4 (the protocol picker/Reload) must not be usable while a
        # run is in flight; StatusPanel derives this from whichever orchestrator
        # it's currently bound to, so this connection is made once here rather
        # than re-wired per protocol load. A direct bound-method connection
        # (not a lambda closing over self/the window) so this permanent,
        # never-disconnected wiring can't turn into a window<->statusPanel
        # reference cycle -- exactly what bindOrchestrator/unbindOrchestrator
        # elsewhere are careful to avoid.
        self.statusPanel.sigInteractionLocked.connect(self.protocolPanel.setInteractionLocked)
        self.newSliceBtn.clicked.connect(self.newSlice)
        self.searchPanel.sigAddRegionRequested.connect(self.addRegionHere)
        self.searchPanel.sigConstraintsChanged.connect(self._onConstraintsChanged)
        self.statusPanel.sigInteractionLocked.connect(
            self.searchPanel.setInteractionLocked
        )
        # Coverage advances on the worker thread as the producer images tiles, so
        # the readout is refreshed off a status change rather than polled. Routed
        # through StatusPanel, not connected to the orchestrator directly: the
        # orchestrator is a parentless QObject and a connection from it to this
        # window would give it a reference back, rebuilding the cycle
        # bindOrchestrator/unbindOrchestrator exist to avoid. StatusPanel is in
        # this window's widget tree, so this wiring is made once and never needs
        # re-wiring per protocol load.
        self.statusPanel.sigStatusChanged.connect(self._onRunStatus)
        # ProtocolPanel selects (and thus loads) a protocol as soon as its own
        # constructor's initial scan populates the combo -- before the
        # `sigProtocolLoaded` connection above exists, since that scan runs
        # inside `ProtocolPanel(protocolDir=protocolDir)` above, several lines
        # before this window finishes wiring itself up. That first emission
        # therefore reaches no slot and is lost. Replay it explicitly, now
        # that every panel this handler touches (cellPanel, statusPanel) is
        # built and the connection is live, so an operator who opens the
        # window and presses Start immediately still gets a run.
        if self.protocolPanel.protocolFile is not None:
            self._onProtocolLoaded(self.protocolPanel.protocolFile)

    def _startSlice(self) -> bool:
        """Install a fresh Slice for the tissue under the objective.

        Returns whether one was created: a slice needs the camera's field of
        view and a valid set of search constraints, and either being missing
        leaves self.slice exactly as it was rather than installing a half-built
        one. The camera-less case reports itself through SearchPanel; invalid
        constraints have already reported themselves there.

        Shared by newSlice() and addRegionHere(), so the construction lives in
        one place -- but only the construction. Discarding the previous slice's
        queued cells belongs to newSlice() alone: addRegionHere() creating the
        slice that will hold its region must not throw away cells the operator
        seeded by hand, which is all its button offers to do.
        """
        camera = self.cameraSelector.getSelectedObj()
        if camera is None:
            self.searchPanel.setError("Select a camera before starting a slice.")
            return False
        constraints = self.searchPanel.constraints()
        if constraints is None:
            return False
        self.slice = Slice(fov=self._cameraFov(camera), constraints=constraints)
        # There is a camera now, so retract the message above if it is up.
        self.searchPanel.setError("")
        return True

    def newSlice(self) -> None:
        """Start a fresh slice, discarding the current one and everything on it.

        Regions, coverage, and search constraints go with the old slice, and so
        do the queued cells: a Cell is a coordinate in tissue, and tissue that
        has been swapped makes every one of those coordinates a place not to
        drive a pipette. The per-cell data already written under the old slice
        directory is the durable record; Area 5's list is a working queue.

        What this deliberately does not do is stop the cell already in flight.
        The queue behind it and Area 5's list are discarded, but that cell runs
        to completion on the tissue it was found in -- it is being worked right
        now, and yanking a pipette out mid-protocol is its own hazard. The
        operator who has physically swapped the tissue presses Stop for that.
        """
        if not self._startSlice():
            return
        self.cellPanel.clearCells()
        if self.orchestrator is not None:
            # Detached before the queue is cleared, not after: a refill still
            # in flight on the worker thread reads the producer and enqueues
            # its result as two separate steps (see Orchestrator._refillQueue),
            # so clearing the queue first leaves a window where that in-flight
            # refill can still land one more old-slice tile in it after the
            # operator has already declared the tissue gone.
            self.orchestrator.setCellProducer(None)
            # clearCells() only drops the panel's own bookkeeping; the
            # orchestrator's deque is a separate strong reference to the same
            # cells and would keep handing them to the protocol.
            self.orchestrator.clearQueue()
        self._refreshSurveyStats()

    def addRegionHere(self) -> None:
        """Add a search region of roughly 3x3 fields of view around the camera center.

        A region is a reasonable first action, so a slice comes into existence
        to hold it. Built directly rather than by way of newSlice(): that is the
        discard-everything path, and an operator who seeded cells by hand and
        then asked only for a region must not lose them. The shape seeded is
        whichever one Area 2's selector currently has picked.
        """
        if self.slice is None and not self._startSlice():
            return
        camera = self.cameraSelector.getSelectedObj()
        if camera is None:
            return
        fov_w, fov_h = self._cameraFov(camera)
        # "roi" mode throughout: the field the camera actually images is what a
        # tile covers, and globalCenterPosition defaults to "sensor", which is
        # off-center for a cropped camera ROI.
        cx, cy = camera.globalCenterPosition("roi")[:2]
        w, h = fov_w * 3, fov_h * 3
        # Area 2 owns the shape; this button owns the placement. An ellipse is
        # inscribed in the same box, so both shapes cover the same 3x3 fields and
        # only the corners differ.
        regionClass = (
            EllipseRegion
            if self.searchPanel.regionShape() == "ellipse"
            else RectRegion
        )
        self.slice.addRegion(
            regionClass(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        )
        self._refreshSurveyStats()

    @staticmethod
    def _cameraFov(camera) -> tuple[float, float]:
        """The camera's imaged field width and height, in global metres."""
        _, _, w, h = camera.getBoundary(globalCoords=True, mode="roi")
        return abs(w), abs(h)

    def _onConstraintsChanged(self, constraints) -> None:
        # None means the spinboxes do not currently describe a valid search
        # (SearchPanel already shows why); leave the live slice on its last
        # good constraints rather than tearing them down mid-edit.
        if constraints is not None and self.slice is not None:
            self.slice.setConstraints(constraints)

    def _refreshSurveyStats(self) -> None:
        if self.slice is None:
            self.searchPanel.setSurveyStats(0, 0, 0.0)
        else:
            self.searchPanel.setSurveyStats(*self.slice.surveyStats())

    def _onRunStatus(self, status: str) -> None:
        """Refresh Area 2's survey readout when the run's status moves.

        Coverage advances on the orchestrator's worker thread, but this arrives
        via StatusPanel on the GUI thread, so re-reading the slice here is safe.
        """
        if status in ("surveying", "waiting"):
            self._refreshSurveyStats()

    def _onTissueMoved(self, cell, ctx, reason: str) -> None:
        """ExecutionContext.tissue_moved, cell-bound by the context factory.

        Runs on the orchestrator's worker thread, mid-cell. Never returns: both
        answers end the cell.

        The operator decides, because a rescan is destructive in its own way --
        it re-images ground already searched and can re-detect cells already
        worked. "Rescan the slice" is offered first and is therefore what a
        headless run picks: driving a pipette to a coordinate known to be stale
        is a hardware risk, while patching a cell twice is a data-hygiene cost,
        so the cheaper mistake goes first.
        """
        pending = len(self.orchestrator.pendingCells()) if self.orchestrator else 0
        answer = prompt(
            ctx,
            message=(
                f"Cell tracking could not re-find this cell ({reason}).\n"
                "The tissue may have moved. Rescanning discards the "
                f"{pending} cell(s) still queued and re-images this region; "
                "cells already patched may be found again."
            ),
            title="Tissue may have moved",
            choices=("Rescan the slice", "Skip this cell only"),
        )
        if answer == "Rescan the slice":
            if self.slice is not None:
                self.slice.forceRescan(cell.position, self.cellPanel.isAttempted)
            if self.orchestrator is not None:
                # After the answer, not before: a cell the operator seeds by
                # hand while the prompt is open is a coordinate in the same
                # moved tissue and goes with the rest.
                self.orchestrator.clearQueue()
                self.orchestrator.clearProducerExhausted()
        # Area 2's survey readout is deliberately not refreshed here: this is the
        # worker thread, and _refreshSurveyStats touches widgets. The next status
        # change routes through _onRunStatus on the GUI thread and picks it up.
        ctx.next_cell()

    def _onStartRun(self) -> None:
        """Snapshot GUI-thread-only state and install the cell producer at Start.

        Runs on the GUI thread before the orchestrator's worker thread starts,
        so the in-flight run never reads InterfaceCombo's
        currentIndex()/interfaceMap off-thread. Re-resolved on every Start, so
        the selection and the slice may both change between runs.
        """
        self._cachedPipette = self.pipetteSelector.getSelectedObj()
        self._cachedCamera = self.cameraSelector.getSelectedObj()
        self._cachedScope = None
        if self._cachedCamera is not None:
            self._cachedScope = self._cachedCamera.scopeDev
        self._installCellProducer()

    def _installCellProducer(self) -> None:
        """Give the orchestrator a producer for the current slice, or none.

        Cleared rather than left stale whenever a survey is not possible: no
        slice, no region, or no camera means the run is a plain drain of the
        cells the operator seeded by hand, and a producer left over from a
        previous Start would otherwise keep surveying tissue that is gone.
        """
        if self.orchestrator is None:
            return
        canSurvey = (
            self.slice is not None
            and self.slice.regions
            and self._cachedCamera is not None
            and self._cachedScope is not None
        )
        if not canSurvey:
            self.orchestrator.setCellProducer(None)
            return
        detector = make_tile_detector(
            camera=self._cachedCamera, scope=self._cachedScope, manager=self.manager
        )
        self.orchestrator.setCellProducer(self.slice.makeCellProducer(detector))

    def _onProtocolLoaded(self, protocolFile) -> None:
        # Loading a second protocol must not abandon a still-live Orchestrator:
        # left running, it would keep calling cellPanel.appendLog/onLogAction
        # directly (bound into its own contextFactory closure, not through an
        # Orchestrator signal -- see CellPanel.unbindOrchestrator's docstring
        # for the one path it deliberately doesn't sever), writing into this
        # new session's Area 5/Area 3 out from under it, and leaving two
        # worker threads eligible to drive the same pipette.
        if self.orchestrator is not None:
            self._stopAndReleaseOrchestrator(self.orchestrator)
        contextFactory = make_context_factory(
            pipetteGetter=lambda: self._cachedPipette,
            manager=self.manager,
            log=self.cellPanel.appendLog,
            onLogAction=self.cellPanel.onLogAction,
            tissueMoved=self._onTissueMoved,
        )
        self.orchestrator = Orchestrator(
            protocolFile, manager=self.manager, contextFactory=contextFactory
        )
        # Belt-and-suspenders on top of teardown(): parenting the orchestrator
        # (a QObject, not otherwise part of the widget tree) to this window
        # means Qt's own parent/child cascade destroys it deterministically,
        # on the GUI thread, when the window is destroyed -- rather than
        # leaning solely on teardown() having already dropped every reference.
        self.orchestrator.setParent(self)
        self.statusPanel.bindOrchestrator(
            self.orchestrator, self.cellPanel, onStart=self._onStartRun
        )
        self.cellPanel.bindOrchestrator(self.orchestrator)

    @staticmethod
    def _stopAndReleaseOrchestrator(orchestrator) -> None:
        """Stop `orchestrator` and unparent it from the window, bounded so a
        stuck action can't hang the caller forever.

        Shared by teardown() (window close) and _onProtocolLoaded() (loading
        a second protocol over a still-live one) so both paths release an
        outgoing orchestrator the same way: any outcome of the wait
        (finished, stopped, timed out) is fine here, since the caller is
        about to drop every reference to `orchestrator` regardless.

        This runs on the GUI thread, so the wait must pump the Qt event loop
        (updates=True) rather than parking on it: a worker still finishing up
        via run_in_gui_thread (as run_task does) cannot complete while the
        GUI thread isn't pumping, which would turn the 5s timeout from a
        backstop into a deadlock.
        """
        orchestrator.stop()
        try:
            orchestrator.wait(timeout=5.0, updates=True)
        except Exception:
            pass
        # The producer closes over the camera and scope devices and over a
        # Slice this window may be about to replace. Leaving it installed on an
        # orchestrator the window has stopped managing keeps all of that
        # reachable from an object nothing is looking after any more.
        orchestrator.setCellProducer(None)
        # The orchestrator's context factory closes over this window (to read
        # the cached pipette) and over cellPanel (to log), so as long as the
        # orchestrator is alive it keeps both alive too -- fine on its own,
        # but setParent(self) in _onProtocolLoaded also makes Qt's parent/
        # child bookkeeping keep the orchestrator alive for as long as this
        # window is, which would turn that one-way dependency back into a
        # cycle. Unparenting here breaks that, so dropping the last Python
        # reference is enough for plain refcounting to free everything.
        orchestrator.setParent(None)

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
            self._stopAndReleaseOrchestrator(self.orchestrator)
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
