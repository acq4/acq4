"""Autopatch module: the operator-facing run window for the experiment
orchestration engine (acq4/experiment/). See autopatch-orchestration-design.md."""
from __future__ import annotations

import functools
import os

from acq4.experiment.actions.prompt import prompt
from acq4.experiment.actions.storage import create_data_dir
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.experiment.slice import RegionTooLarge, Slice
from acq4.experiment.tile_detector import make_tile_detector
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException
from acq4.util.InterfaceCombo import InterfaceCombo

from .cell_panel import CellPanel
from .context_factory import make_context_factory
from .example_protocols import install_example_protocols
from .progress_colors import ColorContext, brushesFor, legendFor
from .progress_overlay import Marker, ProgressOverlay
from .protocol_panel import ProtocolPanel
from .region_mirrors import CameraMirror, PinnedFrameMirror
from .region_panel import RegionPanel
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

        # A splitter, not a fixed box layout: Area 1 is a view of a whole slice,
        # and drawing a region in a strip the operator cannot enlarge is an
        # exercise in patience.
        leftCol = Qt.QSplitter(Qt.Qt.Vertical)
        leftCol.addWidget(self.area1Box)
        leftCol.addWidget(self.area2Box)
        # Area 1 is the view; Area 2 is four spin boxes and a readout.
        leftCol.setStretchFactor(0, 3)
        leftCol.setStretchFactor(1, 1)

        rightCol = Qt.QVBoxLayout()
        rightCol.addWidget(self.area3Box)
        rightCol.addWidget(self.area4Box)
        rightCol.addWidget(self.area5Box)
        rightColWidget = Qt.QWidget()
        rightColWidget.setLayout(rightCol)

        outer = Qt.QHBoxLayout()
        outer.addWidget(leftCol, 2)
        outer.addWidget(rightColWidget, 1)
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

        self.newSliceBtn = Qt.QPushButton("New slice")
        self.newSliceBtn.setToolTip(
            "Discard the current slice -- its regions, coverage, and queued "
            "cells -- and start a fresh one for newly mounted tissue."
        )
        self.regionPanel = RegionPanel()
        self.area1Box.layout().addWidget(self.newSliceBtn)
        self.area1Box.layout().addWidget(self.regionPanel)

        self._pinnedFrameMirror = PinnedFrameMirror(self.regionPanel.view)
        # The getter is closed over the manager alone, never over this window.
        # A bound self._cameraModuleWindow would give mirror -> window while
        # self._cameraMirror gives window -> mirror, and teardown() never drops
        # that attribute, so the pair would outlive teardown and be reclaimable
        # only by the cyclic collector -- the same shape as the exit segfault
        # this module's deterministic teardown was written to prevent.
        self._cameraMirror = CameraMirror(
            functools.partial(self._cameraModuleWindow, self.manager)
        )

        self._progressOverlay = ProgressOverlay(self.regionPanel.view)
        # id(cell) -> the last (x, y) global position known for it. Seeded from
        # cell.initialPosition and updated from sigPositionChanged payloads:
        # cell.position evaluates max(self._positions), which iterates a dict
        # the tracking worker writes, so reading it here is an intermittent
        # RuntimeError. Ids and plain tuples, never cells, for the same reason
        # every dict in cell_panel.py holds ids.
        self._cellPositions: dict[int, tuple] = {}

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
        # Whether Area 3's instruction band is currently carrying a message this
        # window's Area 1 handlers put there -- see _setRegionInstruction().
        self._regionInstruction = False
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
        self.regionPanel.sigAddRegionRequested.connect(self.addRegionHere)
        self.regionPanel.sigRegionsChanged.connect(self._onRegionsEdited)
        self.regionPanel.mirrorCheck.toggled.connect(self._onMirrorToggled)
        if self.manager is not None:
            # Both Area 1 mirrors resolve the Camera module through
            # _cameraModuleWindow, which reports None while that module is not
            # open -- so a mirror armed before the operator opens it binds to
            # nothing. Manager announces every module load and quit here, which
            # is the one event that can change that answer. Disconnected in
            # teardown(); a window built with no module (the headless/test mode)
            # has no manager to listen to.
            self.manager.sigModulesChanged.connect(self._onModulesChanged)
        self.searchPanel.sigConstraintsChanged.connect(self._onConstraintsChanged)
        self.statusPanel.sigInteractionLocked.connect(
            self.searchPanel.setInteractionLocked
        )
        self.statusPanel.sigInteractionLocked.connect(
            self.regionPanel.setInteractionLocked
        )
        self.statusPanel.sigStatusChanged.connect(self.regionPanel.setRunStatus)
        self.statusPanel.sigInteractionLocked.connect(
            self.cellPanel.setInteractionLocked
        )
        self.cellPanel.sigCellStateChanged.connect(self._onCellStateChanged)
        # A bound method, not a lambda: a lambda connected to a signal in this
        # module's panels reproducibly segfaults its test file about 40 tests
        # after the connect (see RegionPanel's own colour-source wiring).
        self.regionPanel.sigColorSourceChanged.connect(self._onColorSourceChanged)
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

    @staticmethod
    def _cameraModuleWindow(manager):
        """The Camera module's window under `manager`, or None if there is none.

        Not having one is ordinary -- a rig with the module unloaded, or a
        headless test -- and both mirrors treat it as nothing to do rather than
        as a failure.

        Asked of the loaded modules rather than of Manager.getModule alone,
        which loads a module that is not already open: this is reached from
        every mirror redraw, including the one behind "Add region here", and a
        button that adds a region must not also start the Camera module.

        Static, taking the manager as an argument, so that the Camera mirror can
        be handed a getter that holds no reference to this window -- see where
        it is constructed.
        """
        if manager is None:
            return None
        try:
            if "Camera" not in manager.listModules():
                return None
            return manager.getModule("Camera").window()
        except Exception:
            return None

    def _cameraWindow(self):
        """The Camera module's window, or None if there is not one."""
        return self._cameraModuleWindow(self.manager)

    def _onMirrorToggled(self, enabled: bool) -> None:
        """Turn the outline mirror on or off, saying so if there is nowhere to
        draw.

        A tick with no Camera module open is otherwise a silent no-op: the
        checkbox stays ticked, nothing appears anywhere, and nothing
        distinguishes that from a mirror that is broken. The message is
        accurate about what happens next -- _onModulesChanged() re-runs this
        handler when a module is opened, so the outlines really do appear then.
        """
        self._cameraMirror.setEnabled(enabled)
        if enabled and self._cameraWindow() is None:
            self._setRegionInstruction(
                "Mirror to Camera: no Camera module is open. The outlines will "
                "appear if one is opened."
            )
        else:
            self._setRegionInstruction("")

    def _onModulesChanged(self) -> None:
        """Re-resolve Area 1's two mirrors against the modules now loaded.

        Both of them find the Camera module once and keep the answer: the
        outline mirror at the moment the checkbox is ticked, the pinned-frame
        mirror at the moment a slice starts. Either can happen before the
        Camera module is open, and Manager emits this whenever that changes.

        Refuses once the window is torn down. teardown() waits on the
        orchestrator with the Qt event loop still pumping, so a module loaded in
        those seconds is announced while teardown is in progress, and re-binding
        then would leave the Camera module holding a closed session's graphics.
        """
        if self._tornDown:
            return
        # Re-runs the checkbox's own handler, which redraws the outlines against
        # whatever window there is now and raises or retracts its message.
        self._onMirrorToggled(self.regionPanel.mirrorCheck.isChecked())
        camera = self.cameraSelector.getSelectedObj()
        if self.slice is not None and camera is not None:
            self._bindPinnedFrames(camera)

    def _onRegionsEdited(self, regions) -> None:
        """Take Area 1's edited region list as the slice's regions.

        A wholesale swap, which is what makes this safe to do while a producer
        may be reading regions on the worker thread (see Slice.setRegions).

        A signal is not a permission check: Area 1's controls are gated on a
        slice existing, but arriving here without one must not raise on the GUI
        thread. The editing gate is read for the same reason -- RegionPanel
        locks every editing surface it owns, and this is the second line of that
        defence, since committing an edit while a producer may be reading the
        regions on the worker thread is what the gate exists to prevent. A torn
        down window refuses for a third: teardown() waits on the orchestrator
        with the Qt event loop still pumping, so an ROI drag released during
        that wait arrives here after the session it belongs to has ended.

        Area 1 is deliberately not redrawn from here on the accepted path: this
        arrives *from* the panel, and RegionPanel.setRegions() rebuilds every
        ROI, which would discard the very handle the operator is holding. A
        refused edit is the exception, and rebuilding is the point there: the
        ROI has to go back to the size the slice still holds.
        """
        if self._tornDown or self.slice is None or not self.regionPanel.isEditable():
            return
        try:
            self.slice.setRegions(regions)
        except RegionTooLarge as exc:
            # Refuse the whole edit rather than dropping the one region: a
            # survey that quietly ignores outlined tissue is the failure mode
            # this module keeps ruling out. Area 3's band takes the message --
            # it is guidance about a control, with no traceback to show.
            self._setRegionInstruction(str(exc))
            self.regionPanel.setRegions(self.slice.regions)
            return
        self._setRegionInstruction("")
        self._cameraMirror.setRegions(regions)
        self._refreshSurveyStats()

    def _setRegionInstruction(self, text: str) -> None:
        """Put Area 1's guidance in Area 3's band, or retract what it last put
        there.

        Area 1 has one guidance slot: a later message replaces an earlier one.
        Whether this window is currently using that slot is tracked rather than
        written straight through, because newSlice() writes into the same band
        for its own reason -- an unchosen storage directory -- and clearing
        Area 1's message must not erase guidance whose condition still holds.
        """
        if text:
            self._regionInstruction = True
            self.statusPanel.setInstruction(text)
        elif self._regionInstruction:
            self._regionInstruction = False
            self.statusPanel.clearInstruction()

    def _canStartSlice(self) -> bool:
        """Whether a slice can be started right now, reporting the reason
        through SearchPanel exactly as _startSlice() itself does.

        Split out so newSlice() can run this check before create_data_dir()
        commits to a new storage directory -- constructing the Slice remains
        _startSlice()'s job alone, called only once directory creation has
        already succeeded.

        A torn-down window can never start one again. teardown() waits on the
        orchestrator with the Qt event loop still pumping (see
        _stopAndReleaseOrchestrator), so New slice and Add region here stay
        clickable for as long as that wait lasts, and a slice built then would
        re-bind PinnedFrameMirror to the Camera module's long-lived ImagingCtrl
        with nothing left to release it: _tornDown is already True, so the
        closeEvent that follows returns early.
        """
        if self._tornDown:
            return False
        camera = self.cameraSelector.getSelectedObj()
        if camera is None:
            self.searchPanel.setError("Select a camera before starting a slice.")
            return False
        if self.searchPanel.constraints() is None:
            return False
        return True

    def _startSlice(self, dirHandle=None) -> bool:
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
        seeded by hand, which is all its button offers to do. `dirHandle` is
        the pass-through for that same reason: newSlice() has already created a
        directory by the time it calls here, while addRegionHere() calls here
        with none, which is what leaves its implicit slice's dirHandle at None.
        """
        if not self._canStartSlice():
            return False
        camera = self.cameraSelector.getSelectedObj()
        constraints = self.searchPanel.constraints()
        fov = self._cameraFov(camera)
        self.slice = Slice(fov=fov, constraints=constraints, dirHandle=dirHandle)
        self.searchPanel.setSliceReady(True)
        self.regionPanel.setSliceReady(True)
        # A fresh Slice has no regions, and an outline left from the last one is
        # a coordinate on tissue that may no longer be there.
        self.regionPanel.setRegions([])
        self._cameraMirror.setRegions([])
        # A fresh pg.ViewBox spans about a metre, and Area 1's units are global
        # metres, so an operator clicking in an empty view lands a vertex half a
        # metre out. Ten fields around where the camera is looking puts the
        # first click on tissue-sized coordinates; "roi" mode throughout, for
        # the same reason addRegionHere() uses it.
        self.regionPanel.setViewport(
            camera.globalCenterPosition("roi")[:2], (fov[0] * 10, fov[1] * 10)
        )
        self._bindPinnedFrames(camera)
        # There is a camera now, so retract the message above if it is up.
        self.searchPanel.setError("")
        return True

    def _bindPinnedFrames(self, camera) -> None:
        """Mirror `camera`'s pinned frames into Area 1's view.

        Bound here rather than at construction because this is the first point
        at which a camera is known to be selected, and both routes into a slice
        pass through it.

        Every path unbinds first, including the two that find nothing to bind
        to. Switching from a camera the Camera module has an interface for to
        one it does not -- or starting a slice after the Camera module has been
        closed -- would otherwise leave Area 1 mirroring the previous camera's
        frames: imagery of tissue that is no longer under the objective, with
        regions being drawn over it.
        """
        self._pinnedFrameMirror.unbind()
        window = self._cameraWindow()
        if window is None:
            return
        try:
            imagingCtrl = window.getInterfaceForDevice(camera.name()).imagingCtrl
        except (KeyError, AttributeError):
            return
        self._pinnedFrameMirror.bind(imagingCtrl)

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

        Its terminal disposition is suppressed instead, so finishing on the
        discarded tissue does not hand its coordinate back to Area 5 as a
        completed -- and therefore reusable -- cell. See Orchestrator.
        abandonCellInHand for exactly which orderings that covers, and the one
        it does not.

        The slice directory is created before anything is discarded. Creating it
        is the step that can fail -- an operator who has not chosen a storage
        directory is the likeliest first use of this button -- and a failure that
        has already thrown away their cells is worse than the failure itself.

        The camera/constraints check runs before that directory is even
        created, though: those are the likelier first-use failure, and an
        operator missing a camera should not have storage repointed into a
        fresh, empty Slice directory before finding that out.
        """
        if not self._canStartSlice():
            return
        try:
            dirHandle = create_data_dir(self.manager, level="Slice")
        except HelpfulException as exc:
            # Guidance, not a failure report: the operator has not chosen a
            # storage directory, and Area 3's band is where instructions go.
            # Narrowed to HelpfulException so a genuine programming error (a
            # missing manager, say) propagates instead of being reported as
            # storage guidance.
            #
            # The band is this handler's now, not Area 1's, so a later region
            # edit must not treat retracting its own message as licence to
            # retract this one (see _setRegionInstruction).
            self._regionInstruction = False
            self.statusPanel.setInstruction(str(exc))
            return
        if not self._startSlice(dirHandle=dirHandle):
            return
        self.cellPanel.clearCells()
        # Area 3's band names a cell and a failure from the tissue just
        # discarded above; left up, it would go on describing a coordinate
        # that no longer exists once the operator has physically swapped in
        # new tissue.
        self.statusPanel.clearError()
        # Whichever handler filled the band, what it was about went with the
        # tissue just discarded.
        self._regionInstruction = False
        self.statusPanel.clearInstruction()
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
            # Alongside clearQueue(), never inside it: this is the caller that
            # means "the tissue is gone". _onTissueMoved's rescan branch clears
            # the same queue meaning "the tissue moved", and the cell that lost
            # tracking there has to keep reporting its disposition -- that row is
            # the operator's session record.
            self.orchestrator.abandonCellInHand()
        self._refreshSurveyStats()

    def addRegionHere(self) -> None:
        """Add a search region of roughly 3x3 fields of view around the camera center.

        A region is a reasonable first action, so a slice comes into existence
        to hold it. Built directly rather than by way of newSlice(): that is the
        discard-everything path, and an operator who seeded cells by hand and
        then asked only for a region must not lose them. The shape seeded is
        whichever one Area 1's selector currently has picked.
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
        # Area 1 owns the shape; this button owns the placement. An ellipse is
        # inscribed in the same box, so both shapes cover the same 3x3 fields and
        # only the corners differ.
        shape = self.regionPanel.regionShape()
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        if shape == "polygon":
            # The same box, as a polygon: the button places a region of a known
            # size, and the shape selector says what kind. A four-vertex seed is
            # also the readiest thing to reshape into the outline actually
            # wanted, which is the point of choosing polygon at all.
            region = PolygonRegion(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
        else:
            regionClass = EllipseRegion if shape == "ellipse" else RectRegion
            region = regionClass(x0, y0, x1, y1)
        try:
            self.slice.addRegion(region)
        except RegionTooLarge as exc:
            # 3x3 fields is nine tiles whatever the field of view, so this
            # button cannot trip the slice's tile cap as it stands. Caught
            # anyway because a traceback raised out of a button's slot is not a
            # failure mode this window should have at all.
            self._setRegionInstruction(str(exc))
            return
        self.regionPanel.setRegions(self.slice.regions)
        self._cameraMirror.setRegions(self.slice.regions)
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

    def _onCellStateChanged(self) -> None:
        """Re-read the cell panel after a row or disposition changed."""
        self._syncCellPositions()
        self._refreshProgress()

    def _onColorSourceChanged(self, _key: str) -> None:
        """Redraw Area 1's markers and legend under the newly chosen source."""
        self._refreshProgress()

    def _syncCellPositions(self) -> None:
        """Seed a position for every cell that has none, and drop the departed.

        Reads cell.initialPosition, which __init__ assigns once and nothing
        mutates. Live updates arrive through sigPositionChanged instead.
        """
        known = set()
        for cell in self.cellPanel.cells():
            cellId = id(cell)
            known.add(cellId)
            if cellId not in self._cellPositions:
                position = getattr(cell, "initialPosition", None)
                if position is not None:
                    self._cellPositions[cellId] = (position[0], position[1])
        for departed in set(self._cellPositions) - known:
            del self._cellPositions[departed]

    def _colorContext(self) -> ColorContext:
        """Everything the colour sources may read, gathered in one pass.

        The slice-derived fields are None when there is no slice, which is
        ordinary: cells can be seeded by hand before one exists.
        """
        cells = self.cellPanel.cells()
        constraints = None if self.slice is None else self.slice.constraints
        return ColorContext(
            cellIds=[id(c) for c in cells],
            positions=dict(self._cellPositions),
            dispositions={id(c): self.cellPanel.disposition(c) for c in cells},
            attempted={id(c) for c in cells if self.cellPanel.isAttempted(c)},
            # getattr, not c.score, despite Task 1 declaring the attribute:
            # CellPanel accepts anything as a cell -- its own tests seed plain
            # object() rows -- so this window cannot assume every row's payload
            # is a Cell. This is a deliberate departure from the spec's §5.1
            # wording ("read cell.score plainly"), which was written about the
            # cross-repo dependency rather than about the panel's stub-tolerance.
            scores={id(c): getattr(c, "score", None) for c in cells},
            fov=None if self.slice is None else self.slice.fov,
            tileVolume=None if self.slice is None else self.slice.tileVolume(),
            maxCellDensity=None if constraints is None else constraints.max_cell_density,
            minHealth=None if constraints is None else constraints.min_health,
        )

    def _refreshProgress(self) -> None:
        """Redraw Area 1's markers and legend from current state."""
        if self._tornDown:
            return
        ctx = self._colorContext()
        key = self.regionPanel.colorSource()
        brushes = brushesFor(key, ctx)
        self._progressOverlay.setMarkers([
            Marker(
                self._cellPositions[cellId][0],
                self._cellPositions[cellId][1],
                brushes[cellId],
                cellId,
            )
            for cellId in ctx.cellIds
            if cellId in self._cellPositions
        ])
        self.regionPanel.setLegend(legendFor(key, ctx))

    def _refreshCoverage(self) -> None:
        """Shade the tiles still to be surveyed."""
        if self._tornDown or self.slice is None:
            self._progressOverlay.setCoverage([], (0.0, 0.0))
            return
        covered = set(self.slice.coveredTiles)
        todo = [tile for tile in self.slice.tileGrid() if tile not in covered]
        self._progressOverlay.setCoverage(todo, self.slice.fov)

    def _onRunStatus(self, status: str) -> None:
        """Refresh Area 2's survey readout when the run's status moves.

        Coverage advances on the orchestrator's worker thread, but this arrives
        via StatusPanel on the GUI thread, so re-reading the slice here is safe.
        """
        if status in ("surveying", "waiting"):
            self._refreshSurveyStats()
            self._refreshCoverage()
            self._refreshProgress()

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
                # Captured before clearQueue(), which is the one call that
                # makes pendingCells() report nothing at all.
                discarded = self.orchestrator.pendingCells()
                # After the answer, not before: a cell the operator seeds by
                # hand while the prompt is open is a coordinate in the same
                # moved tissue and goes with the rest.
                self.orchestrator.clearQueue()
                self.orchestrator.clearProducerExhausted()
                # Area 5's rows must match what the operator just agreed to
                # discard; an attempted cell keeps its row regardless -- it is
                # the session record, not a stale queued entry -- which is
                # discardCells()'s own job to enforce.
                self.cellPanel.discardCells(discarded)
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

        Also releases Area 1's two mirrors, whose items and signal connection
        live in the *Camera* module's window and imaging control -- objects that
        outlive this window, and would otherwise be left holding graphics
        belonging to a session that has ended.

        The mirrors are released *after* the orchestrator, not before, because
        stopping it means waiting on it with the Qt event loop still pumping
        (see _stopAndReleaseOrchestrator). The window is still up and every
        Area 1 control still connected for the length of that wait, so anything
        the operator clicks in it -- Mirror to Camera, the end of an ROI drag --
        lands while teardown is in progress. Releasing last is what makes those
        clicks harmless rather than a mirror re-armed after its own cleanup.
        `_tornDown` above closes the other half: it is set before the wait, so
        nothing clicked during it can start a slice or commit a region edit.

        Idempotent: safe to call more than once (e.g. once explicitly from
        Autopatch.quit() and again via closeEvent() when the operator closes
        the window directly).
        """
        if self._tornDown:
            return
        self._tornDown = True
        try:
            if self.orchestrator is not None:
                self._stopAndReleaseOrchestrator(self.orchestrator)
        finally:
            # In a finally because these are the releases that reach *outside*
            # this window: a raise while stopping the orchestrator would
            # otherwise leave the Camera module holding this session's outlines
            # and its imaging control still connected to a dead mirror.
            #
            # The manager goes first, and for the same reason the mirrors go
            # last: the manager outlives this window, so a connection left on it
            # would go on calling this window's handler at every later module
            # load or quit, re-arming the mirrors the next two lines release.
            # Dropping it here closes that off for good; anything announced
            # during the wait above was already refused by _onModulesChanged's
            # own torn-down check.
            if self.manager is not None:
                Qt.disconnect(self.manager.sigModulesChanged, self._onModulesChanged)
            self._pinnedFrameMirror.unbind()
            self._cameraMirror.clear()
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
