from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acq4.devices.PatchPipette import PatchPipette
from acq4.logging_config import get_logger
from acq4.util.task import Stopped, check_stop, asynch_with_qt_signals, set_state, sleep, synch
from acq4.util.task import run_in_gui_thread
from acq4.util.imaging.sequencer import run_image_sequence
from ..TaskRunner import TaskRunner
from ...Manager import Manager
from ...util.DataManager import DirHandle

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


class Autopatcher:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window
        # Whether the current demo has worked through at least one cell. Once the
        # queued cell list is exhausted, the "find more cells" option decides
        # whether to run detection for new cells or stop the demo.
        self._hasWorkedCell = False

    def _handleAutopatchDemoFinish(self, fut):
        win = self._window
        win.sigWorking.emit(False)
        win.ui.reuseLastCellBtn.setEnabled(win._cell is not None or bool(win._ranked_cells))

    @asynch_with_qt_signals
    def _autopatchDemo(self):
        win = self._window
        win.sigWorking.emit(win.ui.autopatchDemoBtn)
        self._hasWorkedCell = False
        # Start each run surveying the region from scratch; the ROI persists.
        win._surveyRegion.reset()
        ppip: PatchPipette = win.patchPipetteDevice
        man = win.module.manager
        data_manager = run_in_gui_thread(man.getModule, "Data Manager")
        multipatch_win = run_in_gui_thread(man.getModule, 'MultiPatch').win
        demo_dir = self._makeValidDemoDir()
        man.setCurrentDir(demo_dir)
        synch(win.cameraDevice.scopeDev.findSurfaceDepth)(win.cameraDevice)
        try:
            while True:
                # Decide whether there's another cell to work on before creating a
                # cell folder, cleaning the pipette, or clearing the patch log, so
                # the demo stops cleanly instead of setting up a nonexistent cell.
                if self._outOfCells():
                    set_state("Autopatch: reached end of cell list; stopping")
                    return
                cell_dir = run_in_gui_thread(data_manager.createNewFolder, "Cell")
                try:
                    started_clean = ppip.isTipClean()
                    if not started_clean:
                        set_state("Autopatch: cleaning pipette")
                        try:
                            ppip.setState("clean", nextState="bath").wait(timeout=600)
                        except Exception:
                            set_state("Clean is unsafe to undo; quitting demo")
                            logger.exception("Error during pipette clean - quitting autopatch demo")
                            return
                        if not ppip.isTipClean():
                            set_state("Pipette still not clean after clean state; quitting demo")
                            return
                        win.scopeDevice.moveDip().wait()

                    cell = self._autopatchFindCell()
                    if cell is None:
                        set_state("No cells found; quitting demo")
                        return
                    set_state("Autopatch: cell found")
                    ppip.newPatchAttempt()
                    run_in_gui_thread(multipatch_win.ui.recordBtn.setChecked, True)
                    set_state("Autopatch: go home before find surface")
                    ppip.pipetteDevice.goHome("fast").wait()

                    set_state("Autopatch: find surface above target")
                    synch(win.cameraDevice.scopeDev.findSurfaceDepth)(win.cameraDevice)

                    set_state("Autopatch: finding pipette tip")
                    synch(ppip.pipetteDevice.goAboveTarget)("fast")
                    ppip.clampDevice.autoPipetteOffset()
                    win.pipetteDevice.iterativelyFindTip()

                    # move 50 um up for sonication
                    pip_pos = ppip.pipetteDevice.globalPosition()
                    next_pos = [pip_pos[0], pip_pos[1], pip_pos[2] + 50e-6]
                    f1 = win.cameraDevice.moveCenterToGlobal(
                        next_pos, "fast", name="move focus to watch sonication"
                    )
                    f2 = ppip.pipetteDevice.moveToGlobalNoPlanning(
                        next_pos, 'fast', name="move pipette farther from slice for sonication"
                    )
                    f1.wait()
                    f2.wait()

                    set_state("Quick clean")
                    start_pressure = ppip.pressureDevice.getPressure()
                    ppip.pressureDevice.setPressure(source='regulator', pressure=50e3)
                    ppip.sonicatorDevice.doProtocol("quick clean")
                    set_state("Autopatch: expel ACSF after sonication")
                    sleep(4)
                    ppip.pressureDevice.setPressure(source='regulator', pressure=start_pressure)

                    set_state("Autopatch: go approach")
                    ppip.pipetteDevice.goApproach("fast").wait()
                    try:
                        set_state("Autopatch: patch cell")
                        logger.warning("Autopatch: Start cell patching")
                        state = self._autopatchCellPatch(cell)
                    except Exception:
                        logger.exception("Autopatch: Exception during cell patching")
                        raise

                    logger.warning(f"Autopatch: Cell patching finished: {state}")
                    if state != "whole cell":
                        logger.warning("Autopatch: Next cell!")
                        continue
                    cell_dir.setInfo({'important': True})
                    set_state("Autopatch: Whole cell; running task")
                    self._autopatchRunTaskRunner()

                    set_state("Autopatch: Taking cell images")
                    win.scopeDevice.loadPreset('GFP')
                    self._saveStack("patched GFP cellfie")
                    # win.scopeDevice.loadPreset('tdTomato')
                    # self._saveStack("patched tdTomato cellfie")
                    win.scopeDevice.loadPreset('brightfield')
                    ppip.pipetteDevice.focusTarget('slow').wait()

                    # set_state("Autopatch: resealing")
                    # ppip.setState("reseal").wait()
                    # self._saveStack("resealed nucleus")
                    #
                    # # start nucleus collection
                    # homeFut = ppip.setState("home with nucleus")
                    #
                    # check on the resealed cell
                    # win.scopeDevice.loadPreset('GFP')
                    # win.cameraDevice.moveCenterToGlobal(
                    #     cell.position, "fast", name="center on resealed cell"
                    # ).wait()
                    # self._saveStack("cell without nucleus")
                    # ppip.pipetteDevice.focusTip('slow').wait()
                    # homeFut.wait()

                    # collect the nucleus
                    # TODO once we have motion planning
                    # ppip.setState("collect").wait()
                    # ppip.pipetteDevice.goAboveTarget("fast").wait()
                    # self._saveStack("post-collection")

                    ppip.pipetteDevice.goHome().wait()
                    ppip.setState("bath")

                except Stopped:
                    raise
                except Exception:
                    logger.exception("Error during protocol:")
                    continue
                finally:
                    man.setCurrentDir(cell_dir.parent())
                    run_in_gui_thread(multipatch_win.ui.recordBtn.setChecked, False)
        finally:
            man.setCurrentDir(demo_dir.parent())

    def _makeValidDemoDir(self) -> DirHandle:
        man = self._window.module.manager
        parent = man.getCurrentDir()
        inappropriate_parents = ("autopatchdemo", "cell")
        while any(name in parent.name().lower() for name in inappropriate_parents):
            parent = parent.parent()
        return parent.mkdir('AutopatchDemo', autoIncrement=True)

    def _autopatchCellPatch(self, cell):
        win = self._window
        ppip = win.patchPipetteDevice
        ppip.setState("approach", startANewCell=False)
        # detect_finished = False
        while True:
            state = ppip.getState().stateName
            # remove? seal state already has this (and this is colliding with seal's move)
            # if state not in ("approach", "cell detect", "contact cell", "seal", "cell attached", "break in"):
            #     if not detect_finished:
            #         win.cameraDevice.moveCenterToGlobal(
            #             cell.position, "fast", name="center on cell during patching"
            #         ).wait()
            #         detect_finished = True
            if state in ("whole cell", "bath", "broken", "fouled"):
                set_state(f"Exiting patch loop - ended in state {state}")
                break
            sleep(0.1)
        return state

    def _outOfCells(self) -> bool:
        """Whether the queued cell list is exhausted and we shouldn't look for more.

        True once we've worked through at least one cell, the unranked list is
        empty, and the user hasn't opted into detecting new cells. Re-detecting in
        that case would (in mock mode) just repeat the same cells; this lets the
        demo stop before starting work on a nonexistent cell.
        """
        win = self._window
        return (
            not win._unranked_cells
            and self._hasWorkedCell
            and not win.ui.autoFindMoreCellsCheck.isChecked()
        )

    def _autopatchFindCell(self):
        win = self._window
        # Keep imaging survey tiles until one yields a cell. An empty field of
        # view is the common case, so it must advance to the next tile rather than
        # end the survey; we only give up (return None) when nextTile() reports the
        # region is fully imaged, there's no region, or we're out of cells.
        while not win._unranked_cells:
            if self._outOfCells():
                set_state("Autopatch: reached end of cell list; stopping")
                return None
            if not win._surveyRegion.hasRegion():
                set_state("Autopatch: add a survey region to search for cells")
                return None
            center = run_in_gui_thread(win._surveyRegion.nextTile)
            if center is None:
                set_state("Autopatch: survey region fully imaged; stopping")
                return None
            set_state("Autopatch: moving to next survey tile")
            win.scopeDevice.setGlobalPosition(center, name="autopatch survey move").wait()
            set_state("Autopatch: searching for cells")
            surf = win.cameraDevice.scopeDev.findSurfaceDepth(win.cameraDevice)
            win.cameraDevice.setFocusDepth(surf - 60e-6, "fast").wait()
            fut = win._detector._detectNeuronsZStack()
            fut.sigFinished.connect(win._detector._handleDetectResults)  # adds to win._unranked_cells
            fut.wait(timeout=600)

        set_state("Autopatch: checking selected cell")
        cell = win._unranked_cells.pop(0)
        self._hasWorkedCell = True
        win._ranked_cells.append(cell)
        win.patchPipetteDevice.setCell(cell)
        win._cell = cell
        # cell.sigPositionChanged.connect(win._feature_tracker._updatePipetteTarget)

        # stack = win._current_classification_stack or win._current_detection_stack
        # if (pos - margin) not in stack or (pos + margin) not in stack:
        # stack = None
        try:
            cell.initializeTracker(win.cameraDevice)
        except Stopped:
            raise
        except ValueError as e:
            if win._mockDemo:
                logger.info(f"Autopatch: Mocking cell despite {e}")
                return cell
            logger.info(f"Cell moved too much? {e}\nRetrying")
            return self._autopatchFindCell()
        logger.info(f"Autopatch: Cell found at {cell.position}")
        return cell

    def _autopatchRunTaskRunner(self):
        win = self._window
        man = win.module.manager
        ppip = win.patchPipetteDevice
        clampName = ppip.clampDevice.name()
        taskrunner: TaskRunner | None = None
        for mod in man.listInterfaces('taskRunnerModule'):
            mod = man.getModule(mod)
            if clampName in mod.docks:
                taskrunner = mod
                break
        if taskrunner is None:
            logger.warning(f"No task runner found that uses {clampName}")
            return

        expected_duration = (
            taskrunner.sequenceInfo["period"] * taskrunner.sequenceInfo["totalParams"]
        )
        # run_in_gui_thread(taskrunner.runSequence, store=True, storeDirHandle=self.dh).wait(...)
        run_in_gui_thread(taskrunner.runSequence, store=True).wait(
            timeout=max(30, expected_duration * 20),
        )
        logger.warning("Autopatch: Task runner sequence completed.")

    def _saveStack(self, name):
        ppip = self._window.patchPipetteDevice
        start = ppip.pipetteDevice.targetPosition()[2] - (20e-6 / 2)
        end = start + 20e-6
        save_in = ppip.dm.getCurrentDir().getDir(f"{name} stack", create=True)
        run_image_sequence(
            ppip.imagingDevice(),
            z_stack=(start, end, 1e-6),
            storage_dir=save_in,
            name="cellfie",
        ).wait()
        sleep(5)  # pose for the user
